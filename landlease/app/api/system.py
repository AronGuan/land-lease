"""系统管理：计租标准 + 街路级别 + 减免登记 + 模型管理 + 审计日志 + 配置项。"""
from __future__ import annotations

from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import desc, select
from sqlalchemy.orm import Session

from ..core.db import get_db
from ..models import (AuditLog, BackupRecord, ConfigItem, ModelConfig,
                       ReductionRecord, RentStandard, RegistryStreetLevel)
from ..schemas import AuditLogOut, ModelChannelUpdate, Page
from ._common import apply_pagination, orm_to_dict, page_params

router = APIRouter(prefix='/api/system', tags=['system'])


@router.get('/standards', response_model=list)
def list_standards(db: Session = Depends(get_db)):
    rows = db.scalars(select(RentStandard).order_by(RentStandard.land_usage,
                                                    RentStandard.effective_from)).all()
    return [orm_to_dict(r) for r in rows]


@router.get('/street-levels', response_model=list)
def list_street_levels(db: Session = Depends(get_db)):
    return [orm_to_dict(r) for r in db.scalars(select(RegistryStreetLevel)).all()]


@router.get('/reductions', response_model=list)
def list_reductions(db: Session = Depends(get_db)):
    return [orm_to_dict(r) for r in db.scalars(select(ReductionRecord)).all()]


@router.get('/audit-logs', response_model=Page[AuditLogOut])
def list_audit_logs(actor: Optional[str] = Query(None),
                      action: Optional[str] = Query(None),
                      db: Session = Depends(get_db),
                      params: dict = Depends(page_params)):
    q = db.query(AuditLog).order_by(desc(AuditLog.created_at))
    if actor:
        q = q.where(AuditLog.actor == actor)
    if action:
        q = q.where(AuditLog.action == action)
    return apply_pagination(q, params)


@router.get('/models', response_model=list)
def list_models(db: Session = Depends(get_db)):
    """模型通道列表（闭源云端 / 开源可部署 / 本地离线），含可用性与主通道标记。"""
    from ..services import channel as channel_svc
    return [channel_svc.serialize(c) for c in channel_svc.list_channels(db)]


@router.post('/models/{cid}/activate', response_model=dict)
def activate_model(cid: int, actor: str = '管理员',
                   db: Session = Depends(get_db)):
    """现场切换主通道：改 is_active + 写审计，下一份文档立即生效（无需重启）。"""
    from ..services import channel as channel_svc
    try:
        ch = channel_svc.activate(db, cid, actor)
    except LookupError as e:
        raise HTTPException(404, str(e))
    return {**channel_svc.serialize(ch), 'message': f'主通道已切换为 {ch.name}'}


@router.post('/models/{cid}/test', response_model=dict)
def test_model(cid: int, db: Session = Depends(get_db)):
    """通道探活：地址可达 + 鉴权通过 + 模型名存在，只发 1 token，不耗实质额度。"""
    from ..services import channel as channel_svc
    try:
        ch = channel_svc.get_channel(db, cid)
    except LookupError as e:
        raise HTTPException(404, str(e))
    return {'id': ch.id, 'name': ch.name, **channel_svc.probe(ch)}


@router.put('/models/{cid}', response_model=dict)
def update_model(cid: int, payload: ModelChannelUpdate,
                 actor: str = '管理员', db: Session = Depends(get_db)):
    """改通道地址 / 模型名 / 凭据环境变量名（开源通道接不同托管商或政务网内 vLLM）。"""
    from ..services import channel as channel_svc
    try:
        ch = channel_svc.update_channel(
            db, cid, name=payload.name, endpoint=payload.endpoint,
            model_id=payload.model_id, api_key_env=payload.api_key_env, actor=actor)
    except LookupError as e:
        raise HTTPException(404, str(e))
    return channel_svc.serialize(ch)


@router.get('/model-logs', response_model=list)
def list_model_logs(db: Session = Depends(get_db)):
    """模型调用日志（审计留痕）：最近 20 条。"""
    from ..models import ModelCallLog
    rows = db.scalars(select(ModelCallLog)
                      .order_by(desc(ModelCallLog.created_at)).limit(20)).all()
    return [orm_to_dict(r) for r in rows]


@router.post('/backup', response_model=dict)
def backup(operator: str = '系统',
               db: Session = Depends(get_db)):
    """触发备份（占位）：mysqldump + 校验文件 SHA256 + 写记录。"""
    db.add(BackupRecord(backup_type='manual', sha256_status='ok'))
    db.commit()
    return {'ok': True, 'type': 'manual'}