"""税务推送：按年度生成税务推送单（覆盖欠缴宗地明细）。"""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import desc, func, select
from sqlalchemy.orm import Session

from ..core.db import get_db
from ..models import Parcel, TaxPush, TaxPushItem
from ..schemas import TaxPushOut
from ._common import apply_pagination, page_params

router = APIRouter(prefix='/api/tax', tags=['tax'])


@router.post('/push', response_model=dict)
def push_tax(year: int = 2026, operator: str = '操作员',
                db: Session = Depends(get_db)):
    """对欠缴宗地生成税收推送单（明细按宗地欠缴行）。"""
    rows = db.execute(
        select(Parcel).where(Parcel.arrears > 0)
    ).scalars().all()
    if not rows:
        raise HTTPException(400, '无欠缴宗地')
    push = TaxPush(period=f'{year}Q4', year=year, row_count=len(rows),
                       total_amount=sum(p.arrears for p in rows), operator=operator)
    db.add(push); db.flush()
    for p in rows:
        db.add(TaxPushItem(push_id=push.id, parcel_key=p.parcel_key,
                              unit_no=p.unit_no, lessee=p.contract_lessee,
                              year=year, arrears=p.arrears))
    db.commit()
    return {'push_id': push.id, 'row_count': len(rows)}


@router.get('', response_model=list[TaxPushOut])
def list_pushes(db: Session = Depends(get_db)):
    return db.scalars(select(TaxPush)
                      .order_by(desc(TaxPush.created_at)).limit(50)).all()


@router.get('/{push_id}/items', response_model=list)
def push_items(push_id: int, db: Session = Depends(get_db)):
    """推送单明细（按税务部门模板字段）。"""
    from ..models import TaxPushItem
    rows = db.scalars(select(TaxPushItem).where(TaxPushItem.push_id == push_id)).all()
    from ..api._common import orm_to_dict
    return [orm_to_dict(r) for r in rows]