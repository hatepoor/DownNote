"""系统通知接口测试：自测入口按真实链路推事件、默认落到最近活跃会话、无会话不报错。

对应模块：docx/v0.2.0/modules/01-托盘常驻与系统通知.md
"""

import asyncio
import json

from fastapi.testclient import TestClient

from down_note.api import notify as notifyApi
from down_note.app import createApp
from down_note.core.events import NOTIFY_EVENTS_CHANNEL, broker
from down_note.db import database, models


def _client() -> TestClient:
    return TestClient(createApp())


def test_notifyTestWithoutSession(dbFile):
    """一条会话都没有：接口仍 200，sessionId 为空串（前端此时不绑定会话）。"""
    resp = _client().post("/api/notify/test", json={})
    assert resp.status_code == 200
    assert resp.json() == {"status": "sent", "sessionId": ""}


def test_notifyTestFallsToRecentSession(dbFile):
    """默认落到最近活跃会话；也支持显式指定。"""
    with database.getDb() as db:
        models.upsertChatSession(db, "old-session", "2026-10-01T10:00:00")
        models.upsertChatSession(db, "new-session", "2026-10-12T21:00:00")
    client = _client()
    assert client.post("/api/notify/test", json={}).json()["sessionId"] == "new-session"
    explicit = client.post("/api/notify/test", json={"sessionId": "old-session"}).json()
    assert explicit["sessionId"] == "old-session"


def test_notifyTestPublishes(dbFile, monkeypatch):
    """自测入口确实推了事件，而不是只返回 200。"""
    calls: list[tuple[str, str, str]] = []
    monkeypatch.setattr(
            notifyApi,
            "notifyProactiveMessage",
            lambda sessionId, title, body: calls.append((sessionId, title, body)),
        )
    _client().post("/api/notify/test", json={"sessionId": "s1"})
    assert calls == [("s1", notifyApi.TEST_TITLE, notifyApi.TEST_BODY)]


def test_notifyEventStreamPushesNotification(dataDir, dbFile):
    """通知通道：发布事件 → 事件流产出对应 SSE 帧（前端据此弹系统通知）。"""

    async def _drive() -> dict:
        stream = notifyApi.notifyEventStream()
        pending = asyncio.ensure_future(stream.__anext__())
        await asyncio.sleep(0)  # 让生成器先完成订阅
        broker.publish(
                NOTIFY_EVENTS_CHANNEL,
                {"type": "notify", "sessionId": "s1", "title": "低落日记", "body": "在忙吗"},
            )
        frame = await asyncio.wait_for(pending, timeout=1)
        await stream.aclose()
        return json.loads(frame[len("data: "):].strip())

    assert asyncio.run(_drive()) == {
        "type": "notify",
        "sessionId": "s1",
        "title": "低落日记",
        "body": "在忙吗",
    }
