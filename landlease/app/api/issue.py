"""问题清单：13 类（PRD 6.4）+ 状态机（open/confirmed/resolved）。"""
from __future__ import annotations

from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import desc, select
from sqlalchemy import func as sa_func
from sqlalchemy.orm import Session

from ..core.db import get_db
from ..models import AuditLog, Issue
from ..services.grouping import ISSUE_TYPES
from ..schemas import IssueOut, Page
from ._common import apply_pagination, page_params

router = APIRouter(prefix='/api/issues', tags=['issue'])


@router.get('/types', response_model=list[str])
def list_issue_types():
    """13 类问题清单（严格使用，不得自创）。"""
    return ISSUE_TYPES


@router.get('/type-stats', response_model=dict)
def issue_type_stats(db: Session = Depends(get_db)):
    """13 类各自的条数（未消解 / 已消解 / 合计），供系统管理「问题类型」页对账。"""
    rows = db.execute(select(Issue.issue_type, Issue.status,
                             sa_func.count(Issue.id)).group_by(Issue.issue_type, Issue.status)).all()
    stat: dict = {t: {'open': 0, 'resolved': 0, 'total': 0} for t in ISSUE_TYPES}
    for t, st, n in rows:
        if t not in stat:
            stat[t] = {'open': 0, 'resolved': 0, 'total': 0}
        stat[t]['total'] += int(n)
        if st == 'open':
            stat[t]['open'] += int(n)
        else:
            stat[t]['resolved'] += int(n)
    return {'types': ISSUE_TYPES, 'stats': stat}


@router.get('', response_model=Page[IssueOut])
def list_issues(status: Optional[str] = Query(None),
                 issue_type: Optional[str] = Query(None),
                 keyword: Optional[str] = Query(None),
                 db: Session = Depends(get_db), params: dict = Depends(page_params)):
    q = db.query(Issue).order_by(desc(Issue.created_at))
    if status:
        q = q.where(Issue.status == status)
    if issue_type:
        q = q.where(Issue.issue_type == issue_type)
    if keyword:
        q = q.where(Issue.target.like(f'%{keyword}%')
                       | Issue.description.like(f'%{keyword}%'))
    return apply_pagination(q, params)


@router.post('/{id}/resolve', response_model=dict)
def resolve_issue(id: int, operator: str = '操作员',
                    comment: str = '已通过主管部门书面确认',
                    db: Session = Depends(get_db)):
    """关闭问题清单（含义：实地核验通过 / 主管部门书面确认）。"""
    i = db.get(Issue, id) or _404('问题')
    i.status = 'resolved'
    i.description = (i.description or '') + f'｜消解：{comment}'
    db.add(AuditLog(actor=operator, action='issue_resolve',
                     target_type='issue', target_id=str(id), after_value=comment))
    db.commit()
    return {'ok': True, 'id': id, 'status': 'resolved'}


def _404(msg: str):
    raise HTTPException(404, f'{msg}不存在')