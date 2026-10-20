"""会话删除接口测试：三处级联清理、幂等、长期记忆不受影响。

对应模块：docx/v0.2.0/modules/03-会话删除.md
"""

from fastapi.testclient import TestClient

import helpers
from helpers import FakeToolModel, parseSseEvents

from down_note import config
from down_note.agent import context
from down_note.agent import llm as agentLlm
from down_note.agent import mainAgent
from down_note.agent.checkpointer import getCheckpointer
from down_note.agent.session import dropSession
from down_note.app import createApp
from down_note.db import database, models


def _configure(db):
    models.setSetting(db, "base_url", "http://model.local/v1")
    models.setSetting(db, "model_name", "test-model")


def _wakeSession(local: TestClient, monkeypatch) -> str:
    monkeypatch.setattr(
            agentLlm,
            "buildChatModel",
            lambda cfg, **kw: FakeToolModel(messages=iter([helpers.AIMessage(content="晚上好。")])),
        )
    with local.stream("POST", "/api/chat/wake") as res:
        return parseSseEvents(res.iter_lines())[0]["sessionId"]


def test_deleteRemovesMessagesSessionAndGraphState(dataDir, dbFile, monkeypatch):
    """删除后三处都空：会话行、消息、图状态；长期记忆逐条比对不变。"""
    with database.getDb() as db:
        _configure(db)
        memoryId = models.addLongTermMemory(db, "basic", "名字是阿澈", updatedBy="user")
    local = TestClient(createApp())
    sessionId = _wakeSession(local, monkeypatch)

    with database.getDb() as db:
        cfg = config.getModelServiceConfig(db)
    graph = mainAgent.buildMainAgent(cfg, getCheckpointer(), sessionId)
    assert graph.get_state({"configurable": {"thread_id": sessionId}}).values.get("messages")

    assert local.delete(f"/api/chat/sessions/{sessionId}").status_code == 204

    with database.getDb() as db:
        assert db.get(models.ChatSession, sessionId) is None
        assert models.listMessages(db, sessionId) == []
        kept = models.getLongTermMemory(db, memoryId)
        assert (kept.id, kept.content) == (memoryId, "名字是阿澈")
    assert local.get("/api/chat/sessions").json() == []
    assert not graph.get_state({"configurable": {"thread_id": sessionId}}).values.get("messages")


def test_deleteIsIdempotent(dataDir, dbFile):
    """重复删除 / 删除不存在的会话：都 204，无副作用（前端失败重试安全）。"""
    local = TestClient(createApp())
    assert local.delete("/api/chat/sessions/nope").status_code == 204
    assert local.delete("/api/chat/sessions/nope").status_code == 204


def test_historyEmptyAfterDelete(dataDir, dbFile, monkeypatch):
    with database.getDb() as db:
        _configure(db)
    local = TestClient(createApp())
    sessionId = _wakeSession(local, monkeypatch)
    assert local.get(f"/api/chat/history?sessionId={sessionId}").json()
    assert local.delete(f"/api/chat/sessions/{sessionId}").status_code == 204
    assert local.get(f"/api/chat/history?sessionId={sessionId}").json() == []


def test_dropSessionClearsPromptBlocksAndIsIdempotent(dataDir, dbFile, monkeypatch):
    """dropSession 是删除的唯一入口：提示词快照一并失效，重复调用无副作用。"""
    with database.getDb() as db:
        _configure(db)
    local = TestClient(createApp())
    sessionId = _wakeSession(local, monkeypatch)
    assert sessionId in context._promptBlocks

    dropSession(sessionId)
    dropSession(sessionId)

    assert sessionId not in context._promptBlocks
    with database.getDb() as db:
        assert models.listMessages(db, sessionId) == []
        assert models.getSessionById(db, sessionId) is None
