"""主动陪伴引擎（05）测试：计时/计数、让路、未回退避、落点、降级与在途删除。

判定全部注入 now（不依赖真实时钟），可逐条演练文档里的表一~表四。
对应模块：docx/v0.2.0/modules/05-主动陪伴引擎.md
"""

import json
from datetime import datetime, time, timedelta

import helpers
from helpers import FakeToolModel

from down_note.agent import llm as agentLlm
from down_note.core import companion
from down_note.core.events import broker
from down_note.db import database, models

CARE_REPLY = "在忙吗？"


def _at(hour: int, minute: int, daysAgo: int = 0) -> datetime:
    return datetime.combine(datetime.now().date() - timedelta(days=daysAgo), time(hour, minute))


def _configure(db, enabled: bool = True, tier: str = "normal", withModel: bool = True) -> None:
    if withModel:
        models.setSetting(db, "base_url", "http://model.local/v1")
        models.setSetting(db, "model_name", "test-model")
    models.setSetting(db, companion.ENABLED_KEY, "1" if enabled else "0")
    models.setSetting(db, companion.TIER_KEY, tier)


def _setState(db, **fields) -> None:
    models.setSetting(db, companion.STATE_KEY, json.dumps(fields, ensure_ascii=False))


def _state() -> dict:
    with database.getDb() as db:
        raw = models.getSetting(db, companion.STATE_KEY)
    return json.loads(raw) if raw else {}


def _ready(monkeypatch, reply: str = CARE_REPLY) -> list[int]:
    """把启动缓冲挪到 30 天前（注入的 now 无论早晚都已过缓冲），并记录模型构建次数（0 = 没开口）。"""
    calls: list[int] = []
    monkeypatch.setattr(companion, "_processStartedAt", datetime.now() - timedelta(days=30))

    def factory(cfg, **kw):
        calls.append(1)
        return FakeToolModel(messages=iter([helpers.AIMessage(content=reply)]))

    monkeypatch.setattr(agentLlm, "buildChatModel", factory)
    return calls


def _openings() -> list:
    with database.getDb() as db:
        return [
                message
                for session in models.listRecentSessions(db, limit=10)
                for message in models.listMessages(db, session.session_id)
                if message.role == "assistant"
            ]


def test_disabledDoesNothing(dataDir, dbFile, monkeypatch):
    """开关关闭：与现状完全一致——什么都不做，状态也不动。"""
    with database.getDb() as db:
        _configure(db, enabled=False)
    calls = _ready(monkeypatch)
    companion.patrol(_at(12, 0))
    assert calls == []
    assert _state() == {}


def test_startupGraceSkips(dataDir, dbFile, monkeypatch):
    """刚启动 10 分钟内让路（表二）。"""
    with database.getDb() as db:
        _configure(db)
    calls: list[int] = []

    def factory(cfg, **kw):
        calls.append(1)
        return FakeToolModel(messages=iter([helpers.AIMessage(content=CARE_REPLY)]))

    monkeypatch.setattr(agentLlm, "buildChatModel", factory)
    monkeypatch.setattr(companion, "_processStartedAt", _at(12, 0) - timedelta(minutes=1))
    companion.patrol(_at(12, 0))
    assert calls == []


def test_outsideWindowSkips(dataDir, dbFile, monkeypatch):
    """窗口外（含深夜）一律不开口。"""
    with database.getDb() as db:
        _configure(db)
    calls = _ready(monkeypatch)
    companion.patrol(_at(23, 30))
    companion.patrol(_at(7, 30))
    assert calls == []
    assert _openings() == []


def test_waitsForNextAtAndDayCap(dataDir, dbFile, monkeypatch):
    """未到点 / 当日上限：都跳过，且 nextAt 不变（下次再判）。"""
    with database.getDb() as db:
        _configure(db)
        _setState(
                db,
                day=_at(12, 0).strftime("%Y-%m-%d"),
                nextAt=(_at(12, 0) + timedelta(minutes=30)).isoformat(timespec="seconds"),
                dayCount=0,
                missed=0,
            )
    calls = _ready(monkeypatch)
    companion.patrol(_at(12, 0))
    assert calls == []

    with database.getDb() as db:
        _setState(
                db,
                day=_at(12, 0).strftime("%Y-%m-%d"),
                nextAt=_at(12, 0).isoformat(timespec="seconds"),
                dayCount=companion.TIER_DAY_CAPS["normal"],
                missed=0,
            )
    companion.patrol(_at(12, 0))
    assert calls == []


def test_missedStreakStopsTodayAndRecoversTomorrow(dataDir, dbFile, monkeypatch):
    """连续 3 次未回 → 当日停止；次日恢复（表四）。"""
    today = _at(12, 0).strftime("%Y-%m-%d")
    yesterday = _at(12, 0, daysAgo=1).strftime("%Y-%m-%d")
    with database.getDb() as db:
        _configure(db)
        _setState(
                db,
                day=today,
                nextAt=_at(12, 0).isoformat(timespec="seconds"),
                dayCount=1,
                missed=companion.MAX_MISSED,
            )
    calls = _ready(monkeypatch)
    companion.patrol(_at(12, 0))
    assert calls == []  # 当日停止

    # 次日：跨天重置 missed / dayCount → 正常开口
    with database.getDb() as db:
        _setState(
                db,
                day=yesterday,
                nextAt=_at(12, 0, daysAgo=1).isoformat(timespec="seconds"),
                dayCount=1,
                missed=companion.MAX_MISSED,
            )
    companion.patrol(_at(10, 0))
    assert calls  # 已经开口
    assert _state()["missed"] == 1
    assert _state()["dayCount"] == 1


def test_userReplyResetsMissed(dataDir, dbFile, monkeypatch):
    """主动开口之后用户回过话 → 未回计数清零（哪怕此前已经攒到 3）。"""
    openedAt = _at(10, 0)
    with database.getDb() as db:
        _configure(db)
        sessionId = "s-replied"
        models.upsertChatSession(db, sessionId, openedAt.isoformat(timespec="seconds"))
        models.addMessage(
                db,
                sessionId,
                "user",
                "我在",
                (_at(10, 30)).isoformat(timespec="seconds"),
            )
        _setState(
                db,
                day=openedAt.strftime("%Y-%m-%d"),
                nextAt=_at(11, 0).isoformat(timespec="seconds"),
                lastOpenAt=openedAt.isoformat(timespec="seconds"),
                dayCount=1,
                missed=companion.MAX_MISSED,
            )
    calls = _ready(monkeypatch)
    companion.patrol(_at(11, 5))
    assert calls  # 回过话 → 清零 → 到点就开口


def test_activityMakesWay(dataDir, dbFile, monkeypatch):
    """用户正在写日记 / 对话中（5 分钟有效期）→ 让路；过期自动失效。"""
    with database.getDb() as db:
        _configure(db)
        _setState(
                db,
                day=_at(12, 0).strftime("%Y-%m-%d"),
                nextAt=_at(12, 0).isoformat(timespec="seconds"),
                dayCount=0,
                missed=0,
            )
    calls = _ready(monkeypatch)

    monkeypatch.setattr(companion, "_activityAt", {"diary": _at(12, 0)})
    companion.patrol(_at(12, 2))
    assert calls == []  # 正在写日记：让路

    monkeypatch.setattr(companion, "_activityAt", {"chat": _at(12, 0) - timedelta(minutes=6)})
    companion.patrol(_at(12, 2))
    assert calls  # 6 分钟前的活动：已过期，可以开口


def test_landsInMostRecentSessionOrCreatesOne(dataDir, dbFile, monkeypatch):
    """落点 = 最近活跃会话；一条会话都没有时才新建（表三 / 落点的用户口径）。"""
    with database.getDb() as db:
        _configure(db)
        models.upsertChatSession(db, "s-old", _at(8, 0).isoformat(timespec="seconds"))
        models.upsertChatSession(db, "s-new", _at(9, 0).isoformat(timespec="seconds"))
        _setState(
                db,
                day=_at(12, 0).strftime("%Y-%m-%d"),
                nextAt=_at(12, 0).isoformat(timespec="seconds"),
                dayCount=0,
                missed=0,
            )
    _ready(monkeypatch)
    companion.patrol(_at(12, 0))
    with database.getDb() as db:
        assert models.listMessages(db, "s-new")  # 落在最近活跃会话
        assert models.listMessages(db, "s-old") == []

    # 清空会话后再巡检：新建一个会话并把话落进去
    with database.getDb() as db:
        models.deleteChatSession(db, "s-old")
        models.deleteChatSession(db, "s-new")
        _setState(
                db,
                day=_at(13, 0).strftime("%Y-%m-%d"),
                nextAt=_at(13, 0).isoformat(timespec="seconds"),
                dayCount=0,
                missed=0,
            )
    companion.patrol(_at(13, 0))
    with database.getDb() as db:
        sessions = models.listRecentSessions(db, limit=5)
        assert len(sessions) == 1
        assert models.listMessages(db, sessions[0].session_id)  # 新建的会话里有这条


def test_opensPersistsNotifiesAndUpdatesState(dataDir, dbFile, monkeypatch):
    """正常开口：落库 + 会话事件 + 系统通知 + 状态推进（dayCount/missed/nextAt）。"""
    with database.getDb() as db:
        _configure(db, tier="cold")
    _ready(monkeypatch)
    notified: list[tuple] = []
    published: list[tuple] = []
    monkeypatch.setattr(
            companion, "notifyProactiveMessage", lambda sid, title, body: notified.append((sid, title, body))
        )
    monkeypatch.setattr(broker, "publish", lambda channel, event: published.append((channel, event)))

    now = _at(14, 0)
    companion.patrol(now)

    state = _state()
    assert state["dayCount"] == 1
    assert state["missed"] == 1
    assert state["lastOpenAt"] == now.isoformat(timespec="seconds")
    low, high = companion.TIER_INTERVAL_MINUTES["cold"]
    nextAt = datetime.fromisoformat(state["nextAt"])
    assert timedelta(minutes=low) <= nextAt - now <= timedelta(minutes=high)

    assert len(notified) == 1
    assert notified[0][1] == companion.NOTIFY_TITLE and notified[0][2] == CARE_REPLY
    assert any(channel == notified[0][0] and event["type"] == "message" for channel, event in published)


def test_degradedSkipsWithoutTouchingNextAt(dataDir, dbFile, monkeypatch):
    """降级（未配置模型）：跳过本次，不补发不攒——nextAt 原样不动。"""
    with database.getDb() as db:
        _configure(db, withModel=False)
        dueAt = _at(12, 0).isoformat(timespec="seconds")
        _setState(db, day=_at(12, 0).strftime("%Y-%m-%d"), nextAt=dueAt, dayCount=0, missed=0)
    calls = _ready(monkeypatch)
    companion.patrol(_at(12, 0))
    assert calls == []
    assert _state()["nextAt"] == dueAt


def test_sessionDeletedDuringGenerationIsDiscarded(dataDir, dbFile, monkeypatch):
    """生成期间目标会话被删 → 本次丢弃（不写入、不复活）；不计次数。"""
    with database.getDb() as db:
        _configure(db)
        models.upsertChatSession(db, "s-doomed", _at(11, 0).isoformat(timespec="seconds"))
    _ready(monkeypatch)

    def fakeGenerate(cfg, sessionId):
        with database.getDb() as db:
            models.deleteChatSession(db, sessionId)
            models.deleteSessionMessages(db, sessionId)
        return CARE_REPLY

    monkeypatch.setattr(companion, "_generateOpening", fakeGenerate)
    companion.patrol(_at(12, 0))

    with database.getDb() as db:
        assert models.listRecentSessions(db, limit=5) == []
    assert _state().get("dayCount", 0) == 0  # 丢弃的开口不计次数
