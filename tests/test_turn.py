"""主图回合 module 测试：流过滤、增量顺序、persist 开关、异常不落库。

不建真图：在 buildMainAgent / refreshSystemPrompt / messageText 三个 seam 上注入
假 adapter，验证的是 runAgentTurn 这个 interface 的契约，而不是 LangGraph 的内部形状。
"""

import pytest

from down_note.agent import turn
from down_note.config import ModelServiceConfig
from down_note.db import database, models

CFG = ModelServiceConfig(baseUrl="http://model.local/v1", apiKey="sk-test", modelName="test-model")


class FakeGraph:
    def __init__(self, chunks, error=None):
        self.chunks = chunks
        self.error = error

    def stream(self, inputs, config, stream_mode):
        for chunk, meta in self.chunks:
            yield chunk, meta
        if self.error is not None:
            raise self.error


def _useTurn(monkeypatch, chunks, error=None) -> None:
    """把回合 module 的依赖换成假 adapter：图、提示词刷新、chunk 取文本。"""
    monkeypatch.setattr(
            turn.mainAgent,
            "buildMainAgent",
            lambda *args, **kwargs: FakeGraph(chunks, error),
        )
    monkeypatch.setattr(turn, "refreshSystemPrompt", lambda *args, **kwargs: None)
    monkeypatch.setattr(turn.llm, "messageText", lambda chunk: chunk)


def _prepareSession(sessionId: str = "s-turn") -> None:
    with database.getDb() as db:
        models.upsertChatSession(db, sessionId, "2026-10-20T12:00:00")


def _messages(sessionId: str = "s-turn") -> list:
    with database.getDb() as db:
        return models.listMessages(db, sessionId)


def test_streamsOnlyAgentNodesInOrderAndPersists(dataDir, dbFile, monkeypatch):
    """只转发 agent 节点的非空增量，顺序不变；结束后落一条 assistant 消息。"""
    _useTurn(
            monkeypatch,
            [
                    ("你好", {"langgraph_node": "agent"}),
                    ("工具", {"langgraph_node": "tools"}),
                    ("，", {"langgraph_node": "agent"}),
                    ("", {"langgraph_node": "agent"}),
                    ("结束", {"langgraph_node": "agent"}),
                ],
        )
    _prepareSession()

    assert list(turn.runAgentTurn(CFG, "s-turn", [])) == ["你好", "，", "结束"]

    messages = _messages()
    assert [(m.role, m.content) for m in messages] == [("assistant", "你好，结束")]


def test_persistFalseLeavesMessagesForCaller(dataDir, dbFile, monkeypatch):
    """persist=False：只流式、不落库——主动开口要在自己的检查之后落。"""
    _useTurn(monkeypatch, [("在忙吗", {"langgraph_node": "agent"})])
    _prepareSession()

    assert list(turn.runAgentTurn(CFG, "s-turn", [], persist=False)) == ["在忙吗"]
    assert _messages() == []


def test_errorMidStreamPropagatesAndDoesNotPersist(dataDir, dbFile, monkeypatch):
    """流式途中的异常原样抛出，已完成的部分不落库（避免半截回复进历史）。"""
    _useTurn(
            monkeypatch,
            [("半句", {"langgraph_node": "agent"})],
            error=RuntimeError("boom"),
        )
    _prepareSession()

    with pytest.raises(RuntimeError):
        list(turn.runAgentTurn(CFG, "s-turn", []))
    assert _messages() == []
