"""分析管线测试（mock 模型）。

覆盖：正常落库、非法 JSON 重试一次、两次失败静默放弃、未配置跳过、
代码围栏剥离、已分析条目幂等。
对应模块：docx/v0.1.0/modules/05-分析管线.md
"""

import json

import pytest
from langchain_core.language_models import FakeListChatModel

from down_note.agent import llm as agentLlm
from down_note.core import analysis
from down_note.db import database, models


def _goodJson():
    return json.dumps({"labels": ["低落"], "intensity": 6, "summary": "测试摘要"}, ensure_ascii=False)


@pytest.fixture()
def entryId(dbFile):
    # 配置模型（分析入口有降级检查，未配置会在构造消息前直接跳过）
    with database.getDb(dbFile) as db:
        models.setSetting(db, "base_url", "http://model.local/v1")
        models.setSetting(db, "model_name", "test-model")
        return models.addEntry(db, "今天有点低落", None, "2026-10-05T21:00:00")


def test_analyzeNormal(entryId, dbFile, monkeypatch):
    monkeypatch.setattr(
            agentLlm,
            "buildChatModel",
            lambda cfg, **kw: FakeListChatModel(responses=[_goodJson()]),
        )
    result = analysis.analyzeEntry(entryId)
    assert result is not None
    assert result.labels == ["低落"]

    with database.getDb(dbFile) as db:
        assert models.getEntry(db, entryId).analyzed is True
        mood = models.getMoodByEntry(db, entryId)
        assert mood.intensity == 6
        assert mood.summary == "测试摘要"


def test_analyzeRetriesOnBadJson(entryId, monkeypatch):
    model = FakeListChatModel(responses=["我想想……这不是 JSON", _goodJson()])
    monkeypatch.setattr(agentLlm, "buildChatModel", lambda cfg, **kw: model)
    assert analysis.analyzeEntry(entryId) is not None


def test_analyzeGivesUpAfterTwoBadOutputs(entryId, dbFile, monkeypatch):
    monkeypatch.setattr(
            agentLlm,
            "buildChatModel",
            lambda cfg, **kw: FakeListChatModel(responses=["坏输出一", "坏输出二"]),
        )
    assert analysis.analyzeEntry(entryId) is None
    with database.getDb(dbFile) as db:
        assert models.getEntry(db, entryId).analyzed is False
        assert models.getMoodByEntry(db, entryId) is None


def test_analyzeSkipsWhenNotConfigured(entryId, dbFile):
    # 显式清空配置 → 降级 → 静默跳过
    with database.getDb(dbFile) as db:
        models.setSetting(db, "base_url", "")
    assert analysis.analyzeEntry(entryId) is None
    with database.getDb(dbFile) as db:
        assert models.getEntry(db, entryId).analyzed is False


def test_analyzeStripsCodeFence(entryId, monkeypatch):
    fenced = "```json\n" + _goodJson() + "\n```"
    monkeypatch.setattr(
            agentLlm,
            "buildChatModel",
            lambda cfg, **kw: FakeListChatModel(responses=[fenced]),
        )
    assert analysis.analyzeEntry(entryId) is not None


def test_analyzeSkipsAlreadyAnalyzed(entryId, dbFile, monkeypatch):
    with database.getDb(dbFile) as db:
        models.markEntryAnalyzed(db, entryId)

    calls = 0

    def _fakeBuild(cfg, **kw):
        nonlocal calls
        calls += 1
        return FakeListChatModel(responses=[])

    monkeypatch.setattr(agentLlm, "buildChatModel", _fakeBuild)
    assert analysis.analyzeEntry(entryId) is None
    assert calls == 0
