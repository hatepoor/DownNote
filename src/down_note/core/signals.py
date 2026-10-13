"""触发信号检测（v0.3.0 02）：纯程序判定心情异常模式，检出后主动陪伴提前开口。

保守判据（宁漏勿扰）：
  连续低落 = 连续 2 个自然日「当日有低落标签日记 且 日均强度 ≥5」；
  强度突变 = 单日日均强度 比 前 3 日均值 突升 ≥4。
检出并开口后记 48 小时冷却；两类信号各自独立冷却（低落开口不压制突变）；连续低落中断即重置。
取数基准为传入的 now（不用系统时间），保证测试可复现。
对应开发文档：docx/v0.3.0/modules/02-信号触发.md
"""

import json
from dataclasses import dataclass
from datetime import datetime, timedelta

from down_note.core.prompts.analyzeMood import LOW_LABELS
from down_note.db import models

HANDLED_KEY_PREFIX = "signal_handled_at:"  # settings 键前缀：按信号类型分别记冷却（low / spike）
COOLDOWN_HOURS = 48
LOW_MIN_INTENSITY = 5
SPIKE_DELTA = 4
WINDOW_DAYS = 7  # 「近几天」取数窗口


@dataclass
class SignalHit:
    kind: str  # "low"=连续低落 | "spike"=强度突变
    detail: str  # 给开口上下文的自然语言描述


def _dailyMood(db, now: datetime, days: int) -> dict[str, list[tuple[list[str], int]]]:
    """以 now 为基准取最近 days 天按日聚合的心情记录：{YYYY-MM-DD: [(labels, intensity), ...]}。"""
    since = (now - timedelta(days=days)).isoformat(timespec="seconds")
    result: dict[str, list] = {}
    for createdAt, mood in models.listRecentMoods(db, limit=200):
        if createdAt < since:
            continue
        day = createdAt[:10]
        result.setdefault(day, []).append((json.loads(mood.labels), mood.intensity))
    return result


def _avg(intensities: list[int]) -> float:
    return sum(intensities) / len(intensities) if intensities else 0.0


def _dayIsLow(entries: list[tuple[list[str], int]]) -> bool:
    hasLow = any(any(label in LOW_LABELS for label in labels) for labels, _ in entries)
    return hasLow and _avg([i for _, i in entries]) >= LOW_MIN_INTENSITY


def _inCooldown(db, kind: str, now: datetime) -> bool:
    raw = models.getSetting(db, HANDLED_KEY_PREFIX + kind)
    if not raw:
        return False
    try:
        return now - datetime.fromisoformat(raw) < timedelta(hours=COOLDOWN_HOURS)
    except ValueError:
        return False


def detectSignal(db, now: datetime) -> SignalHit | None:
    """检出未处理信号则返回 SignalHit；冷却期内或无信号返回 None。

    两类信号各自独立冷却。判据从宽：「前 3 日」取最近 3 个有记录的日子，
    不强求连续自然日（有意从宽，覆盖低频写日记的用户，见模块 02）。
    """
    daily = _dailyMood(db, now, WINDOW_DAYS)
    days = sorted(daily.keys(), reverse=True)  # 新→旧
    if not days:
        return None  # 近几天没有任何心情记录：无信号可判

    # 连续低落：最近两个「有记录」的自然日都满足低落门槛
    today = days[0]
    yesterday = days[1] if len(days) > 1 else None
    if (
            not _inCooldown(db, "low", now)
            and today and yesterday
            and (datetime.fromisoformat(today) - datetime.fromisoformat(yesterday)).days == 1
            and _dayIsLow(daily[today]) and _dayIsLow(daily[yesterday])
        ):
        avg = _avg([i for _, i in daily[today]] + [i for _, i in daily[yesterday]])
        return SignalHit("low", f"用户已连续两天低落（日均强度 {avg:.1f}）")

    # 强度突变：最新一天比前 3 天均值突升
    if not _inCooldown(db, "spike", now) and len(days) >= 2:
        prevDays = days[1:4]
        prev = [i for d in prevDays for _, i in daily[d]]
        latest = [i for _, i in daily[days[0]]]
        if prev and latest and _avg(latest) - _avg(prev) >= SPIKE_DELTA:
            return SignalHit("spike", f"用户今天情绪强度骤升（{_avg(latest):.1f}，前几日约 {_avg(prev):.1f}）")
    return None


def markHandled(db, kind: str, now: datetime) -> None:
    models.setSetting(db, HANDLED_KEY_PREFIX + kind, now.isoformat(timespec="seconds"))
