"""基础数据：02 登记 / 03 缴费 / 04 减免 / 05 标准的导入与重算。

上传 → 预览校验 → 确认落库（替换/追加）→ 重新归集 → 全量重算 → 差异清单。
"""
from __future__ import annotations

from typing import Optional

from fastapi import APIRouter, Depends, File, HTTPException, Query, UploadFile
from pydantic import BaseModel
from sqlalchemy.orm import Session

from ..core.db import get_db
from ..services import refdata

router = APIRouter(prefix='/api/refdata', tags=['refdata'])

_MAX_BYTES = 20 * 1024 * 1024
_EXTS = ('.xlsx', '.xls', '.csv')


class CommitIn(BaseModel):
    token: str
    kind: str
    mode: str = 'replace'          # replace / append
    sheet: Optional[str] = None
    operator: str = '系统'
    relink: bool = True            # 落库后是否立即重算


@router.get('/status', response_model=dict)
def status(db: Session = Depends(get_db)):
    """各类参考数据的当前行数与最近导入记录。"""
    return {'kinds': refdata.KINDS, 'data': refdata.status(db)}


@router.post('/preview', response_model=dict)
async def preview(file: UploadFile = File(...), kind: str = Query(...),
                  sheet: Optional[str] = None):
    """上传并解析，只返回摘要不落库。"""
    if kind not in refdata.KINDS:
        raise HTTPException(400, f'未知数据类型 {kind}')
    name = (file.filename or '').lower()
    if not name.endswith(_EXTS):
        raise HTTPException(400, f'仅支持 {"/".join(_EXTS)} 文件')
    content = await file.read()
    if len(content) > _MAX_BYTES:
        raise HTTPException(400, '文件超过 20MB')
    token = refdata.save_upload(file.filename or 'upload.xlsx', content)
    path = refdata.token_path(token)
    try:
        parsed = refdata.parse_file(path, kind, sheet)
    except Exception as e:                       # noqa: BLE001
        raise HTTPException(400, f'解析失败：{e}')
    return refdata.summarize(kind, parsed, token)


@router.post('/commit', response_model=dict)
def commit(payload: CommitIn, db: Session = Depends(get_db)):
    """确认落库。"""
    if payload.kind not in refdata.KINDS:
        raise HTTPException(400, f'未知数据类型 {payload.kind}')
    if payload.mode not in ('replace', 'append'):
        raise HTTPException(400, 'mode 只能是 replace 或 append')
    path = refdata.token_path(payload.token)
    if path is None:
        raise HTTPException(400, '上传凭据失效，请重新上传')
    parsed = refdata.parse_file(path, payload.kind, payload.sheet)
    if not parsed['rows']:
        raise HTTPException(400, '解析结果为空，未做任何改动')
    result = refdata.commit(db, payload.kind, parsed, payload.mode, payload.operator)
    if payload.relink:
        result['relink'] = refdata.relink(db, payload.operator)
    return result


@router.get('/duplicates', response_model=dict)
def duplicates(db: Session = Depends(get_db)):
    """列出指向同一宗地的重复宗地键（只列不改）。"""
    groups = refdata.duplicate_groups(db)
    return {'group_count': len(groups), 'groups': groups}


@router.post('/merge', response_model=dict)
def merge(operator: str = '系统', db: Session = Depends(get_db)):
    """合并重复宗地键（保留档案号最小者），迁移关联数据后重算。"""
    return refdata.merge_duplicates(db, operator)


@router.post('/relink', response_model=dict)
def relink(operator: str = '系统', db: Session = Depends(get_db)):
    """重新匹配登记 + 归集缴费/减免 + 全量重算，返回差异清单。"""
    return refdata.relink(db, operator)
