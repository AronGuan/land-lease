from pathlib import Path

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from .core.config import settings
from .core.db import engine, init_db
from .api import (batch, dashboard, dunning, health, issue, parcel,
                    refdata, review, system, tax)

app = FastAPI(title='国有土地租赁智能管理系统', version='1.0.0')

app.add_middleware(
    CORSMiddleware,
    allow_origins=['*'],
    allow_methods=['*'],
    allow_headers=['*'],
)

for r in (health.router, batch.router, review.router, parcel.router,
            issue.router, dashboard.router, dunning.router, tax.router,
            refdata.router, system.router):
    app.include_router(r)


@app.on_event('startup')
def on_startup():
    # 首次启动自动建库建表（表已存在则跳过）
    init_db()


@app.get('/api/root')
def api_root():
    return {'name': app.title, 'version': app.version, 'storage': str(settings.STORAGE_DIR)}


# ---------- 前端静态站点（离线部署包：单端口即可运行，无需 nginx / Node） ----------
WEB_DIR = Path(__file__).resolve().parents[2] / 'web'

if WEB_DIR.is_dir():
    app.mount('/assets', StaticFiles(directory=WEB_DIR / 'assets'), name='assets')
    app.mount('/prototype', StaticFiles(directory=WEB_DIR), name='prototype')

    @app.get('/')
    def index():
        return FileResponse(WEB_DIR / 'index.html')

    @app.get('/{full_path:path}')
    def spa_fallback(full_path: str):
        """SPA 兜底：非 /api 开头的路径一律回 index.html（前端路由）"""
        if full_path.startswith('api/'):
            raise HTTPException(404, 'not found')
        target = WEB_DIR / full_path
        if full_path and target.is_file():
            return FileResponse(target)
        return FileResponse(WEB_DIR / 'index.html')
