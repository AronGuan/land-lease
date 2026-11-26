"""欠缴看板：Top5 + 治理队列 + 按年度/用途的分布。"""
from __future__ import annotations

from fastapi import APIRouter, Depends
from sqlalchemy import desc, func, select
from sqlalchemy.orm import Session

from ..core.db import get_db
from ..models import Parcel, RentDue
from ..schemas import Page, ParcelOut
from ._common import apply_pagination, page_params

router = APIRouter(prefix='/api/dashboard', tags=['dashboard'])


@router.get('/kpis', response_model=dict)
def kpis(db: Session = Depends(get_db)):
    """工作台六卡 + 治理口径统计（全部由数据库实时汇总，前端不再硬编码）。"""
    from ..models import ContractDoc, FieldCorrection, FieldExtraction, FileObject, Issue
    confirmed = ContractDoc.status == 'confirmed'
    total_contracts = db.scalar(select(func.count(ContractDoc.id)).where(confirmed)) or 0
    # 原件张数：按合同页数累加（缺页数按 1 张计），无页数信息时回退到批次文件数
    total_files = db.scalar(
        select(func.sum(func.coalesce(ContractDoc.page_count, 1))).where(confirmed)) or 0
    if db.scalar(select(func.count(ContractDoc.page_count)).where(confirmed)) == 0:
        total_files = db.scalar(select(func.count(FileObject.id))) or 0
    auto_pass = db.scalar(
        select(func.count(ContractDoc.id)).where(confirmed,
                                                 ContractDoc.process_type == '自动通过')) or 0
    manual = db.scalar(
        select(func.count(ContractDoc.id)).where(confirmed,
                                                 ContractDoc.process_type == '人工复核')) or 0
    # 准确率口径：自动通过件中未经人工字段改正的比例
    corrected = db.scalar(
        select(func.count(func.distinct(FieldExtraction.doc_id)))
        .where(FieldExtraction.id.in_(select(FieldCorrection.extraction_id))
               & FieldExtraction.doc_id.in_(
                   select(ContractDoc.id).where(confirmed,
                                                ContractDoc.process_type == '自动通过')))) or 0
    return {
        'total_parcels': db.scalar(select(func.count(Parcel.parcel_key))) or 0,
        'total_due': float(db.scalar(select(func.sum(Parcel.total_due))) or 0),
        'total_arrears': float(db.scalar(select(func.sum(Parcel.arrears))) or 0),
        'due_2026': float(db.scalar(select(func.sum(Parcel.due_2026))) or 0),
        'pending_review': db.scalar(
            select(func.count(ContractDoc.id)).where(
                ContractDoc.status.in_(('pending', 'reverted')))) or 0,
        'issues_open': db.scalar(
            select(func.count(Issue.id)).where(Issue.status == 'open')) or 0,
        # 治理口径
        'total_contracts': total_contracts,
        'total_files': int(total_files or 0),
        'auto_pass_docs': auto_pass,
        'manual_docs': manual,
        'corrected_docs': corrected,
    }


@router.get('/arrears-top', response_model=list)
def arrears_top(n: int = 5, db: Session = Depends(get_db)):
    rows = db.scalars(select(Parcel).where(Parcel.arrears > 0)
                          .order_by(desc(Parcel.arrears)).limit(n)).all()
    return [{'key': p.parcel_key, 'lessee': p.contract_lessee,
             'phone': p.phone, 'arrears': float(p.arrears or 0),
             'years': p.arrears_years} for p in rows]


@router.get('/distributions', response_model=dict)
def distributions(db: Session = Depends(get_db)):
    by_year = db.execute(
        select(RentDue.year, func.sum(RentDue.arrears))
        .where(RentDue.arrears > 0).group_by(RentDue.year)
        .order_by(RentDue.year)
    ).all()
    by_usage = db.execute(
        select(Parcel.land_usage, func.sum(Parcel.arrears))
        .where(Parcel.arrears > 0).group_by(Parcel.land_usage)
    ).all()
    return {
        'by_year': [{'year': y, 'arrears': float(a or 0)} for y, a in by_year],
        'by_usage': [{'usage': u, 'arrears': float(a or 0)} for u, a in by_usage],
    }


@router.get('/governance-queue', response_model=dict)
def governance_queue(db: Session = Depends(get_db)):
    """治理队列：批次未决 + 待复核 + 存疑。"""
    from ..models import ContractDoc, ImportBatch, Issue
    return {
        'batches_pending': db.scalar(
            select(func.count(ImportBatch.id)).where(
                ImportBatch.status.in_(('created', 'uploaded', 'processing')))) or 0,
        'docs_pending': db.scalar(
            select(func.count(ContractDoc.id)).where(ContractDoc.status != 'confirmed')) or 0,
        'issues_open': db.scalar(
            select(func.count(Issue.id)).where(Issue.status == 'open')) or 0,
    }