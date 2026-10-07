"""FastAPI 应用工厂：注册 /api 路由；启动时建表；生产模式挂载 frontend/dist 静态文件。

对应开发文档：docx/v0.1.0/modules/01-项目骨架.md、02-数据库与配置.md
"""

from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles

from down_note import config, scheduler
from down_note.api.chat import router as chatRouter
from down_note.api.diaries import router as diariesRouter
from down_note.api.entries import router as entriesRouter
from down_note.api.memories import router as memoriesRouter
from down_note.api.settings import router as settingsRouter
from down_note.db import database


@asynccontextmanager
async def lifespan(app: FastAPI):
    # 应用启动即加载 .env、建表、起兜底调度——真实运行时的统一接线入口
    config.loadEnv()
    database.ensureSchema()
    scheduler.startScheduler()
    yield


def createApp() -> FastAPI:
    app = FastAPI(title="低落日记", version="0.1.0", lifespan=lifespan)

    # include_router 是 FastAPI 的 API，保持库的命名（编码规范强制例外）
    app.include_router(settingsRouter)
    app.include_router(entriesRouter)
    app.include_router(diariesRouter)
    app.include_router(memoriesRouter)
    app.include_router(chatRouter)

    @app.get("/api/health")
    def health() -> dict[str, str]:
        return {"status": "ok"}

    # 生产模式由后端伺服前端静态文件；dist 不存在（dev 模式）时跳过，页面走 Vite 开发服务器
    frontendDist = config.getBundledRoot() / "frontend" / "dist"
    if frontendDist.exists():
        app.mount("/", StaticFiles(directory=frontendDist, html=True), name="frontend")

    return app
