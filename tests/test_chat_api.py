"""对话接口测试：wake/turn SSE、危机轮、事件通道、历史与会话列表。

对应模块：docx/v0.1.0/modules/08-对话Agent.md
"""

import json
import threading
import time

from fastapi.testclient import TestClient
from langchain_core.messages import SystemMessage

import helpers
from helpers import FakeToolModel, parseSseEvents

from down_note import config
from down_note.db import database, models
from down_note.agent import llm as agentLlm
from down_note.agent import mainAgent
from down_note.agent.checkpointer import getCheckpointer
from down_note.app import createApp
from down_note.core.events import broker


def _configure(db):
    models.setSetting(db, "base_url", "http://model.local/v1")
    models.setSetting(db, "model_name", "test-model")


def _modelPool(*models_):
    """按 buildChatModel 调用顺序依次出队的模型池（耗尽后回退空模型并打印调用栈）。"""
    pool = list(models_)

    def factory(cfg, **kw):
        import traceback

        if pool:
            return pool.pop(0)
        stack = traceback.format_stack()
        print("=== buildChatModel 池耗尽，调用栈：")
        for line in stack[-8:-1]:
            print("   ", line.strip().splitlines()[0])
        return FakeToolModel(messages=iter([]))

    return factory


def test_wakeReturns409WhenNotConfigured(dataDir, dbFile):
    with TestClient(createApp()) as local:
        assert local.post("/api/chat/wake").status_code == 409


def test_turnReturns404ForUnknownSession(dataDir, dbFile):
    local = TestClient(createApp())
    res = local.post("/api/chat/messages", json={"sessionId": "nope", "content": "嗨"})
    assert res.status_code == 404


def test_wakeStreamsOpeningAndPersists(dataDir, dbFile, monkeypatch):
    with database.getDb() as db:
        _configure(db)
        entryId = models.addEntry(db, "今天有点低落", None, "2026-10-05T21:00:00")
        models.upsertMood(
                db,
                entryId=entryId,
                labels=["低落"],
                intensity=5,
                summary="测试",
                crisis=False,
                analyzedAt="2026-10-05T21:05:00",
                model="test",
            )
    monkeypatch.setattr(
            agentLlm,
            "buildChatModel",
            _modelPool(FakeToolModel(messages=iter([helpers.AIMessage(content="晚上好，今天过得怎么样？")]))),
        )
    local = TestClient(createApp())

    with local.stream("POST", "/api/chat/wake") as res:
        assert res.status_code == 200
        events = parseSseEvents(res.iter_lines())

    assert events[0]["type"] == "start"
    assert events[0]["wakeNote"] is True
    assert events[-1]["type"] == "done"
    sessionId = events[0]["sessionId"]
    assert any(e["type"] == "delta" for e in events)

    with database.getDb() as db:
        rows = models.listMessages(db, sessionId)
    assert len(rows) == 1
    assert rows[0].role == "assistant"
    assert db.get(models.ChatSession, sessionId) is not None


def test_turnStreamsAndHistoryReadback(dataDir, dbFile, monkeypatch):
    with database.getDb() as db:
        _configure(db)
    monkeypatch.setattr(
            agentLlm,
            "buildChatModel",
            _modelPool(
                FakeToolModel(messages=iter([helpers.AIMessage(content="晚上好。")])),
                FakeToolModel(messages=iter([helpers.AIMessage(content="我在呢。")])),
            ),
        )
    local = TestClient(createApp())

    with local.stream("POST", "/api/chat/wake") as res:
        sessionId = parseSseEvents(res.iter_lines())[0]["sessionId"]

    with local.stream(
            "POST",
            "/api/chat/messages",
            json={"sessionId": sessionId, "content": "在的"},
        ) as res:
        events = parseSseEvents(res.iter_lines())
    assert [e["text"] for e in events if e["type"] == "delta"] == ["我在呢。"]

    history = local.get(f"/api/chat/history?sessionId={sessionId}").json()
    assert [m["role"] for m in history] == ["assistant", "user", "assistant"]

    # afterId 增量过滤
    later = local.get(f"/api/chat/history?sessionId={sessionId}&afterId={history[0]['id']}").json()
    assert [m["role"] for m in later] == ["user", "assistant"]


def test_crisisTurnStreamsGuidelinesAndMeta(dataDir, dbFile, monkeypatch):
    with database.getDb() as db:
        _configure(db)
    crisisJson = json.dumps({"crisis": True, "reason": "本人意念"}, ensure_ascii=False)
    monkeypatch.setattr(
            agentLlm,
            "buildChatModel",
            _modelPool(
                FakeToolModel(messages=iter([helpers.AIMessage(content="晚上好。")])),  # wake
                FakeToolModel(messages=iter([helpers.AIMessage(content=crisisJson)])),  # 复判
                FakeToolModel(  # 危机应答流
                    messages=iter([helpers.AIMessage(content="我在这里陪着你。此刻很难的话，可以拨打 12356。")])
                ),
                FakeToolModel(messages=iter([])),  # update_state 重建主图（不触发生成）
            ),
        )
    local = TestClient(createApp())
    with local.stream("POST", "/api/chat/wake") as res:
        sessionId = parseSseEvents(res.iter_lines())[0]["sessionId"]

    with local.stream(
            "POST",
            "/api/chat/messages",
            json={"sessionId": sessionId, "content": "最近总觉得撑不下去了"},
        ) as res:
        events = parseSseEvents(res.iter_lines())

    meta = next(e for e in events if e["type"] == "meta")
    assert meta["crisis"] is True
    assert len(meta["hotlines"]) >= 1
    assert any(e["type"] == "delta" for e in events)

    # 危机回合注入主图上下文（下轮它记得）
    with database.getDb() as db:
        cfg = config.getModelServiceConfig(db)
    graph = mainAgent.buildMainAgent(cfg, getCheckpointer(), sessionId)
    state = graph.get_state({"configurable": {"thread_id": sessionId}})
    contents = [agentLlm.messageText(m) for m in state.values["messages"]]
    assert any("我在这里陪着你" in c for c in contents)


def test_eventsChannelPushesRecall(dataDir, dbFile):
    # TestClient 的 ASGI 传输会缓冲完整响应，无法消费无限流——直接驱动生成器测
    import asyncio

    from down_note.api.chat import chatEventStream

    sessionId = "s-events"

    async def scenario():
        gen = chatEventStream(sessionId)
        task = asyncio.create_task(gen.__anext__())  # 等待首帧（订阅已生效）
        await asyncio.sleep(0.1)
        broker.publish(
                sessionId,
                {"type": "recall", "message": {"role": "assistant", "content": "回忆到了", "createdAt": "2026"}},
            )
        first = await asyncio.wait_for(task, timeout=3)
        assert '"type": "recall"' in first or '"type":"recall"' in first
        await gen.aclose()

    asyncio.run(scenario())


def test_sessionsListHasPreview(dataDir, dbFile, monkeypatch):
    with database.getDb() as db:
        _configure(db)
    monkeypatch.setattr(
            agentLlm,
            "buildChatModel",
            _modelPool(
                FakeToolModel(messages=iter([helpers.AIMessage(content="晚上好。")])),
                FakeToolModel(messages=iter([helpers.AIMessage(content="我在呢。")])),
            ),
        )
    local = TestClient(createApp())
    with local.stream("POST", "/api/chat/wake") as res:
        sessionId = parseSseEvents(res.iter_lines())[0]["sessionId"]
    local.post("/api/chat/messages", json={"sessionId": sessionId, "content": "今天想聊聊工作的事"})

    sessions = local.get("/api/chat/sessions").json()
    assert len(sessions) == 1
    assert sessions[0]["sessionId"] == sessionId
    assert "工作" in sessions[0]["preview"]


def test_memoryEditMidSessionRefreshesSystemPrompt(dataDir, dbFile, monkeypatch):
    """① 唤醒之后写的记忆，下一个回合即进入系统提示词（原位替换旧快照，且不重复堆积）。"""
    with database.getDb() as db:
        _configure(db)
    # 池按构建顺序出队：wake → 校验构建 → 回合1 → 校验构建 → 回合2 → 校验构建
    # （校验构建的模型从不被调用，给空迭代器即可）
    monkeypatch.setattr(
            agentLlm,
            "buildChatModel",
            _modelPool(
                FakeToolModel(messages=iter([helpers.AIMessage(content="晚上好。")])),
                FakeToolModel(messages=iter([])),
                FakeToolModel(messages=iter([helpers.AIMessage(content="我记得的。")])),
                FakeToolModel(messages=iter([])),
                FakeToolModel(messages=iter([helpers.AIMessage(content="还在。")])),
                FakeToolModel(messages=iter([])),
            ),
        )
    local = TestClient(createApp())
    with local.stream("POST", "/api/chat/wake") as res:
        sessionId = parseSseEvents(res.iter_lines())[0]["sessionId"]

    def systemMessages() -> list:
        with database.getDb() as db:
            cfg = config.getModelServiceConfig(db)
        graph = mainAgent.buildMainAgent(cfg, getCheckpointer(), sessionId)
        state = graph.get_state({"configurable": {"thread_id": sessionId}})
        return [
                message
                for message in state.values["messages"]
                if isinstance(message, SystemMessage)
            ]

    # 唤醒时快照里没有名字
    initial = systemMessages()
    assert len(initial) == 1
    assert "张飞航" not in initial[0].content

    # 用户在记忆页写下名字，然后在同一个会话里发问
    with database.getDb() as db:
        models.addLongTermMemory(db, "basic", "名字是张飞航", updatedBy="user")
    with local.stream(
            "POST",
            "/api/chat/messages",
            json={"sessionId": sessionId, "content": "你记得吗"},
        ) as res:
        parseSseEvents(res.iter_lines())

    # 旧快照被替换：仍然只有一条系统消息，且带上了新记忆
    messages = systemMessages()
    assert len(messages) == 1
    assert "张飞航" in messages[0].content

    # 无变化的下一个回合：系统消息保持原样（稳态不打扰）
    with local.stream(
            "POST",
            "/api/chat/messages",
            json={"sessionId": sessionId, "content": "在吗"},
        ) as res:
        parseSseEvents(res.iter_lines())
    messages = systemMessages()
    assert len(messages) == 1
    assert "张飞航" in messages[0].content
