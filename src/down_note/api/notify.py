"""系统通知接口：后端决定主动开口 → 推通知事件 → 前端弹系统通知、点击回到对应会话。

通知由前端发（Tauri 通知插件在 WebView 侧），后端只负责"该开口了"这件事：
05-主动陪伴引擎落库后调用 notifyProactiveMessage（core/events.py），事件经本模块的 SSE
通道送到前端；/api/notify/test 是开发自测入口（托盘「测试通知」项打它）。
对应开发文档：docx/v0.2.0/modules/01-托盘常驻与系统通知.md
"""

import asyncio

from fastapi import APIRouter
from fastapi.responses import StreamingResponse
from pydantic import BaseModel

from down_note.core.events import NOTIFY_EVENTS_CHANNEL, broker, notifyProactiveMessage, sseFrame
from down_note.db import database, models

router = APIRouter(prefix="/api/notify", tags=["notify"])

TEST_TITLE = "低落日记"
TEST_BODY = "（测试）在忙吗，我随口说一句"


class NotifyTestRequest(BaseModel):
    sessionId: str | None = None


async def notifyEventStream():
    """通知常驻事件流（独立生成器便于直接测试：TestClient 会缓冲完整响应，测不了无限流）。"""
    queue = broker.subscribe(NOTIFY_EVENTS_CHANNEL)
    try:
        while True:
            try:
                event = await asyncio.wait_for(queue.get(), timeout=15)
                yield sseFrame(event)
            except asyncio.TimeoutError:
                yield ": keepalive\n\n"
    finally:
        broker.unsubscribe(NOTIFY_EVENTS_CHANNEL, queue)


@router.get("/events")
async def notifyEvents() -> StreamingResponse:
    """通知通道：主动开口时推 {type, sessionId, title, body}（15 秒保活，与记忆通道同款）。"""
    return StreamingResponse(notifyEventStream(), media_type="text/event-stream")


@router.post("/test")
def notifyTest(body: NotifyTestRequest) -> dict[str, str]:
    """开发自测：走真实链路推一条通知；不指定会话时落到最近活跃会话。"""
    sessionId = body.sessionId
    if sessionId is None:
        with database.getDb() as db:
            sessions = models.listRecentSessions(db, limit=1)
        sessionId = sessions[0].session_id if sessions else ""
    notifyProactiveMessage(sessionId, TEST_TITLE, TEST_BODY)
    return {"status": "sent", "sessionId": sessionId}
