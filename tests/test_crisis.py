"""危机判定测试——初筛必须全离线，复判用 mock 模型，资源加载与落库联动。

对应模块：docx/v0.1.0/modules/06-危机应对.md
"""

import httpx
import json
import pytest
from langchain_core.language_models import FakeListChatModel

from down_note import config
from down_note.agent import llm as agentLlm
from down_note.config import ModelServiceConfig
from down_note.core import analysis, crisis
from down_note.db import database, models

CFG = ModelServiceConfig(baseUrl="http://model.local/v1", apiKey="sk-test", modelName="test-model")

CRISIS_JSON_TRUE = '{"crisis": true, "reason": "本人意念"}'
CRISIS_JSON_FALSE = '{"crisis": false, "reason": "转述他人"}'


class _BrokenModel(FakeListChatModel):
    """invoke 即抛连接错误的假模型。"""

    def _call(self, messages, stop=None, run_manager=None, **kwargs):
        raise httpx.ConnectError("连接被拒")


def test_screenHitsVariousCategories():
    assert crisis.screen("最近总会想到自杀的事")
    assert crisis.screen("手臂上有自残的痕迹")
    assert crisis.screen("真的撑不下去了")
    assert crisis.screen("真的有点撑不住了")
    assert crisis.screen("扛不住了")
    assert crisis.screen("写了一封遗书")
    assert crisis.screen("I keep having suicide thoughts")
    assert crisis.screen("I want to die")


def test_screenCaseInsensitive():
    assert crisis.screen("Suicide is on my mind")
    assert crisis.screen("SELF HARM")


def test_screenMissesOrdinaryTexts():
    assert not crisis.screen("今天有点累但还好，下班吃了顿好的")
    assert not crisis.screen("普通的难过，睡一觉就好")
    assert not crisis.screen("")
    assert not crisis.screen("生活总有些不如意")


def test_assessTrueForPersonalIdeation(monkeypatch):
    monkeypatch.setattr(
            agentLlm,
            "buildChatModel",
            lambda cfg, **kw: FakeListChatModel(responses=[CRISIS_JSON_TRUE]),
        )
    assert crisis.assess("最近总会想到自杀的事", CFG) is True


def test_assessFalseForThirdPartyStory(monkeypatch):
    monkeypatch.setattr(
            agentLlm,
            "buildChatModel",
            lambda cfg, **kw: FakeListChatModel(responses=[CRISIS_JSON_FALSE]),
        )
    assert crisis.assess("新闻里那个孩子自杀了，好难受", CFG) is False


def test_assessFailsClosedToTrue(monkeypatch):
    # 复判不可用 → 保守标记危机（宁敏感勿遗漏，ADR-0003）
    monkeypatch.setattr(agentLlm, "buildChatModel", lambda cfg, **kw: _BrokenModel(responses=[]))
    assert crisis.assess("命中了词表但模型挂了", CFG) is True


def test_assessEntryTextSkipsModelWhenNoHit(monkeypatch):
    calls = 0

    def _fakeBuild(cfg, **kw):
        nonlocal calls
        calls += 1
        return FakeListChatModel(responses=[CRISIS_JSON_TRUE])

    monkeypatch.setattr(agentLlm, "buildChatModel", _fakeBuild)
    assert crisis.assessEntryText("平静的一天", CFG) is False
    assert calls == 0


def test_assessEntryTextTwoLevelHit(monkeypatch):
    monkeypatch.setattr(
            agentLlm,
            "buildChatModel",
            lambda cfg, **kw: FakeListChatModel(responses=[CRISIS_JSON_TRUE]),
        )
    assert crisis.assessEntryText("写好了遗书", CFG) is True


def test_loadHotlinesPackaged():
    resources = crisis.loadHotlines()
    assert len(resources) >= 1
    assert all(r["name"] and r["phone"] for r in resources)


def test_loadHotlinesUserOverride(dataDir):
    override = dataDir / crisis.RESOURCES_FILE_NAME
    override.write_text(
            json.dumps({"resources": [{"name": "本地热线", "region": "测试市", "phone": "0000", "note": ""}]}, ensure_ascii=False),
            encoding="utf-8",
        )
    resources = crisis.loadHotlines(dataDir)
    assert len(resources) == 1
    assert resources[0]["name"] == "本地热线"


def test_analysisMarksCrisisOnMood(dbFile, monkeypatch):
    # 全链路：条目含关键词 → 分析产出心情 → 复判确认 → moods.crisis = 1
    with database.getDb(dbFile) as db:
        models.setSetting(db, "base_url", "http://model.local/v1")
        models.setSetting(db, "model_name", "test-model")
        entryId = models.addEntry(db, "这几天总觉得撑不下去了", None, "2026-10-05T23:00:00")

    model = FakeListChatModel(
            responses=[
                json.dumps({"labels": ["绝望"], "intensity": 9, "summary": "撑不下去了"}, ensure_ascii=False),
                CRISIS_JSON_TRUE,
            ]
        )
    monkeypatch.setattr(agentLlm, "buildChatModel", lambda cfg, **kw: model)

    assert analysis.analyzeEntry(entryId) is not None
    with database.getDb(dbFile) as db:
        mood = models.getMoodByEntry(db, entryId)
        assert mood.crisis is True
