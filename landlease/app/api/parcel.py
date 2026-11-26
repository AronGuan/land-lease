"""宗地台账：列表（分页/筛选）+ 详情下钻（含应缴明细 + 缴费归集 + 合同链）。"""
from __future__ import annotations

from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import desc, func, select
from sqlalchemy.orm import Session

from ..core.db import get_db
from ..models import (Parcel, ParcelDoc, RentDue, PaymentAlloc, PaymentRecord,
                       ReductionRecord, ContractDoc)
from ..schemas import Page, ParcelOut, RentDueOut
from ._common import apply_pagination, orm_to_dict, page_params

router = APIRouter(prefix='/api/parcels', tags=['parcel'])


@router.get('', response_model=Page[ParcelOut])
def list_parcels(keyword: Optional[str] = Query(None),
                  land_usage: Optional[str] = Query(None),
                  arrears_min: Optional[float] = Query(None),
                  arrears_max: Optional[float] = Query(None),
                  db: Session = Depends(get_db), params: dict = Depends(page_params)):
    q = db.query(Parcel).order_by(desc(Parcel.updated_at))
    if keyword:
        q = q.where(Parcel.parcel_key.like(f'%{keyword}%'))
    if land_usage:
        q = q.where(Parcel.land_usage == land_usage)
    if arrears_min is not None:
        q = q.where(Parcel.arrears >= arrears_min)
    if arrears_max is not None:
        q = q.where(Parcel.arrears <= arrears_max)
    page = apply_pagination(q, params)
    # 附档案号列表 + 催缴状态（每宗地最新一份通知书）
    keys = [it.parcel_key for it in page['items']]
    doc_map: dict = {}
    notice_map: dict = {}
    if keys:
        from ..models import CollectionNotice
        for d in db.scalars(select(ParcelDoc).where(ParcelDoc.parcel_key.in_(keys))):
            doc_map.setdefault(d.parcel_key, []).append(d.archive_no)
        latest_ids = (select(func.max(CollectionNotice.id))
                      .where(CollectionNotice.parcel_key.in_(keys))
                      .group_by(CollectionNotice.parcel_key))
        for n in db.scalars(select(CollectionNotice)
                            .where(CollectionNotice.id.in_(latest_ids))):
            notice_map[n.parcel_key] = n
    # 直接构造 dict（响应模型会丢弃附加属性，必须在此填充）
    status_label = {'generated': '已催缴', '部分回款': '部分回款', '已回款': '已回款'}
    items = []
    for it in page['items']:
        row = orm_to_dict(it)
        row['archives'] = ';'.join(doc_map.get(it.parcel_key, [])) or None
        n = notice_map.get(it.parcel_key)
        row['dunning_status'] = status_label.get(n.status, '已催缴') if n else '未催缴'
        row['dunning_notice_id'] = n.id if n else None
        row['dunning_at'] = n.created_at.strftime('%Y-%m-%d %H:%M') if n and n.created_at else None
        items.append(row)
    page['items'] = items
    page['archives'] = {k: ';'.join(v) for k, v in doc_map.items()}
    return page


@router.get('/{parcel_key}', response_model=dict)
def get_parcel(parcel_key: str, db: Session = Depends(get_db)):
    p = db.get(Parcel, parcel_key) or _404('宗地')
    docs = db.scalars(select(ParcelDoc).where(ParcelDoc.parcel_key == parcel_key))
    archs = [d.archive_no for d in docs]
    contracts = db.scalars(select(ContractDoc).where(ContractDoc.id.in_(archs)))
    dues = db.scalars(select(RentDue).where(RentDue.parcel_key == parcel_key)
                          .order_by(RentDue.year))
    allocs = db.execute(
        select(PaymentAlloc, PaymentRecord)
        .join(PaymentRecord, PaymentAlloc.payment_id == PaymentRecord.id)
        .where(PaymentAlloc.parcel_key == parcel_key)
        .order_by(PaymentRecord.pay_date)
    ).all()
    reductions = db.scalars(
        select(ReductionRecord).where(ReductionRecord.parcel_key == parcel_key))
    return {
        'parcel': orm_to_dict(p),
        'contracts': [orm_to_dict(c) for c in contracts],
        'dues': [orm_to_dict(d) for d in dues],
        'payments': [{'alloc': orm_to_dict(a), 'payment': orm_to_dict(r)} for a, r in allocs],
        'reductions': [orm_to_dict(x) for x in reductions],
    }


@router.get('/{parcel_key}/contract-draft', response_model=dict)
def contract_draft(parcel_key: str, years: int = 10, db: Session = Depends(get_db)):
    """合同生成：按当前宗地要素生成续签合同草稿（PRD 宗地台账·合同生成 Tab）。

    续期起租日 = 原合同期满次日；终止日 = 起租日 + 年限 − 1 天（与口径一致）。
    """
    from datetime import date, timedelta
    p = db.get(Parcel, parcel_key) or _404('宗地')
    docs = db.scalars(select(ParcelDoc).where(ParcelDoc.parcel_key == parcel_key)).all()
    last = None
    if docs:
        # MySQL 无 NULLS LAST：用 (end_date IS NULL, end_date DESC) 让非空值优先
        last = db.scalars(
            select(ContractDoc)
            .where(ContractDoc.id.in_([d.archive_no for d in docs]))
            .order_by(ContractDoc.end_date.is_(None), ContractDoc.end_date.desc())
        ).first()

    old_end = (last.end_date if last else None) or p.end_date
    start = (old_end + timedelta(days=1)) if old_end else date(2027, 1, 1)
    months = years * 12
    ey = start.year + (start.month - 1 + months) // 12
    em = (start.month - 1 + months) % 12 + 1
    import calendar
    end = date(ey, em, min(start.day, calendar.monthrange(ey, em)[1])) - timedelta(days=1)

    # 建议年租金：随标准调整型按面积 × 当年标准；固定型沿用原年租金
    from ..models import RentStandard
    mode = p.rent_mode or ''
    area = _dec(p.contract_area or p.reg_area)
    std = db.scalars(
        select(RentStandard)
        .where(RentStandard.land_usage == p.land_usage,
               RentStandard.land_level == p.land_level,
               RentStandard.effective_from <= start)
        .order_by(RentStandard.effective_from.desc())
    ).first()
    suggest_rent = None
    if area and std:
        suggest_rent = round(float(area) * float(std.price), 2)

    return {
        'parcel_key': parcel_key,
        'doc_type': '续期',
        'orig_contract_no': last.contract_no if last else None,
        'orig_archive_no': last.id if last else None,
        'lessor': last.lessor if last else '××县自然资源和规划局',
        'lessee': p.reg_owner or p.contract_lessee,
        'id_no': last.id_no if last else None,
        'phone': p.phone,
        'location': p.reg_location,
        'parcel_no': last.parcel_no if last else None,
        'area': float(area) if area else None,
        'land_usage': p.land_usage,
        'land_level': p.land_level,
        'rent_mode': mode,
        'rate': float(std.price) if std else None,
        'suggest_rent': suggest_rent,
        'start_date': start.isoformat(),
        'end_date': end.isoformat(),
        'years': years,
        'warnings': (
            (['原合同已到期未续，续期自到期次日计'] if old_end and old_end < date(2026, 9, 30) else [])
            + (['登记权利人与合同承租人不一致，签约主体需核实']
               if p.reg_owner and p.contract_lessee and p.reg_owner != p.contract_lessee else [])
            + (['面积与登记不一致，草稿按合同面积，签约前需确认'] if p.contract_area and p.reg_area
               and abs(float(p.contract_area) - float(p.reg_area)) > 0.01 else [])
        ),
    }


def _dec(v):
    from decimal import Decimal, InvalidOperation
    try:
        return Decimal(str(v)) if v not in (None, '') else None
    except (InvalidOperation, ValueError):
        return None


def _404(msg: str):
    raise HTTPException(404, f'{msg}不存在')