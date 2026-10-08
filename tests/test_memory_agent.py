"""记忆管理子智能体测试：mock 模型（带 tool_calls）驱动真实 LangGraph 图与工具。

覆盖：工具调用新增落库、无操作路径、调度器联动（维护标记与二跑不再命中）、工具侧变更通知。
对应模块：docx/v0.1.0/modules/07-长期记忆.md、docx/v0.1.2/modules/10-记忆即时可见.md
"""

from langchain_core.language_models import GenericFakeChatModel
from langchain_core.messages import AIMessage

from down_note.agent import llm as agentLlm
from down_note.agent import memoryAgent
from down_note.agent.tools.memory import add as memoryAddTool
from down_note.agent.tools.memory import delete as memoryDeleteTool
from down_note.agent.tools.memory import update as memoryUpdateTool
from down_note.config import ModelServiceConfig
from down_note.db import database, models
from down_note import scheduler

CFG = ModelServiceConfig(baseUrl="http://model.local/v1", apiKey="sk-test", modelName="test-model")


class _FakeToolModel(GenericFakeChatModel):
    """GenericFakeChatModel 不实现 bind_tools；测试用直接返回自身。"""

    def bind_tools(self, tools, **kwargs):
        return self


def _toolCallMessage(name: str, args: dict, callId: str) -> AIMessage:
    return AIMessage(
            content="",
            tool_calls=[{"name": name, "args": args, "id": callId, "type": "tool_call"}],
        )


def test_maintenanceAddsMemoryViaToolCall(dbFile, monkeypatch):
    model = _FakeToolModel(
            messages=iter([
                _toolCallMessage("addMemory", {"category": "basic", "content": "用户叫林晓"}, "call-1"),
                AIMessage(content="新增了一条基本信息。"),
            ])
        )
    monkeypatch.setattr(agentLlm, "buildChatModel", lambda cfg, **kw: model)

    reply = memoryAgent.runMemoryMaintenance(CFG, transcript="用户：我叫林晓", memoriesText="", moodsText="")

    assert "基本信息" in reply
    with database.getDb(dbFile) as db:
        memories = models.listLongTermMemories(db)
    assert len(memories) == 1
    assert memories[0].category == "basic"
    assert memories[0].content == "用户叫林晓"
    assert memories[0].updated_by == "agent"


def test_maintenanceNoOpKeepsMemoryEmpty(dbFile, monkeypatch):
    model = _FakeToolModel(messages=iter([AIMessage(content="无需更新——没有值得记录的变化。")]))
    monkeypatch.setattr(agentLlm, "buildChatModel", lambda cfg, **kw: model)

    reply = memoryAgent.runMemoryMaintenance(CFG, transcript="用户：今天有点累", memoriesText="", moodsText="")

    assert "无需更新" in reply
    with database.getDb(dbFile) as db:
        assert models.listLongTermMemories(db) == []


def test_schedulerMaintainsOnlySessionsWithNewMessages(dbFile, monkeypatch):
    with database.getDb(dbFile) as db:
        models.setSetting(db, "base_url", "http://model.local/v1")
        models.setSetting(db, "model_name", "test-model")
        models.upsertChatSession(db, "s1", "2026-10-05T21:00:00")
        models.addMessage(db, "s1", "user", "我叫林晓", "2026-10-05T21:00:10")
        models.upsertChatSession(db, "s2", "2026-10-05T20:00:00")
        models.markSessionMaintained(db, "s2", "2026-10-05T20:30:00")  # s2 无新消息

    ran = []

    def _fakeRun(cfg, transcript, memoriesText, moodsText):
        ran.append(transcript)
        return "无需更新"

    monkeypatch.setattr(memoryAgent, "runMemoryMaintenance", _fakeRun)
    scheduler.maintainMemories()

    assert len(ran) == 1
    assert "林晓" in ran[0]
    with database.getDb(dbFile) as db:
        assert db.get(models.ChatSession, "s1").memory_maintained_at is not None

    # 二跑：无新消息的会话不再触发
    scheduler.maintainMemories()
    assert len(ran) == 1


def test_schedulerSkipsWhenNotConfigured(dbFile, monkeypatch):
    with database.getDb(dbFile) as db:
        models.upsertChatSession(db, "s1", "2026-10-05T21:00:00")
        models.addMessage(db, "s1", "user", "你好", "2026-10-05T21:00:10")

    ran = []
    monkeypatch.setattr(
            memoryAgent,
            "runMemoryMaintenance",
            lambda cfg, t, m, md: ran.append(t) or "x",
        )
    scheduler.maintainMemories()
    assert ran == []  # 降级（无配置）整体跳过


def test_memoryToolsNotifyFrontend(dbFile, monkeypatch):
    """三个记忆工具落库成功后都通知前端——对话 / 记忆维护 / 日整合共用这套工具。"""
    calls: list[str] = []
    for module in (memoryAddTool, memoryUpdateTool, memoryDeleteTool):
        monkeypatch.setattr(module, "notifyMemoryChanged", lambda: calls.append("memory"))

    added = memoryAddTool.addMemory.invoke({"category": "psych", "content": "喜欢跑步"})
    assert added.startswith("已新增记忆")
    assert memoryUpdateTool.updateMemory.invoke({"memoryId": 1, "content": "平时喜欢跑步"}) == "已更新记忆 #1"
    assert memoryDeleteTool.deleteMemory.invoke({"memoryId": 1}) == "已删除记忆 #1"
    assert calls == ["memory", "memory", "memory"]

    # 失败路径（编号不存在）不通知
    calls.clear()
    assert "不存在" in memoryUpdateTool.updateMemory.invoke({"memoryId": 999, "content": "x"})
    assert "不存在" in memoryDeleteTool.deleteMemory.invoke({"memoryId": 999})
    assert calls == []
