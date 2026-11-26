import sqlalchemy
from fastapi import APIRouter
from sqlalchemy import text

from ..core.config import settings
from ..core.db import engine

router = APIRouter(prefix='/api', tags=['health'])


@router.get('/health')
def health():
    """健康检查：库连通性 + 已建表数量 + 模型通道状态。"""
    db_ok, db_msg, table_count = True, 'ok', None
    try:
        with engine.connect() as conn:
            conn.execute(text('SELECT 1'))
            table_count = conn.execute(
                text("SELECT COUNT(*) FROM information_schema.tables WHERE table_schema = :db"),
                {'db': settings.DB_NAME},
            ).scalar()
    except Exception as e:  # noqa: BLE001 启动自检需要暴露真实原因
        db_ok, db_msg = False, str(e)[:200]

    return {
        'status': 'ok' if db_ok else 'degraded',
        'database': db_msg,
        'table_count': table_count,
        'sqlalchemy': sqlalchemy.__version__,
        'model': settings.DEFAULT_VL_MODEL,
        'api_key_configured': bool(settings.DASHSCOPE_API_KEY),
        'rule_version': settings.CALC_RULE_VERSION,
    }
