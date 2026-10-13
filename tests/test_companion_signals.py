"""信号触发（v0.3.0 02）：连续低落/强度突变判定、按类型独立冷却、巡检提前开口。

隔离由 conftest 的 isolateDataDir + dbFile 保证；种子用无参 getDb()。
"""
from datetime import datetime

import pytest

from down_note.core import signals
from down_note.db import database, models


@pytest.fixture()
def db_path(dbFile):  # conftest dbFile：隔离库已建表
    return dbFile


def _mood(db, day: str, labels, intensity: int):
    entryId = models.addEntry(db, f"{day} 的日记", None, f"{day}T20:00:00")
    models.upsertMood(db, entryId=entryId, labels=labels, intensity=intensity,
                      summary="s", crisis=False, analyzedAt=f"{day}T20:00:01", model="m")
    return entryId


def test_no_signal_when_calm(db_path):
    with database.getDb() as db:
        _mood(db, "2026-10-12", ["平静"], 3)
        _mood(db, "2026-10-13", ["平静"], 3)
        assert signals.detectSignal(db, datetime(2026, 10, 13, 21, 0)) is None


def test_consecutive_low_triggers(db_path):
    with database.getDb() as db:
        _mood(db, "2026-10-12", ["低落"], 6)
        _mood(db, "2026-10-13", ["低落"], 7)
        hit = signals.detectSignal(db, datetime(2026, 10, 13, 21, 0))
    assert hit is not None and hit.kind == "low"


def test_consecutive_low_below_threshold_no_trigger(db_path):
    with database.getDb() as db:
        _mood(db, "2026-10-12", ["低落"], 3)  # 强度不足
        _mood(db, "2026-10-13", ["低落"], 4)
        assert signals.detectSignal(db, datetime(2026, 10, 13, 21, 0)) is None


def test_single_low_day_no_trigger(db_path):
    with database.getDb() as db:
        _mood(db, "2026-10-13", ["低落"], 8)  # 只有一天
        assert signals.detectSignal(db, datetime(2026, 10, 13, 21, 0)) is None


def test_intensity_spike_triggers(db_path):
    with database.getDb() as db:
        for d, i in (("2026-10-10", 3), ("2026-10-11", 3), ("2026-10-12", 4)):
            _mood(db, d, ["平静"], i)
        _mood(db, "2026-10-13", ["焦虑"], 9)  # 9 vs 前3日均值(3.3) 突升 ≥4
        hit = signals.detectSignal(db, datetime(2026, 10, 13, 21, 0))
    assert hit is not None and hit.kind == "spike"


def test_cooldown_suppresses_repeat(db_path):
    with database.getDb() as db:
        _mood(db, "2026-10-12", ["低落"], 6)
        _mood(db, "2026-10-13", ["低落"], 7)
        models.setSetting(db, signals.HANDLED_KEY_PREFIX + "low",
                          "2026-10-13T21:00:00")  # 1 小时前刚处理过低落
        assert signals.detectSignal(db, datetime(2026, 10, 13, 22, 0)) is None


def test_cooldown_is_per_kind(db_path):
    """两类信号冷却互不相干：low 被冷却挡住的同时，spike 仍应放行。

    数据集同时满足两类信号的触发条件：连续两天高强度低落（low 命中）
    且最新日 9 比前 3 日均值 4.0 突升 5（spike 命中）。low 已冷却 → 放行 spike。
    """
    with database.getDb() as db:
        for d in ("2026-10-10", "2026-10-11"):
            _mood(db, d, ["平静"], 3)
        _mood(db, "2026-10-12", ["低落"], 6)  # 与 10-13 构成连续低落
        _mood(db, "2026-10-13", ["低落"], 9)  # 强度高 → 对前 3 日均值(4.0)突升 5
        models.setSetting(db, signals.HANDLED_KEY_PREFIX + "low",
                          "2026-10-13T21:00:00")  # low 已冷却
        hit = signals.detectSignal(db, datetime(2026, 10, 13, 22, 0))
    assert hit is not None and hit.kind == "spike"  # low 被挡、spike 放行


def test_low_streak_broken_resets(db_path):
    with database.getDb() as db:
        _mood(db, "2026-10-12", ["低落"], 6)
        _mood(db, "2026-10-13", ["平静"], 2)  # 中断（枚举内标签）
        _mood(db, "2026-10-14", ["低落"], 7)  # 需重新累计
        assert signals.detectSignal(db, datetime(2026, 10, 14, 21, 0)) is None


def test_daily_digest_mood_not_counted(db_path):
    """日整合日记（kind=daily）的心情不计入信号取数。

    日整合的心情是同一天逐条心情的汇总，混进来等于同一天被平均两次：
    本例 10-12 逐条均值 4（未达标），加上日整合那条 9 之后会变成 6.5，误报连续低落。
    """
    with database.getDb() as db:
        _mood(db, "2026-10-12", ["低落"], 4)
        digestId = models.addDailyEntry(db, "2026-10-12", "整合正文")
        models.upsertMood(db, entryId=digestId, labels=["低落"], intensity=9,
                          summary="日级", crisis=False,
                          analyzedAt="2026-10-12T23:59:59", model="m")
        _mood(db, "2026-10-13", ["低落"], 6)
        assert signals.detectSignal(db, datetime(2026, 10, 13, 21, 0)) is None


def test_patrol_signal_opens_early(db_path, monkeypatch):
    """信号绕过「未到点」：冷档位 nextAt 还在明天，信号命中时本轮巡检即开口。"""
    from down_note.core import companion

    with database.getDb() as db:
        models.setSetting(db, companion.ENABLED_KEY, "1")
        models.setSetting(db, companion.TIER_KEY, "cold")
        models.setSetting(db, "base_url", "http://x/v1")
        models.setSetting(db, "model_name", "m")
        # 冷档位 nextAt 在很远的未来——频率逻辑本不该开口
        stateJson = (
                '{"day": "2026-10-13", "dayCount": 0, "missed": 0,'
                ' "nextAt": "2026-10-14T09:00:00"}'
            )
        models.setSetting(db, companion.STATE_KEY, stateJson)
        _mood(db, "2026-10-12", ["低落"], 6)
        _mood(db, "2026-10-13", ["低落"], 7)
        models.upsertChatSession(db, "sess-1", "2026-10-13T10:00:00")
    monkeypatch.setattr(companion, "_processStartedAt", datetime(2026, 10, 13, 0, 0))
    monkeypatch.setattr(companion, "_activityAt", {})  # 界面活动是模块级全局，清掉避免串用例
    monkeypatch.setattr(companion, "_openSession", lambda now: "sess-1")
    monkeypatch.setattr(companion, "_generateOpening", lambda cfg, sid, instruction="": "这两天还好吗？")
    monkeypatch.setattr(companion, "notifyProactiveMessage", lambda *a, **k: None)
    result = companion.patrol(now=datetime(2026, 10, 13, 21, 0))
    assert result["opened"] is True  # 信号绕过「未到点」提前开口
    with database.getDb() as db:
        assert models.getSetting(db, signals.HANDLED_KEY_PREFIX + "low") is not None


def test_patrol_signal_respects_startup_grace(db_path, monkeypatch):
    """信号不豁免启动缓冲：刚启动（<10 分钟）即使信号命中也不开口。"""
    from down_note.core import companion

    with database.getDb() as db:
        models.setSetting(db, companion.ENABLED_KEY, "1")
        models.setSetting(db, companion.TIER_KEY, "cold")
        models.setSetting(db, "base_url", "http://x/v1")
        models.setSetting(db, "model_name", "m")
        _mood(db, "2026-10-12", ["低落"], 6)
        _mood(db, "2026-10-13", ["低落"], 7)
    # 进程刚启动 2 分钟（缓冲 10 分钟内）
    monkeypatch.setattr(companion, "_processStartedAt", datetime(2026, 10, 13, 20, 58))
    monkeypatch.setattr(companion, "_generateOpening",
                        lambda *a, **k: pytest.fail("启动缓冲内不应生成"))
    result = companion.patrol(now=datetime(2026, 10, 13, 21, 0))
    assert result["opened"] is False and result["reason"] == "启动缓冲"
