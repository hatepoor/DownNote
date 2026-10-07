"""主智能体测试：工具循环、回顾派发（非阻塞）、后台双写与上下文注入。

对应模块：docx/v0.1.0/modules/08-对话Agent.md
"""

import time

from langchain_core.messages import AIMessage

import helpers
from helpers import FakeToolModel, toolCall

from down_note.agent import llm as agentLlm
from down_note.agent import mainAgent
from down_note.agent.checkpointer import getCheckpointer
from down_note.config import ModelServiceConfig
from down_note.db import database, models

CFG = ModelServiceConfig(baseUrl="http://model.local/v1", apiKey="sk-test", modelName="test-model")

THREAD = {"configurable": {"thread_id": "s1"}}


def test_timeToolLoop(dataDir, monkeypatch):
    model = FakeToolModel(messages=iter([
        toolCall("getCurrentTime", {}, "call-1"),
        AIMessage(content="时间我知道啦。"),
    ]))
    monkeypatch.setattr(agentLlm, "buildChatModel", lambda cfg, **kw: model)

    graph = mainAgent.buildMainAgent(CFG, getCheckpointer(), "s1")
    result = graph.invoke({"messages": [AIMessage(content="现在几点了")]}, THREAD)

    assert agentLlm.messageText(result["messages"][-1]) == "时间我知道啦。"
    # 工具真实执行过：状态里存在 ToolMessage
    assert any(m.type == "tool" for m in result["messages"])


def test_diaryToolLoop(dataDir, dbFile, monkeypatch):
    with database.getDb() as db:
        models.addEntry(db, "试用记录页，心里松了一点。", None, "2026-10-05T21:08:00")

    model = FakeToolModel(messages=iter([
        toolCall("queryDiaries", {"date": "2026-10-05"}, "call-1"),
        AIMessage(content="翻到了，昨天你写了试用记录页的事。"),
    ]))
    monkeypatch.setattr(agentLlm, "buildChatModel", lambda cfg, **kw: model)

    graph = mainAgent.buildMainAgent(CFG, getCheckpointer(), "s1")
    result = graph.invoke({"messages": [AIMessage(content="我昨天写了什么")]}, THREAD)

    assert agentLlm.messageText(result["messages"][-1]) == "翻到了，昨天你写了试用记录页的事。"
    toolMessages = [m for m in result["messages"] if m.type == "tool"]
    assert toolMessages and "试用记录页" in toolMessages[0].content


def test_dispatchRecallRunsInBackgroundAndInjects(dataDir, dbFile, monkeypatch):
    with database.getDb() as db:
        models.upsertChatSession(db, "s1", "2026-10-05T21:00:00")

    model = FakeToolModel(messages=iter([
        toolCall("dispatchRecall", {"userQuestion": "还记得我前天说的吗"}, "call-1"),
        AIMessage(content="我翻翻前天的记录哈，稍等一下。"),
    ]))
    monkeypatch.setattr(agentLlm, "buildChatModel", lambda cfg, **kw: model)
    monkeypatch.setattr(mainAgent.recallAgent, "runRecall", lambda cfg, q: "前天你提到了面试的事。")

    graph = mainAgent.buildMainAgent(CFG, getCheckpointer(), "s1")
    result = graph.invoke(
            {"messages": [AIMessage(content="还记得我前天说的吗")]},
            THREAD,
        )
    # 派发即返：主回合不等回顾
    assert agentLlm.messageText(result["messages"][-1]) == "我翻翻前天的记录哈，稍等一下。"

    # 等后台线程完成双写（messages 表 + checkpointer 注入）
    deadline = time.time() + 3
    injected = False
    while time.time() < deadline:
        state = graph.get_state(THREAD)
        last = agentLlm.messageText(state.values["messages"][-1])
        with database.getDb() as db:
            rows = models.listMessages(db, "s1")
        hasMessage = any(m.role == "assistant" and "面试" in m.content for m in rows)
        injected = "面试" in last and hasMessage
        if injected:
            break
        time.sleep(0.05)
    assert injected


def test_recallFailureWritesFallback(dataDir, dbFile, monkeypatch):
    with database.getDb() as db:
        models.upsertChatSession(db, "s1", "2026-10-05T21:00:00")

    model = FakeToolModel(messages=iter([
        toolCall("dispatchRecall", {"userQuestion": "还记得吗"}, "call-1"),
        AIMessage(content="我翻翻。"),
    ]))
    monkeypatch.setattr(agentLlm, "buildChatModel", lambda cfg, **kw: model)

    def _fail(cfg, question):
        raise agentLlm.ModelUnavailableError("服务不可用")

    monkeypatch.setattr(mainAgent.recallAgent, "runRecall", _fail)

    graph = mainAgent.buildMainAgent(CFG, getCheckpointer(), "s1")
    graph.invoke({"messages": [AIMessage(content="还记得吗")]}, THREAD)

    deadline = time.time() + 3
    found = False
    while time.time() < deadline:
        with database.getDb() as db:
            rows = models.listMessages(db, "s1")
        found = any("暂时翻不了" in m.content for m in rows)
        if found:
            break
        time.sleep(0.05)
    assert found
