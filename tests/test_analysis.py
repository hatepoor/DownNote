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


def test_claimIsMutuallyExclusive(dbFile):
    """认领互斥：同一条目第二次认领必须失败——手动刷新与兜底扫描不会重复分析。"""
    with database.getDb(dbFile) as db:
        entryId = models.addEntry(db, "一条待分析", None, "2026-10-05T21:00:00")
    with database.getDb(dbFile) as db:
        assert models.claimForAnalysis(db, entryId) is True
    with database.getDb(dbFile) as db:
        assert models.claimForAnalysis(db, entryId) is False


def test_analysisDiscardsResultWhenContentChanged(dbFile, monkeypatch):
    """分析期间正文被改：丢弃本次结果、状态回 pending、不写心情记录（旧正文不覆盖新正文）。"""
    with database.getDb(dbFile) as db:
        models.setSetting(db, "base_url", "http://model.local/v1")
        models.setSetting(db, "model_name", "test-model")
        entryId = models.addEntry(db, "原始正文", None, "2026-10-05T21:00:00")

    def _fakeInvokeModel(cfg, messages, **kwargs):
        with database.getDb(dbFile) as inner:
            models.updateEntryContent(inner, entryId, "分析途中被改的正文")
        return _goodJson()

    monkeypatch.setattr(agentLlm, "invokeModel", _fakeInvokeModel)
    assert analysis.analyzeEntry(entryId) is None
    with database.getDb(dbFile) as db:
        assert models.getEntry(db, entryId).analyze_state == models.ANALYZE_PENDING
        assert models.getMoodByEntry(db, entryId) is None


def test_analysisMarksFailedWhenBudgetExhausted(dbFile, monkeypatch):
    """总预算耗尽：落 failed（界面显示「分析失败」+ 刷新；兜底扫描随后重试）。"""
    with database.getDb(dbFile) as db:
        models.setSetting(db, "base_url", "http://model.local/v1")
        models.setSetting(db, "model_name", "test-model")
        entryId = models.addEntry(db, "预算耗尽的条目", None, "2026-10-05T21:00:00")
    monkeypatch.setattr(analysis, "ANALYSIS_TOTAL_BUDGET_SECONDS", -1.0)
    assert analysis.analyzeEntry(entryId) is None
    with database.getDb(dbFile) as db:
        assert models.getEntry(db, entryId).analyze_state == models.ANALYZE_FAILED


def test_editResetsStateSoReanalysisRuns(dbFile, monkeypatch):
    """编辑正文后必须回到待分析：否则新正文会被 done 状态卡住、永不重析。"""
    with database.getDb(dbFile) as db:
        entryId = models.addEntry(db, "旧正文", None, "2026-10-05T21:00:00")
        models.setAnalyzeState(db, entryId, models.ANALYZE_DONE)
    with database.getDb(dbFile) as db:
        models.updateEntryContent(db, entryId, "新正文")
        assert models.getEntry(db, entryId).analyze_state == models.ANALYZE_PENDING
