"""主动陪伴引擎：巡检（纯程序）决定此刻该不该开口，命中后发起一次生成任务。

判定全是轻量程序（表一计时与计数、表二让路、表四未回退避，无模型调用）；模型只说内容——
复用主智能体链路与人格注入（04）。状态存 settings 的 companion_state JSON，跨重启保留；
窗口外一律不开口；降级 / 让路 / 锁被占都只跳过本次——不补发、不攒（nextAt 不变，下次再判）。
对应开发文档：docx/v0.2.0/modules/05-主动陪伴引擎.md
"""

import json
import logging
import random
import threading
import uuid
from datetime import datetime, time, timedelta

from langchain_core.messages import HumanMessage

from down_note import config
from down_note.agent import llm, mainAgent
from down_note.agent.checkpointer import getCheckpointer
from down_note.agent.context import nowIso, refreshSystemPrompt
from down_note.agent.prompts import CARE_INSTRUCTION, SIGNAL_CARE_INSTRUCTION
from down_note.agent.tools import getCurrentTime
from down_note.core import signals
from down_note.core.events import broker, notifyProactiveMessage, turnLock
from down_note.db import database, models

logger = logging.getLogger(__name__)

STATE_KEY = "companion_state"  # settings 键：引擎状态 JSON（键名驼峰）
ENABLED_KEY = "companion_enabled"
TIER_KEY = "companion_tier"
TIERS = ("cold", "normal", "caring")

# 表一：计时与计数（基准值，实机按体感微调）
TIER_INTERVAL_MINUTES = {
    "cold": (4 * 60, 6 * 60),
    "normal": (2 * 60, 3 * 60),
    "caring": (60, 2 * 60),
}
TIER_DAY_CAPS = {"cold": 3, "normal": 6, "caring": 12}
WINDOW_START = time(9, 0)
WINDOW_END = time(22, 30)
MIN_GAP_MINUTES = 45
STARTUP_GRACE_MINUTES = 10
DAY_START_SPREAD_MINUTES = 60

# 表二：让路（活动状态按"最近 N 分钟有动作"判定，自动过期）
ACTIVITY_WINDOW_MINUTES = 5
ACTIVITY_KINDS = ("diary", "chat")

# 表四：未回退避
MAX_MISSED = 3

NOTIFY_TITLE = "低落日记"
NOTIFY_BODY_MAX = 120

_processStartedAt = datetime.now()  # 进程启动时刻（表二「刚启动 10 分钟内」）
_activityAt: dict[str, datetime] = {}  # 界面活动时刻（前端节流上报）
_patrolLock = threading.Lock()


def reportActivity(kind: str) -> None:
    """前端上报界面活动（写日记 / 对话中）；只记时刻，判定按 5 分钟有效期算。"""
    _activityAt[kind] = datetime.now()


def markProcessStart(now: datetime | None = None) -> None:
    """重置启动缓冲基准（应用启动 / 测试用）。"""
    global _processStartedAt
    _processStartedAt = now or datetime.now()


def _parseTs(raw: str | None) -> datetime | None:
    if not raw:
        return None
    try:
        return datetime.fromisoformat(raw)
    except ValueError:
        return None


def _loadState(db) -> dict:
    raw = models.getSetting(db, STATE_KEY)
    if not raw:
        return {}
    try:
        return json.loads(raw)
    except ValueError:
        return {}


def _saveState(db, state: dict) -> None:
    models.setSetting(db, STATE_KEY, json.dumps(state, ensure_ascii=False))


def _rollDay(state: dict, now: datetime) -> None:
    """跨天：当日计数与未回计数重置（表四「次日恢复」）。"""
    day = now.strftime("%Y-%m-%d")
    if state.get("day") == day:
        return
    state["day"] = day
    state["dayCount"] = 0
    state["missed"] = 0
    state["nextAt"] = now.isoformat(timespec="seconds")  # 新的一天从"已到点"起（仍受缓冲与窗口约束）


def _scheduleNext(state: dict, tier: str, openedAt: datetime) -> None:
    """下次开口 = 本次开口 + 档位区间内随机值；越窗顺延到次日窗口内随机一刻（表一）。"""
    low, high = TIER_INTERVAL_MINUTES.get(tier, TIER_INTERVAL_MINUTES["normal"])
    target = openedAt + timedelta(minutes=random.randint(low, high))
    if target.time() > WINDOW_END:
        nextDay = (openedAt + timedelta(days=1)).date()
        target = datetime.combine(nextDay, WINDOW_START) + timedelta(
                minutes=random.randint(0, DAY_START_SPREAD_MINUTES)
            )
    state["nextAt"] = target.isoformat(timespec="seconds")


def _insideWindow(now: datetime) -> bool:
    return WINDOW_START <= now.time() <= WINDOW_END


def _skipReason(
        state: dict,
        tier: str,
        now: datetime,
        ignoreTiming: bool,
        ignoreNextAt: bool = False,
    ) -> str | None:
    """表一 / 表二 / 表四判定：返回 None 表示可以开口，否则返回跳过原因（便于日志与测试）。

    ignoreTiming（开发自测口子）：跳过"启动缓冲"与"未到点"两条等待，其余照常。
    ignoreNextAt（02-信号触发）：只豁免"未到点"（频率等待）——启动缓冲、窗口、上限、
    让路、退避全部照常；刚启动就开口很突兀，信号的价值在"不等频率"而非"不等启动"。
    """
    if not ignoreTiming and now - _processStartedAt < timedelta(minutes=STARTUP_GRACE_MINUTES):
        return "启动缓冲"
    if not _insideWindow(now):
        return "窗口外"
    nextAt = _parseTs(state.get("nextAt"))
    if not ignoreTiming and not ignoreNextAt and nextAt is not None and now < nextAt:
        return "未到点"
    lastOpenAt = _parseTs(state.get("lastOpenAt"))
    if lastOpenAt is not None and now - lastOpenAt < timedelta(minutes=MIN_GAP_MINUTES):
        return "兜底最小间隔"
    if state.get("dayCount", 0) >= TIER_DAY_CAPS.get(tier, TIER_DAY_CAPS["normal"]):
        return "当日上限"
    if state.get("missed", 0) >= MAX_MISSED:
        return "连续未回（当日停止）"
    for kind in ACTIVITY_KINDS:
        at = _activityAt.get(kind)
        if at is not None and now - at < timedelta(minutes=ACTIVITY_WINDOW_MINUTES):
            return "用户正在写日记或对话中"
    return None


def _openSession(now: datetime) -> str:
    """落点：最近活跃会话；一条会话都没有时才新建（表三 / 落点的用户口径）。"""
    with database.getDb() as db:
        sessions = models.listRecentSessions(db, limit=1)
        if sessions:
            return sessions[0].session_id
        sessionId = uuid.uuid4().hex
        models.upsertChatSession(db, sessionId, nowIso())
    return sessionId


def _generateOpening(cfg, sessionId: str, instruction: str = CARE_INSTRUCTION) -> str:
    """一次生成任务：复用主智能体链路（同人格、同工具边界），返回回复文本。

    "一次"指不为"是否开口"额外问模型；实际可能包含工具调用与空回复兜底的多次模型请求。
    instruction 默认普通主动开口；信号开口传带信号描述的 SIGNAL_CARE_INSTRUCTION（02）。
    """
    graph = mainAgent.buildMainAgent(cfg, getCheckpointer(), sessionId)
    refreshSystemPrompt(graph, sessionId, getCurrentTime.invoke({}))
    replyText = ""
    with turnLock(sessionId):
        for chunk, meta in graph.stream(
                {"messages": [HumanMessage(content=instruction)]},
                {"configurable": {"thread_id": sessionId}},
                stream_mode="messages",
            ):
            if meta.get("langgraph_node") != "agent":
                continue
            text = llm.messageText(chunk)
            if text:
                replyText += text
    return replyText.strip()


def patrol(now: datetime | None = None, ignoreTiming: bool = False) -> dict:
    """巡检一次：该开口就发起生成；返回 {opened, reason, sessionId}。

    ignoreTiming=True（开发自测口子 / 托盘「试一次开口」）：跳过"启动缓冲"与"未到点"，
    其余判定照常——让"我现在就想看看它怎么开口"不用等一两个小时。
    """
    current = now or datetime.now()
    if not _patrolLock.acquire(blocking=False):
        return {"opened": False, "reason": "上一次巡检还在跑", "sessionId": None}
    try:
        return _patrolOnce(current, ignoreTiming)
    finally:
        _patrolLock.release()


def _patrolOnce(current: datetime, ignoreTiming: bool = False) -> dict:
    with database.getDb() as db:
        if models.getSetting(db, ENABLED_KEY) != "1":
            return {"opened": False, "reason": "主动陪伴未开启", "sessionId": None}
        tier = models.getSetting(db, TIER_KEY) or "normal"
        if tier not in TIERS:
            tier = "normal"
        state = _loadState(db)
        _rollDay(state, current)
        lastOpenAt = _parseTs(state.get("lastOpenAt"))
        if lastOpenAt is not None and models.hasUserMessageSince(
                db, lastOpenAt.isoformat(timespec="seconds")
            ):
            state["missed"] = 0  # 表四：主动开口之后用户回过话 → 未回计数清零
        hit = signals.detectSignal(db, current)  # 02：信号优先于频率
        if hit is not None:
            # 只豁免「未到点」：启动缓冲 / 窗口 / 上限 / 让路 / 退避全部照常
            reason = _skipReason(state, tier, current, ignoreTiming, ignoreNextAt=True)
        else:
            reason = _skipReason(state, tier, current, ignoreTiming)
        if reason is not None:
            _saveState(db, state)
            logger.debug("主动陪伴跳过：%s", reason)
            return {"opened": False, "reason": reason, "sessionId": None}
        cfg = config.getModelServiceConfig(db)
        if not cfg.isConfigured():
            _saveState(db, state)  # 降级：跳过本次，不补发不攒（nextAt 不变）
            logger.info("主动陪伴跳过：未配置模型")
            return {"opened": False, "reason": "未配置模型", "sessionId": None}
        _saveState(db, state)

    sessionId = _openSession(current)
    # 信号开口把「信号描述」内嵌进指令（近几天心情轨迹已由常规上下文装配带入）
    instruction = (
            SIGNAL_CARE_INSTRUCTION + f"（{hit.detail}）" if hit is not None else CARE_INSTRUCTION
        )
    try:
        text = _generateOpening(cfg, sessionId, instruction)
    except (llm.ModelConfigError, llm.ModelUnavailableError):
        logger.info("主动陪伴跳过：模型不可用")
        return {"opened": False, "reason": "模型不可用", "sessionId": sessionId}
    except Exception:
        logger.exception("主动开口生成失败")
        return {"opened": False, "reason": "生成失败", "sessionId": sessionId}
    if not text:
        logger.info("主动陪伴跳过：空回复")
        return {"opened": False, "reason": "空回复", "sessionId": sessionId}

    createdAt = nowIso()
    with database.getDb() as db:
        if db.get(models.ChatSession, sessionId) is None:
            logger.info("主动陪伴：目标会话已被删除，本次丢弃")
            return {"opened": False, "reason": "目标会话已被删除", "sessionId": sessionId}  # 表三：不改投、不新建
        models.addMessage(db, sessionId, "assistant", text, createdAt)
        models.upsertChatSession(db, sessionId, createdAt)
        if hit is not None:
            signals.markHandled(db, hit.kind, current)  # 开口成功才算处理（跳过不算），按类型记冷却
        state = _loadState(db)
        state["lastOpenAt"] = current.isoformat(timespec="seconds")
        state["dayCount"] = state.get("dayCount", 0) + 1
        state["missed"] = state.get("missed", 0) + 1
        _scheduleNext(state, tier, current)
        _saveState(db, state)

    # 会话开着就直接看到这条（不用刷新）；系统通知由前端决定弹不弹（窗口在前台就不打扰）
    broker.publish(
            sessionId,
            {"type": "message", "message": {"role": "assistant", "content": text, "createdAt": createdAt}},
        )
    if _insideWindow(current):
        body = text if len(text) <= NOTIFY_BODY_MAX else text[:NOTIFY_BODY_MAX] + "…"
        notifyProactiveMessage(sessionId, NOTIFY_TITLE, body)
    logger.info("主动陪伴已开口%s：%s（%s 字）", "（信号）" if hit is not None else "", sessionId, len(text))
    return {"opened": True, "reason": None, "sessionId": sessionId}
