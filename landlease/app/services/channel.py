"""模型通道注册表：闭源云端 / 开源可部署 / 本地离线三条通道的解析、切换与探活。

设计要点
--------
1. 通道元数据落 `model_config` 表（endpoint / model_id / params）；**凭据只存环境变量名**
   （`params.api_key_env`），不落库明文，符合本项目「代码零硬编码、密钥进 .env」的约定。
2. 运行时由 `resolve()` 统一给出 (base_url, model_id, api_key)，`vlm.py` 不再关心通道来源，
   因此「闭源 ↔ 开源」切换不需要改识别代码，也不需要重启进程。
3. 切换只改 `is_active` 并写 `audit_log`（审计留痕），下一份文档立即走新通道。

赛题对应：第五节(2)「模型调用要做成可配置、可切换；正式环境使用政务网内的模型服务或在本地
服务器部署的开源模型」，表 4「部署与运行——模型能否现场切换」。
"""
from __future__ import annotations

import os
import time
from dataclasses import dataclass, field
from typing import Optional

import httpx
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..core.config import settings
from ..models import AuditLog, ModelConfig

# 通道类型 → 中文标签（前端直接展示，避免两侧各写一套映射）
KIND_LABEL = {
    'cloud': '闭源云端',
    'opensource': '开源可部署',
    'local': '本地离线',
}


# ---------- 默认通道（库内无记录时兜底，保证空库也能跑） ----------

def default_channels() -> list[dict]:
    """三条默认通道。endpoint 取 .env 现值，界面可再改。"""
    return [
        dict(
            name='qwen3-vl-plus',
            channel='cloud',
            endpoint=settings.DASHSCOPE_BASE_URL,
            model_id=settings.DEFAULT_VL_MODEL,
            is_active=1,
            params={
                'vendor': '阿里云百炼',
                'desc': '云端 API · 通用识别抽取',
                'api_key_env': 'DASHSCOPE_API_KEY',
                'open_weight': False,
                'price': '¥0.002/页',
            },
        ),
        dict(
            name='Qwen3-VL-32B（开源）',
            channel='opensource',
            endpoint=settings.OPENSOURCE_BASE_URL,
            model_id=settings.OPENSOURCE_VL_MODEL,
            is_active=0,
            params={
                'vendor': '硅基流动 SiliconFlow',
                'desc': '开源权重 · OpenAI 兼容托管\n可换政务网内 vLLM 地址（1×A100/H100）',
                'api_key_env': 'OPENSOURCE_API_KEY',
                'open_weight': True,
                'license': 'Apache-2.0',
            },
        ),
        dict(
            name='PaddleOCR（本地）',
            channel='local',
            endpoint='',
            model_id='paddleocr',
            is_active=0,
            params={
                'vendor': 'PaddleOCR',
                'desc': 'CPU 部署 · 政务网 / 离线场景\n不走网络，作降级兜底',
                'api_key_env': '',
                'open_weight': True,
                'license': 'Apache-2.0',
            },
        ),
    ]


# ---------- 数据结构 ----------

@dataclass
class Channel:
    id: Optional[int]
    name: str
    kind: str                 # cloud / opensource / local
    base_url: str
    model_id: str
    api_key_env: str
    is_active: bool
    params: dict = field(default_factory=dict)

    @property
    def kind_label(self) -> str:
        return KIND_LABEL.get(self.kind, self.kind)

    @property
    def api_key(self) -> str:
        """凭据运行时从环境变量取（.env 已由 config 模块加载）。"""
        if not self.api_key_env:
            return ''
        return os.getenv(self.api_key_env, '') or getattr(settings, self.api_key_env, '')

    @property
    def available(self) -> bool:
        """本地通道不依赖凭据；云端/开源通道必须有 key 才算可用。"""
        return True if self.kind == 'local' else bool(self.api_key)


def _to_channel(row: ModelConfig) -> Channel:
    p = row.params or {}
    return Channel(
        id=row.id,
        name=row.name,
        kind=row.channel,
        base_url=row.endpoint or '',
        model_id=row.model_id or '',
        api_key_env=p.get('api_key_env', ''),
        is_active=bool(row.is_active),
        params=p,
    )


def serialize(ch: Channel) -> dict:
    """API 出参：补充前端直接可用的派生字段。"""
    return {
        'id': ch.id,
        'name': ch.name,
        'kind': ch.kind,
        'channel': ch.kind,          # 兼容旧前端字段名
        'kind_label': ch.kind_label,
        'base_url': ch.base_url,
        'model_id': ch.model_id,
        'api_key_env': ch.api_key_env,
        'available': ch.available,
        'is_active': ch.is_active,
        'params': ch.params,
    }


# ---------- 读写 ----------

def ensure_defaults(db: Session) -> None:
    """空表时种入三条默认通道（幂等）。"""
    if db.scalar(select(ModelConfig.id).limit(1)):
        return
    for d in default_channels():
        db.add(ModelConfig(**d))
    db.commit()


def list_channels(db: Session) -> list[Channel]:
    ensure_defaults(db)
    rows = db.scalars(select(ModelConfig).order_by(ModelConfig.id)).all()
    return [_to_channel(r) for r in rows]


def get_channel(db: Session, cid: int) -> Channel:
    ensure_defaults(db)
    row = db.get(ModelConfig, cid)
    if row is None:
        raise LookupError(f'通道不存在：{cid}')
    return _to_channel(row)


def get_active(db: Session) -> Channel:
    chs = list_channels(db)
    return next((c for c in chs if c.is_active), chs[0])


def resolve(db: Session, key: Optional[str] = None) -> Channel:
    """按「通道 id / 通道名 / 模型名」解析通道；`None` 取主通道。

    未注册的模型名按闭源端点临时构造，便于试模型而不改表。
    """
    chs = list_channels(db)
    if not key:
        return next((c for c in chs if c.is_active), chs[0])
    k = str(key).strip()
    if k.isdigit():
        for c in chs:
            if c.id == int(k):
                return c
    for c in chs:
        if k in (c.name, c.model_id):
            return c
    return Channel(
        id=None, name=k, kind='cloud', base_url=settings.DASHSCOPE_BASE_URL,
        model_id=k, api_key_env='DASHSCOPE_API_KEY', is_active=False,
    )


def activate(db: Session, cid: int, actor: str = '管理员') -> Channel:
    """设为主通道：同一时刻仅一条 is_active，写审计。"""
    chs = list_channels(db)
    target = next((c for c in chs if c.id == cid), None)
    if target is None:
        raise LookupError(f'通道不存在：{cid}')
    if target.is_active:
        return target
    before = next((c.name for c in chs if c.is_active), '')
    for row in db.scalars(select(ModelConfig)).all():
        row.is_active = 1 if row.id == cid else 0
    db.add(AuditLog(
        actor=actor, action='model_switch', target_type='model_config',
        target_id=str(cid), before_value=before, after_value=target.name,
        context={'kind': target.kind, 'model_id': target.model_id,
                 'base_url': target.base_url},
    ))
    db.commit()
    db.refresh(db.get(ModelConfig, cid))
    return get_channel(db, cid)


def update_channel(db: Session, cid: int, *, name: Optional[str] = None,
                   endpoint: Optional[str] = None, model_id: Optional[str] = None,
                   api_key_env: Optional[str] = None,
                   actor: str = '管理员') -> Channel:
    """改地址 / 模型名 / 凭据环境变量名（开源通道接不同托管商或 vLLM 时用）。"""
    ensure_defaults(db)
    row = db.get(ModelConfig, cid)
    if row is None:
        raise LookupError(f'通道不存在：{cid}')
    before = {'name': row.name, 'endpoint': row.endpoint, 'model_id': row.model_id,
              'api_key_env': (row.params or {}).get('api_key_env', '')}

    if name:
        row.name = name
    if endpoint is not None:
        row.endpoint = endpoint
    if model_id is not None:
        row.model_id = model_id
    if api_key_env is not None:
        # JSON 列需整体赋值，原地改不会被 SQLAlchemy 侦测到
        p = dict(row.params or {})
        p['api_key_env'] = api_key_env
        row.params = p

    db.add(AuditLog(
        actor=actor, action='model_update', target_type='model_config',
        target_id=str(cid), before_value=str(before),
        after_value=str({'name': row.name, 'endpoint': row.endpoint,
                         'model_id': row.model_id, 'api_key_env': api_key_env}),
    ))
    db.commit()
    return get_channel(db, cid)


def probe(ch: Channel, timeout: float = 20.0) -> dict:
    """连通性探活：发一个 1-token 请求，返回 {ok, latency_ms, message}。

    只验证「地址可达 + 鉴权通过 + 模型名存在」，不消耗实质额度。
    """
    if ch.kind == 'local':
        try:
            __import__('paddleocr')
            return {'ok': True, 'latency_ms': 0,
                    'message': '本地通道就绪（PaddleOCR 已安装）'}
        except Exception:                       # noqa: BLE001
            return {'ok': False, 'latency_ms': 0,
                    'message': '本地通道未安装 PaddleOCR（pip install paddleocr）'}
    if not ch.available:
        return {'ok': False, 'latency_ms': 0,
                'message': f'凭据缺失：请在 .env 配置 {ch.api_key_env or "API Key"} 后重启后端'}
    if not ch.base_url:
        return {'ok': False, 'latency_ms': 0, 'message': '通道地址为空'}

    t0 = time.perf_counter()
    try:
        resp = httpx.post(
            f'{ch.base_url.rstrip("/")}/chat/completions',
            headers={'Authorization': f'Bearer {ch.api_key}'},
            json={'model': ch.model_id,
                  'messages': [{'role': 'user', 'content': 'ping'}],
                  'max_tokens': 1},
            timeout=timeout,
        )
        ms = int((time.perf_counter() - t0) * 1000)
        if resp.status_code == 200:
            return {'ok': True, 'latency_ms': ms, 'message': '连通正常'}
        code = ''
        try:
            code = (resp.json().get('error') or {}).get('code') or ''
        except Exception:                       # noqa: BLE001
            code = resp.text[:80]
        return {'ok': False, 'latency_ms': ms,
                'message': f'HTTP {resp.status_code} {code}'.strip()}
    except Exception as e:                      # noqa: BLE001
        ms = int((time.perf_counter() - t0) * 1000)
        return {'ok': False, 'latency_ms': ms,
                'message': f'{type(e).__name__}: {e}'[:160]}
