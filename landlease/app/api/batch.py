"""批次导入：上传 → 落盘 SHA256 → 识别 + 归宗 + 核算（端到端管道）。

入口：
- POST /api/batches                          建空批次
- POST /api/batches/{id}/upload            上传扫描件（文件名「档案号_页序.jpg」）
- POST /api/batches/{id}/run                跑识别 + 归宗 + 核算
- GET  /api/batches                          分页列表
- GET  /api/batches/{id}                     详情
- POST /api/batches/{id}/rollback            撤回（按批次回滚 + 级联重算）
"""
from __future__ import annotations

import hashlib
import uuid
from datetime import datetime
from pathlib import Path
from typing import List

from fastapi import APIRouter, BackgroundTasks, Depends, File, HTTPException, UploadFile
from sqlalchemy import desc, delete, func, select
from sqlalchemy.orm import Session

from ..core.config import settings
from ..core.db import get_db
from ..models import (AuditLog, ContractDoc, FieldCorrection, FieldExtraction,
                      FileObject, ImportBatch, Issue)
from ..schemas import BatchCreate, BatchOut, ContractDocOut, Page
from ._common import apply_pagination, page_params

router = APIRouter(prefix='/api/batches', tags=['batch'])


@router.post('', response_model=BatchOut)
def create_batch(payload: BatchCreate, db: Session = Depends(get_db)):
    b = ImportBatch(batch_no=f'B{datetime.now():%Y%m%d%H%M%S}-{uuid.uuid4().hex[:6]}',
                      batch_type=payload.batch_type, status='created')
    db.add(b); db.commit(); db.refresh(b)
    return b


@router.post('/{batch_id}/upload', response_model=dict)
async def upload_files(batch_id: int, files: List[UploadFile] = File(...),
                       db: Session = Depends(get_db)):
    """上传扫描件。同批次同路径重复上传时覆盖更新（幂等），不会触发唯一键冲突。"""
    b = db.get(ImportBatch, batch_id) or _404('批次')
    rel_root = Path(b.batch_no)
    abs_root = settings.STORAGE_DIR / rel_root
    abs_root.mkdir(parents=True, exist_ok=True)
    for f in files:
        name = f.filename or ''
        archive_no = name.split('_')[0] if '_' in name else Path(name).stem
        page = int(name.split('_')[1].split('.')[0]) if '_' in name else 1
        data = await f.read()
        sha = hashlib.sha256(data).hexdigest()
        rel = str(rel_root / archive_no / f'{archive_no}_{page:02d}{Path(name).suffix}')
        dest = settings.STORAGE_DIR / rel
        dest.parent.mkdir(parents=True, exist_ok=True)
        dest.write_bytes(data)
        # upsert：同批次同路径 → 覆盖（重新上传 / 分次选择同一文件）
        existing = db.scalar(select(FileObject).where(
            FileObject.batch_id == batch_id, FileObject.rel_path == rel))
        if existing:
            existing.page_no = page
            existing.sha256 = sha
            existing.mime = f.content_type
            existing.size = len(data)
        else:
            db.add(FileObject(batch_id=batch_id, archive_no=archive_no, page_no=page,
                              rel_path=rel, sha256=sha, mime=f.content_type, size=len(data)))
    db.flush()
    # 汇总该批次全部文件（而非本次请求），追加式上传计数正确
    b.file_count = db.scalar(
        select(func.count()).select_from(FileObject).where(FileObject.batch_id == batch_id))
    b.doc_count = db.scalar(
        select(func.count(func.distinct(FileObject.archive_no)))
        .where(FileObject.batch_id == batch_id))
    b.status = 'uploaded'
    db.commit()
    return {'batch_id': batch_id, 'archive_count': b.doc_count,
            'file_count': b.file_count}


@router.post('/{batch_id}/run', response_model=dict)
def run_pipeline(batch_id: int, background: BackgroundTasks,
                 db: Session = Depends(get_db), model: str = None):
    """提交识别任务：立即置 processing 并返回，识别在后台执行（页面可自由跳转）。"""
    b = db.get(ImportBatch, batch_id) or _404('批次')
    if b.status not in ('uploaded', 'failed'):
        raise HTTPException(400, f'批次状态 {b.status}，不允许执行')

    n = db.scalar(select(func.count()).select_from(FileObject)
                  .where(FileObject.batch_id == batch_id))
    if not n:
        raise HTTPException(400, '批次无文件，请先上传')

    # 关键：先落库 processing 并提交，前端刷新/跳转回来能看到「识别中」
    b.status = 'processing'
    db.add(AuditLog(actor='系统', action='batch_run_submit',
                    target_type='batch', target_id=str(batch_id)))
    db.commit()
    background.add_task(_run_pipeline_job, batch_id, model)
    return {'batch_id': batch_id, 'status': 'processing', 'accepted': True,
            'message': '识别任务已提交，正在后台执行'}


def _run_pipeline_job(batch_id: int, model: str | None = None) -> None:
    """后台识别任务：独立 DB 会话，完成置 done，异常置 failed 并写审计。

    `model` 可为通道 id / 通道名 / 模型名；为空则取当前主通道（channel.resolve）。
    """
    from ..core.db import SessionLocal
    from ..services import channel as channel_svc, dataset, recognize
    from ..services.calc import Standard

    db = SessionLocal()
    try:
        b = db.get(ImportBatch, batch_id)
        if b is None:
            return
        # 识别前一次性锁定通道：批次内所有文档走同一通道，便于比对与留痕
        ch = channel_svc.resolve(db, model)
        if not ch.available:
            raise RuntimeError(f'通道「{ch.name}」凭据缺失（{ch.api_key_env or "API Key"} 未配置）')
        db.add(AuditLog(actor='系统', action='ocr_channel',
                        target_type='batch', target_id=str(batch_id),
                        after_value=f'{ch.name} / {ch.model_id} / {ch.kind}'))
        db.commit()

        files = db.scalars(select(FileObject).where(FileObject.batch_id == batch_id)
                            .order_by(FileObject.archive_no, FileObject.page_no)).all()
        grouped: dict = {}
        for f in files:
            grouped.setdefault(f.archive_no, []).append(settings.STORAGE_DIR / f.rel_path)

        data = dataset.load_practice()
        std_list = [Standard(s.land_usage, s.land_level, s.effective_from, s.price)
                    for s in dataset.parse_standards(data['standards'])]

        issue_count = 0
        # 识别阶段并发（VLM 为 IO 密集，纯函数无 DB 依赖），写库仍在主线程串行
        import os as _os
        from concurrent.futures import ThreadPoolExecutor, as_completed

        workers = int(_os.getenv('OCR_WORKERS', '4'))
        tasks = list(grouped.items())

        def _recognize(item):
            arc, paths = item
            return arc, recognize.recognize_document(arc, paths, std_list, channel=ch)

        results = {}
        with ThreadPoolExecutor(max_workers=max(1, workers)) as ex:
            futs = {ex.submit(_recognize, t): t[0] for t in tasks}
            for fut in as_completed(futs):
                arc = futs[fut]
                try:
                    results[arc] = fut.result()[1]
                except Exception as e:            # noqa: BLE001 单份失败不阻塞整批
                    db.add(AuditLog(actor='系统', action='ocr_failed',
                                    target_type='contract_doc', target_id=arc,
                                    after_value=f'{type(e).__name__}: {e}'[:400]))

        for arc, _paths in tasks:
            doc = results.get(arc)
            if doc is None:
                continue
            c = _doc_from_result(arc, batch_id, doc)
            # 重新导入同一档案：覆盖字段并回到待复核状态（幂等，可重复执行识别）
            exist = db.get(ContractDoc, arc)
            was_landed = None
            if exist:
                if exist.status == 'confirmed':
                    # 重新识别等于撤回上次确认 → 记录所属宗地，稍后回滚其台账
                    from ..models import ParcelDoc
                    was_landed = db.scalar(
                        select(ParcelDoc.parcel_key).where(ParcelDoc.archive_no == arc))
                for col in ContractDoc.__table__.columns.keys():
                    if col in ('id', 'created_at'):
                        continue
                    setattr(exist, col, getattr(c, col))
            else:
                db.add(c)
            db.flush()
            if was_landed:
                # 该档案已不在「已确认」集合 → 重算宗地（无其他已确认合同时整宗移除）
                from ..services.ledger import recompute_parcel
                recompute_parcel(db, was_landed)
            # 清掉该档案旧的字段抽取与未消解问题（无论合同是否已存在都执行，保证幂等）
            db.execute(delete(FieldExtraction).where(FieldExtraction.doc_id == arc))
            db.execute(delete(Issue).where(Issue.target == arc, Issue.status == 'open'))
            db.flush()
            for f in doc.fields.values():
                db.add(FieldExtraction(doc_id=arc, field_name=f.name,
                                        ai_value=f.ai_value, final_value=f.final_value,
                                        confidence=f.confidence, source=f.source,
                                        reason={'rules': f.rules, 'issues': f.issues}))
            # 1) 字段层问题（识别/校验/反推）
            seen = set()
            for t, m in doc.issues():
                if t in seen:      # 同一档案同一问题类型只记一条（避免字段级与登记比对重复）
                    continue
                seen.add(t)
                db.add(Issue(target=arc, issue_type=t, description=m))
                issue_count += 1
            # 2) 宗地层问题（与不动产登记比对：面积/坐落/权利人）
            for t, m in _registry_issues(db, c):
                if t in seen:
                    continue
                seen.add(t)
                db.add(Issue(target=arc, issue_type=t, description=m))
                issue_count += 1
            db.commit()      # 每份合同单独提交，长任务中断也保留已识别成果
        b = db.get(ImportBatch, batch_id)
        b.status = 'done'
        db.add(AuditLog(actor='系统', action='batch_run_done',
                        target_type='batch', target_id=str(batch_id),
                        after_value=f'archives={len(grouped)}, issues={issue_count}'))
        db.commit()
    except Exception as e:      # noqa: BLE001
        db.rollback()
        try:
            b = db.get(ImportBatch, batch_id)
            if b is not None:
                b.status = 'failed'
            db.add(AuditLog(actor='系统', action='batch_run_failed',
                            target_type='batch', target_id=str(batch_id),
                            after_value=f'{type(e).__name__}: {e}'[:500]))
            db.commit()
        except Exception:       # noqa: BLE001
            db.rollback()
    finally:
        db.close()




def _registry_issues(db: Session, c: ContractDoc) -> list:
    """与不动产登记导出比对，生成宗地层问题（PRD 6.4 中依赖登记数据的那几类）。"""
    from ..services.grouping import compare_with_registry
    from ..services.ledger import match_registry, BASELINE as _BASE

    reg = match_registry(db, c.parcel_no)
    if reg is None:
        # 登记库查不到该宗地 → 登记数据中无对应宗地
        if c.parcel_no:
            return [('登记数据中无对应宗地',
                     f'不动产登记导出中查无宗地号「{c.parcel_no}」')]
        return []
    status = '到期未续' if (c.end_date and c.end_date < _BASE) else '有效'
    doc_dict = {
        '档案号': c.id, '承租人': c.lessee, '坐落': c.location,
        '宗地号': c.parcel_no, '不动产单元号': reg.unit_no,
        '土地面积': c.area, '租赁终止日': c.end_date,
        # 三态：明确「有」→是 / 明确「无」→否 / 未识别→None（不判缺宗地图）
        '有无宗地图': ('是' if c.has_map == 1 else '否' if c.has_map == 0 else None),
        '涂改字段': c.altered_field,
        '涂改处有无签章': ('是' if c.altered_seal == 1 else '否' if c.altered_seal == 0 else None),
        '年租金小写': c.rent_amount, '年租金大写': c.rent_amount_cn,
        '证件号码': c.id_no, '联系电话': c.phone,
    }
    ledger = {'登记坐落': reg.location, '登记面积': reg.area,
              '登记权利人': reg.owner, '不动产单元号': reg.unit_no,
              '合同状态': status}
    out = []
    for item in compare_with_registry(doc_dict, ledger, []):
        out.append((item['问题类型'], item['说明']))
    return out


@router.get('', response_model=Page[BatchOut])
def list_batches(db: Session = Depends(get_db), params: dict = Depends(page_params)):
    q = db.query(ImportBatch).order_by(desc(ImportBatch.created_at))
    return apply_pagination(q, params)


@router.post('/{batch_id}/rollback', response_model=dict)
def rollback_batch(batch_id: int, operator: str = '操作员',
                   db: Session = Depends(get_db)):
    """撤回批次：级联删除该批次产生的合同/字段/问题，并回滚其生成的宗地台账。"""
    from ..models import Parcel, ParcelDoc, RentDue
    from ..services.ledger import recompute_parcel

    b = db.get(ImportBatch, batch_id) or _404('批次')
    if b.status in ('rolled_back',):
        raise HTTPException(400, '批次已撤回')
    if b.status == 'processing':
        raise HTTPException(400, '批次识别执行中，不允许撤回')

    # 该批次的全部档案号
    archives = [row for row in db.scalars(
        select(ContractDoc.id).where(ContractDoc.batch_id == batch_id)).all()]

    deleted = {'contracts': len(archives), 'fields': 0, 'corrections': 0,
               'issues': 0, 'parcels': 0}
    if archives:
        # 受影响的宗地
        parcel_keys = set(db.scalars(
            select(ParcelDoc.parcel_key).where(ParcelDoc.archive_no.in_(archives))).all())
        # 字段改正（挂在字段抽取下）→ 字段抽取 → 问题 → 宗地关系 → 合同
        ext_ids = list(db.scalars(
            select(FieldExtraction.id).where(FieldExtraction.doc_id.in_(archives))).all())
        if ext_ids:
            deleted['corrections'] = db.execute(
                delete(FieldCorrection).where(FieldCorrection.extraction_id.in_(ext_ids))).rowcount
            deleted['fields'] = db.execute(
                delete(FieldExtraction).where(FieldExtraction.doc_id.in_(archives))).rowcount
        deleted['issues'] = db.execute(
            delete(Issue).where(Issue.target.in_(archives))).rowcount
        db.execute(delete(ParcelDoc).where(ParcelDoc.archive_no.in_(archives)))
        db.execute(delete(ContractDoc).where(ContractDoc.id.in_(archives)))
        db.flush()

        # 宗地：仍有已确认合同的 → 重算；已无合同 → 整宗删除
        for pk in parcel_keys:
            remain = db.scalar(
                select(ParcelDoc.parcel_key).where(ParcelDoc.parcel_key == pk).limit(1))
            if remain:
                recompute_parcel(db, pk)
            else:
                db.execute(delete(RentDue).where(RentDue.parcel_key == pk))
                db.execute(delete(Parcel).where(Parcel.parcel_key == pk))
                deleted['parcels'] += 1

    b.status = 'rolled_back'
    db.add(AuditLog(actor=operator, action='batch_rollback',
                    target_type='batch', target_id=str(batch_id),
                    after_value=f'deleted={deleted}'))
    db.commit()
    return {'ok': True, 'batch_id': batch_id, 'batch_no': b.batch_no,
            'status': 'rolled_back', **deleted}


@router.get('/{batch_id}', response_model=BatchOut)
def get_batch(batch_id: int, db: Session = Depends(get_db)):
    return db.get(ImportBatch, batch_id) or _404('批次')


def _404(msg: str):
    raise HTTPException(404, f'{msg}不存在')


import re as _re

def _clean_num(v):
    """从 VLM 输出中提取数值：'5年'→5, '542.79元'→542.79, '1.40元/m²·年'→1.40"""
    if v is None or v == '':
        return None
    s = str(v).strip()
    m = _re.match(r'^[-+]?\d+(?:\.\d+)?', s)
    return m.group() if m else None


def _clean_int(v):
    n = _clean_num(v)
    return int(float(n)) if n else None


def _clean_date(v):
    """VLM 日期字符串 → date；无法解析返回 None（交给后续校验/问题清单记录）。"""
    from ..services.calc import to_date
    return to_date(v) if v not in (None, '') else None


def _clean_flag(v):
    """是/有/1 → 1；否/无/0 → 0；无法判断 → None（None 不产生「缺宗地图」等误报）。"""
    if v in (None, ''):
        return None
    s = str(v).strip()
    if s in ('是', '有', '1', '√', '✓', 'True', 'true'):
        return 1
    if s in ('否', '无', '0', '×', '✗', 'False', 'false'):
        return 0
    return None


def _clean_rent_mode(v):
    """计租方式归一化：VLM 常返回带勾选框的原文，需映射为标准值（固定 / 随标准调整）。"""
    if v in (None, ''):
        return None
    s = str(v)
    if '随' in s and ('标准' in s or '基准地价' in s):
        return '随标准调整'
    if '固定' in s:
        return '固定'
    return s.strip()


def _clean_usage(v):
    """用途归一化：标准表取值为 商服/住宅/工业/仓储，VLM 常带「用地」后缀。"""
    if v in (None, ''):
        return None
    return str(v).strip().replace('用地', '') or None


def _doc_from_result(archive_no: str, batch_id: int, doc) -> 'ContractDoc':
    f = doc.fields
    g = lambda n: (f.get(n).final_value if n in f else None)   # noqa: E731
    return ContractDoc(
        id=archive_no, batch_id=batch_id, doc_type=g('合同类型'),
        page_count=doc.page_count or None,
        contract_no=g('合同编号'), orig_contract_no=g('原合同编号'),
        sign_date=_clean_date(g('签订日期')), lessor=g('出租人'), lessee=g('承租人'),
        lessee_type=g('承租人类型'), id_no=g('证件号码'), phone=g('联系电话'),
        address=g('住所'), parcel_no=g('宗地号'), location=g('坐落'),
        area=_clean_num(g('土地面积')), land_usage=_clean_usage(g('用途')), land_level=g('土地级别'),
        start_date=_clean_date(g('租赁起始日')), end_date=_clean_date(g('租赁终止日')),
        years=_clean_int(g('租赁年限')), rent_mode=_clean_rent_mode(g('计租方式')),
        rate=_clean_num(g('年租金标准')), rent_amount=_clean_num(g('年租金小写')),
        rent_amount_cn=g('年租金大写'),
        has_map=_clean_flag(g('有无宗地图')),
        altered_field=g('涂改字段'), altered_before=g('涂改前内容'),
        altered_seal=_clean_flag(g('涂改处有无签章')),
        process_type=doc.process_type, status='pending',
    )