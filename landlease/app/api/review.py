"""复核工作台：列表 + 字段详情 + 二次确认 + 字段改正留痕。（PRD 8）"""
from __future__ import annotations

from datetime import datetime
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import desc, select
from sqlalchemy import func as sa_func

func_min = sa_func.min

#: 决定整份档案能否自动通过的关键字段（与 recognize.judge 一致）
KEY_FIELDS = ('承租人', '证件号码', '土地面积', '租赁起始日', '租赁终止日', '年租金小写')
from sqlalchemy.orm import Session

from ..core.db import get_db
from ..models import (AuditLog, ContractDoc, FieldCorrection, FieldExtraction)
from ..schemas import (BatchConfirmIn, ContractDocOut, FieldCorrectionIn,
                       FieldExtractionOut, Page)
from ._common import apply_pagination, orm_to_dict, page_params

router = APIRouter(prefix='/api/review', tags=['review'])


@router.get('/docs', response_model=Page[ContractDocOut])
def list_docs(batch_id: Optional[int] = Query(None),
              process_type: Optional[str] = Query(None),
              status: Optional[str] = Query(None),
              keyword: Optional[str] = Query(None),
              db: Session = Depends(get_db), params: dict = Depends(page_params)):
    q = db.query(ContractDoc).order_by(desc(ContractDoc.id))
    if batch_id:
        q = q.where(ContractDoc.batch_id == batch_id)
    if process_type:
        q = q.where(ContractDoc.process_type == process_type)
        # 复核队列只列待办：已确认入库的不再占队列（避免"待复核"与实际不符）
        if not status:
            q = q.where(ContractDoc.status != 'confirmed')
    if status:
        q = q.where(ContractDoc.status == status)
    if keyword:
        like = f'%{keyword}%'
        q = q.where(
            ContractDoc.id.like(like)
            | ContractDoc.lessee.like(like)
            | ContractDoc.contract_no.like(like)
            | ContractDoc.location.like(like)
            | ContractDoc.parcel_no.like(like)
            | ContractDoc.phone.like(like)
            | ContractDoc.id_no.like(like)
        )
    page = apply_pagination(q, params)
    # 附「关键字段最低置信度」：决定该档案能否自动通过（阈值 AUTO_PASS_CONFIDENCE）
    ids = [it.id for it in page['items']]
    if ids:
        rows = db.execute(
            select(FieldExtraction.doc_id,
                   func_min(FieldExtraction.confidence))
            .where(FieldExtraction.doc_id.in_(ids),
                   FieldExtraction.field_name.in_(KEY_FIELDS))
            .group_by(FieldExtraction.doc_id)
        ).all()
        mc = {d: float(c) for d, c in rows if c is not None}
        for it in page['items']:
            it.min_confidence = mc.get(it.id)
    return page


@router.get('/docs/{archive_no}', response_model=dict)
def get_doc(archive_no: str, db: Session = Depends(get_db)):
    c = db.get(ContractDoc, archive_no) or _404('档案')
    fields = db.scalars(select(FieldExtraction)
                        .where(FieldExtraction.doc_id == archive_no)).all()
    return {'doc': orm_to_dict(c), 'fields': [orm_to_dict(f) for f in fields]}


@router.get('/docs/{archive_no}/pages', response_model=dict)
def list_pages(archive_no: str, db: Session = Depends(get_db)):
    """原件对照：返回页数、批次号与每页图片 URL。"""
    c = db.get(ContractDoc, archive_no) or _404('档案')
    from ..models import ImportBatch
    b = db.get(ImportBatch, c.batch_id)
    n = c.page_count or 1
    return {
        'archive_no': archive_no,
        'batch_no': b.batch_no if b else None,
        'page_count': n,
        'pages': [{'page_no': i,
                   'url': f'/api/review/docs/{archive_no}/pages/{i}'} for i in range(1, n + 1)],
    }


@router.get('/docs/{archive_no}/pages/{page_no}')
def get_page(archive_no: str, page_no: int, db: Session = Depends(get_db)):
    """返回某一页原件图片（先查 storage，回落练习集样本包）。"""
    from fastapi.responses import FileResponse
    from ..core.config import settings

    c = db.get(ContractDoc, archive_no) or _404('档案')
    from ..models import ImportBatch
    b = db.get(ImportBatch, c.batch_id)
    candidates = []
    if b:
        candidates += [
            settings.STORAGE_DIR / b.batch_no / archive_no / f'{archive_no}_{page_no:02d}.jpg',
            settings.STORAGE_DIR / b.batch_no / archive_no / f'{archive_no}_{page_no}.jpg',
        ]
    # 回落：练习集 / 测试集样本
    for base in ('国有土地租赁模拟样本包_练习集/练习集/01_合同扫描件',
                 '数据切分/test_20'):
        candidates += [
            settings.PROJECT_ROOT / base / f'{archive_no}_{page_no}.jpg',
            settings.PROJECT_ROOT / base / f'{archive_no}_{page_no}.png',
        ]
    for p in candidates:
        if p.exists():
            return FileResponse(p, media_type='image/jpeg')
    raise HTTPException(404, f'{archive_no} 第 {page_no} 页原件不存在（storage 与样本包均未找到）')


@router.post('/docs/{archive_no}/correct', response_model=dict)
def correct_field(archive_no: str, payload: FieldCorrectionIn,
                  db: Session = Depends(get_db)):
    """复核/入库后改正字段：写 final + 留痕 + 回写合同主表 + 已入库者重算台账。

    口径：任一字段被人工修改 → 处理方式改「人工复核」；
    若该档案已确认入库，改动立即回写主表并重算宗地台账（金额可追溯地随之变化），
    无需撤回重来；需要完整重走复核的，可先调 /revert 撤回再改。
    """
    from ..services.ledger import recompute_parcel
    from ..models import ParcelDoc

    c = db.get(ContractDoc, archive_no) or _404('档案')
    fe = db.scalar(select(FieldExtraction)
                   .where(FieldExtraction.doc_id == archive_no,
                          FieldExtraction.field_name == payload.field_name))
    if fe is None:
        raise HTTPException(404, '字段抽取记录不存在')
    before = fe.final_value
    fe.final_value = payload.after_value
    fe.is_corrected = 1
    fe.corrected_by = payload.operator
    fe.corrected_at = datetime.now()
    db.add(FieldCorrection(extraction_id=fe.id, before_value=before,
                            after_value=payload.after_value, operator=payload.operator))
    # 任一字段被人工修改 → 整份处理方式改为人工复核（PRD 8.1）
    c.process_type = '人工复核'

    # 回写合同主表（否则台账/统计仍用旧值，形成数据不一致）
    writeback = _apply_field_to_doc(c, payload.field_name, payload.after_value)
    db.flush()

    # 已确认入库 → 立即重算该宗地台账（应缴/欠缴随新值变化）
    ledger = None
    if c.status == 'confirmed':
        pk = db.scalar(select(ParcelDoc.parcel_key).where(ParcelDoc.archive_no == archive_no))
        if pk:
            ledger = recompute_parcel(db, pk)
            db.flush()

    db.add(AuditLog(actor=payload.operator, action='field_correct',
                     target_type='contract_doc', target_id=archive_no,
                     before_value=before, after_value=payload.after_value))
    db.commit()
    return {'ok': True, 'field_name': payload.field_name,
            'final_value': payload.after_value, 'writeback': writeback,
            'parcel_key': (ledger or {}).get('parcel_key'),
            'ledger_recomputed': ledger is not None,
            'total_due': (ledger or {}).get('total_due'),
            'arrears': (ledger or {}).get('arrears')}


# 字段名 → 合同主表列 & 类型转换
_DOC_FIELD_MAP = {
    '合同类型': 'doc_type', '合同编号': 'contract_no', '原合同编号': 'orig_contract_no',
    '出租人': 'lessor', '承租人': 'lessee', '承租人类型': 'lessee_type',
    '证件号码': 'id_no', '联系电话': 'phone', '住所': 'address',
    '宗地号': 'parcel_no', '坐落': 'location', '土地面积': 'area',
    '用途': 'land_usage', '土地级别': 'land_level', '租赁年限': 'years',
    '计租方式': 'rent_mode', '年租金标准': 'rate', '年租金小写': 'rent_amount',
    '年租金大写': 'rent_amount_cn', '涂改字段': 'altered_field',
    '涂改前内容': 'altered_before',
}
_DATE_FIELDS = {'签订日期': 'sign_date', '租赁起始日': 'start_date', '租赁终止日': 'end_date'}
_NUM_FIELDS = {'土地面积', '租赁年限', '年租金标准', '年租金小写'}
_INT_FIELDS = {'租赁年限'}
_FLAG_FIELDS = {'有无宗地图': 'has_map', '涂改处有无签章': 'altered_seal'}


def _apply_field_to_doc(c: ContractDoc, field_name: str, value) -> str | None:
    """把修正值回写到合同主表列，返回被写入的列名（无法映射时 None）。"""
    import re as _re

    col = _DOC_FIELD_MAP.get(field_name) or _DATE_FIELDS.get(field_name) \
        or _FLAG_FIELDS.get(field_name)
    if not col:
        return None
    if field_name in _DATE_FIELDS:
        from ..services.calc import to_date
        setattr(c, col, to_date(value) if value not in (None, '') else None)
        return col
    if field_name in _FLAG_FIELDS:
        s = str(value or '').strip()
        setattr(c, col, 1 if s in ('是', '有', '1', 'true', 'True') else 0 if s else None)
        return col
    if field_name in _NUM_FIELDS and value not in (None, ''):
        m = _re.match(r'^\s*[-+]?\d+(?:\.\d+)?', str(value))
        num = m.group() if m else None
        if num is None:
            return None
        setattr(c, col, int(float(num)) if field_name in _INT_FIELDS else num)
        return col
    setattr(c, col, value if value not in ('',) else None)
    return col


@router.post('/docs/{archive_no}/confirm', response_model=dict)
def confirm_doc(archive_no: str, operator: str = '操作员',
                 db: Session = Depends(get_db)):
    """单独确认（自动通过 + 人工复核档都走此接口）：确认即入库生成宗地台账。"""
    from ..services.ledger import confirm_and_land
    c = db.get(ContractDoc, archive_no) or _404('档案')
    if c.status == 'confirmed':
        raise HTTPException(400, '档案已确认')
    landed = confirm_and_land(db, c)
    db.add(AuditLog(actor=operator, action='doc_confirm',
                     target_type='contract_doc', target_id=archive_no,
                     after_value=f"parcel={landed['parcel_key']}"))
    db.commit()
    return {'ok': True, 'archive_no': archive_no, **landed}


@router.post('/batch-confirm', response_model=dict)
def batch_confirm(payload: BatchConfirmIn, db: Session = Depends(get_db)):
    """批量确认：返回抽检建议 + 最低置信预警 Top3（PRD 8.3）。"""
    from ..services.ledger import confirm_and_land
    rows = db.scalars(select(ContractDoc).where(ContractDoc.id.in_(payload.archive_nos))).all()
    if not rows:
        raise HTTPException(400, '档案号列表为空')
    confirmed, parcels = [], set()
    for c in rows:
        if c.status != 'confirmed':
            landed = confirm_and_land(db, c)
            parcels.add(landed['parcel_key'])
            confirmed.append(c.id)
    # 取 Top3 低置信关键字段
    low_conf = db.execute(
        select(FieldExtraction.field_name, FieldExtraction.confidence, FieldExtraction.doc_id)
        .where(FieldExtraction.doc_id.in_(payload.archive_nos),
                  FieldExtraction.confidence < 0.90)
        .order_by(FieldExtraction.confidence.asc()).limit(3)
    ).all()
    db.add(AuditLog(actor=payload.operator, action='batch_confirm',
                    target_type='contract_doc',
                    after_value=f'{len(confirmed)} confirmed, parcels={sorted(parcels)}'))
    db.commit()
    return {'confirmed': confirmed,
            'parcels': sorted(parcels),
            'sample_inspect_rate': payload.sample_inspect_rate,
            'low_confidence_top3': [{'archive': a, 'field': f, 'confidence': float(c)}
                                     for f, c, a in low_conf]}


@router.post('/docs/{archive_no}/revert', response_model=dict)
def revert_doc(archive_no: str, reason: str = '改字段后撤回',
                 operator: str = '操作员', db: Session = Depends(get_db)):
    """撤回已确认的档案：status=reverted + 该宗地按剩余已确认合同重算。"""
    from ..models import ParcelDoc
    from ..services.ledger import recompute_parcel
    c = db.get(ContractDoc, archive_no) or _404('档案')
    c.status = 'reverted'
    db.flush()          # session 为 autoflush=False，必须显式 flush 后重算才看得到新状态
    # 随确认一并消解的问题重新打开，回到待处理状态
    from sqlalchemy import update as _update
    from ..models import Issue
    db.execute(_update(Issue)
               .where(Issue.target == archive_no, Issue.status == 'resolved',
                      Issue.description.like('%复核入库确认消解%'))
               .values(status='open'))
    link = db.scalar(select(ParcelDoc).where(ParcelDoc.archive_no == archive_no))
    if link:
        recompute_parcel(db, link.parcel_key)
    db.add(AuditLog(actor=operator, action='doc_revert',
                     target_type='contract_doc', target_id=archive_no,
                     after_value=reason))
    db.commit()
    return {'ok': True, 'archive_no': archive_no, 'status': 'reverted',
            'parcel_key': link.parcel_key if link else None}


def _404(msg: str):
    raise HTTPException(404, f'{msg}不存在')