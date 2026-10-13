# 02-信号触发 · 实施计划

> **For agentic workers:** REQUIRED SUB-SKILL: superpowers:subagent-driven-development 或 superpowers:executing-plans。步骤用 `- [ ]` 追踪。

**Goal:** 检测到连续低落或强度突变时，主动陪伴不等档位频率轮到，本轮巡检即带着对近几天状态的关注主动开口。

**Architecture:** 纯程序检测器（`core/signals.py`）挂在主动陪伴巡检环里，命中则绕过「未到点」一条等待、其余礼貌规则（窗口/上限/让路/退避）完全复用；开口内容用 `SIGNAL_CARE_INSTRUCTION` + 信号描述，复用既有生成链路。

**所属版本：** v0.3.0 ｜ **前置依赖：** 00（术语）、01（`LOW_LABELS` 已在 analyzeMood 落地）、v0.2.0 主动陪伴引擎

## Global Constraints

- 代码 camelCase；运行 `uv run`；测试 `uv run pytest`（基线 123 passed + 01 新增，不得回归；含既有 `test_companion_engine.py` 11 例）。
- 信号开口**完全同规则**：窗口 09:00–22:30、计入档位当日上限、让路、未回退避全部遵守；只是绕过「未到点」。
- 信号**无独立开关**，随主动陪伴（`companion_enabled`）生效；降级下开口按主动开口规则跳过、信号保持未处理。
- 「低落标签」= `core/prompts/analyzeMood.py` 的 `LOW_LABELS`（低落族：低落/难过/失落/沮丧/空虚/麻木）。
- 测试隔离：conftest `isolateDataDir` + `dbFile`；种子用无参 `getDb()`；不 monkeypatch `DEFAULT_DB_PATH`（不存在）。
- 两类信号（连续低落 `low` / 强度突变 `spike`）**各自独立冷却**——低落开口不压制突变。

## Interfaces（本任务对外的产出契约）

- `detectSignal(db, now: datetime) -> SignalHit | None`；`SignalHit`（dataclass：`kind: "low"|"spike"`、`detail: str`）
- `markHandled(db, kind: str, now: datetime)`；`HANDLED_KEY_PREFIX = "signal_handled_at:"`（键 = 前缀 + kind）
- `SIGNAL_CARE_INSTRUCTION`（`agent/prompts/companion.py`，经 `agent/prompts/__init__.py` 导出）
- `buildSignalContextText(hit) -> str`（`agent/context.py`，可选增强）
- companion `patrol` 信号命中时提前开口；`_generateOpening(cfg, sessionId, instruction=CARE_INSTRUCTION)` 加第三参

设计要点：信号检测挂在 `_skipReason` **之前**——命中时以 `ignoreTiming=True` 调 `_skipReason`（只绕过「启动缓冲」与「未到点」，窗口/上限/让路/退避照常），其余走原有频率逻辑。

---

### Task 2.1: 信号检测器

**Files:**
- Create: `src/down_note/core/signals.py`
- Test: `tests/test_companion_signals.py`

- [ ] **Step 1: 写失败测试**（检测器纯函数 + 两类信号独立冷却）

```python
# tests/test_companion_signals.py
"""信号触发（v0.3.0 02）：连续低落/强度突变判定、按类型独立冷却、巡检提前开口。

隔离由 conftest 的 isolateDataDir + dbFile 保证；种子用无参 getDb()。
"""
from datetime import datetime, timedelta

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
    """低落开口的冷却不压制强度突变（两类信号独立冷却）。"""
    with database.getDb() as db:
        for d, i in (("2026-10-10", 3), ("2026-10-11", 3), ("2026-10-12", 4)):
            _mood(db, d, ["平静"], i)
        _mood(db, "2026-10-13", ["焦虑"], 9)
        models.setSetting(db, signals.HANDLED_KEY_PREFIX + "low",
                          "2026-10-13T21:00:00")  # 低落刚冷却，突变不受压制
        hit = signals.detectSignal(db, datetime(2026, 10, 13, 22, 0))
    assert hit is not None and hit.kind == "spike"


def test_low_streak_broken_resets(db_path):
    with database.getDb() as db:
        _mood(db, "2026-10-12", ["低落"], 6)
        _mood(db, "2026-10-13", ["平静"], 2)  # 中断（枚举内标签）
        _mood(db, "2026-10-14", ["低落"], 7)  # 需重新累计
        assert signals.detectSignal(db, datetime(2026, 10, 14, 21, 0)) is None
```

- [ ] **Step 2: 跑测试确认失败**

Run: `uv run pytest tests/test_companion_signals.py -v`（Expected: FAIL `ModuleNotFoundError`）

- [ ] **Step 3: 实现检测器** `src/down_note/core/signals.py`

```python
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

    # 连续低落：最近两个「有记录」的自然日都满足低落门槛
    today, yesterday = days[0], days[1] if len(days) > 1 else None
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
```

- [ ] **Step 4: 跑测试确认通过**

Run: `uv run pytest tests/test_companion_signals.py -v`（Expected: 7 passed）

---

### Task 2.2: 提示词 + 巡检集成

**Files:**
- Modify: `src/down_note/agent/prompts/companion.py`（SIGNAL_CARE_INSTRUCTION）、`agent/prompts/__init__.py`（导出）、`src/down_note/core/companion.py`（巡检集成）
- Modify: `src/down_note/agent/context.py`（buildSignalContextText，可选增强）
- Test: `tests/test_companion_signals.py`（追加巡检集成用例）

- [ ] **Step 1: 提示词**——`agent/prompts/companion.py` 末尾（`CARE_INSTRUCTION` 后）加：

```python
# 信号开口（02-信号触发）：检测到连续低落/强度突变，它带着对近几天状态的关注主动开口
SIGNAL_CARE_INSTRUCTION = "（这一轮是你主动开口，用户没有说话。你留意到他最近这几天的状态不太对劲，像朋友察觉到了一样自然地递一句话——别点破「我检测到你连续低落」，别开诊断腔、不下判断，就像随口问问「这两天还好吗」。一两句以内，短、口语。）"
```

`agent/prompts/__init__.py` 导出 `SIGNAL_CARE_INSTRUCTION`（先看现有导出风格）。

- [ ] **Step 2: 上下文扩展（可选增强）**——`agent/context.py` 加：

```python
def buildSignalContextText(hit) -> str:
    """信号开口的附加上下文：近几天心情轨迹 + 信号描述（注入数据段）。"""
    with database.getDb() as db:
        pairs = models.listRecentMoods(db, limit=10)
    lines = [f"（信号：{hit.detail}）"]
    for createdAt, mood in pairs:
        labels = "/".join(json.loads(mood.labels))
        lines.append(f"{createdAt[:10]} {labels}（强度 {mood.intensity}）")
    return "\n".join(lines)
```

（本版先用「指令内嵌信号描述」，此函数备用；若要把心情轨迹也注入数据段再启用。）

- [ ] **Step 3: 巡检集成**（`companion.py`）

`_generateOpening` 加可选指令参（默认沿用 `CARE_INSTRUCTION`），把 `graph.stream` 的 `HumanMessage(content=CARE_INSTRUCTION)` 改为 `HumanMessage(content=instruction)`：

```python
def _generateOpening(cfg, sessionId: str, instruction: str = CARE_INSTRUCTION) -> str:
```

`_patrolOnce` 在算 `reason = _skipReason(...)` 之前插入信号判定。文件 import 区加 `from down_note.core import signals`、`from down_note.agent.prompts import SIGNAL_CARE_INSTRUCTION`（`CARE_INSTRUCTION` 现有 import 行扩展）。改动点：

```python
        hit = signals.detectSignal(db, current)  # 02：信号优先于频率
        if hit is not None:
            reason = _skipReason(state, tier, current, ignoreTiming=True)  # 绕过「未到点」，窗口/上限/让路/退避照常
        else:
            reason = _skipReason(state, tier, current, ignoreTiming)
```

`_openSession` 之后选指令（信号描述内嵌进指令，不动 refreshSystemPrompt 快照）：

```python
    sessionId = _openSession(current)
    instruction = (
            SIGNAL_CARE_INSTRUCTION + f"（{hit.detail}）" if hit is not None else CARE_INSTRUCTION
        )
    try:
        text = _generateOpening(cfg, sessionId, instruction)
```

落库块里开口成功后记冷却（按信号类型）：

```python
        if hit is not None:
            signals.markHandled(db, hit.kind, current)  # 开口成功才算处理（跳过不算），按类型记冷却
```

日志行改 `logger.info("主动陪伴已开口%s：%s", "（信号）" if hit else "", sessionId)`。

- [ ] **Step 4: 巡检集成测试**（追加到 `tests/test_companion_signals.py`）

```python
def test_patrol_signal_opens_early(db_path, monkeypatch):
    from down_note.core import companion
    with database.getDb() as db:
        models.setSetting(db, companion.ENABLED_KEY, "1")
        models.setSetting(db, companion.TIER_KEY, "cold")
        models.setSetting(db, "base_url", "http://x/v1")
        models.setSetting(db, "model_name", "m")
        # 冷档位 nextAt 在很远的未来——频率逻辑本不该开口
        models.setSetting(db, companion.STATE_KEY,
                          '{"day": "2026-10-13", "dayCount": 0, "missed": 0, "nextAt": "2026-10-14T09:00:00"}')
        _mood(db, "2026-10-12", ["低落"], 6)
        _mood(db, "2026-10-13", ["低落"], 7)
    monkeypatch.setattr(companion, "_processStartedAt", datetime(2026, 10, 13, 0, 0))
    monkeypatch.setattr(companion, "_openSession", lambda now: "sess-1")
    monkeypatch.setattr(companion, "_generateOpening", lambda cfg, sid, instruction="": "这两天还好吗？")
    monkeypatch.setattr(companion, "notifyProactiveMessage", lambda *a, **k: None)
    with database.getDb() as db:
        models.upsertChatSession(db, "sess-1", "2026-10-13T10:00:00")
    result = companion.patrol(now=datetime(2026, 10, 13, 21, 0))
    assert result["opened"] is True  # 信号绕过「未到点」提前开口
    with database.getDb() as db:
        assert models.getSetting(db, signals.HANDLED_KEY_PREFIX + "low") is not None
```

- [ ] **Step 5: 全量回归 + 提交**

Run: `uv run pytest -q`（含既有 `test_companion_engine.py` 11 例不回归）
```bash
git add src/down_note/core/signals.py src/down_note/core/companion.py src/down_note/agent/ tests/test_companion_signals.py
git commit -m "功能：v0.3.0 02 信号触发（连续低落/强度突变提前开口 + 内容针对 + 按类型冷却）"
```

---

## Self-Review

- **覆盖**：检测器(2.1 判据/冷却/重置/按类型冷却) + 巡检集成(2.2 提前开口/礼貌规则复用/内容针对)，覆盖总纲 02 全部决策。
- **占位**：无 TBD。
- **类型一致**：`detectSignal(db, now)`/`markHandled(db, kind, now)`/`HANDLED_KEY_PREFIX`/`SignalHit.kind` 在 2.1 定义与 2.2 消费一致；`_generateOpening(cfg, sessionId, instruction)` 三参与既有调用（两参，用默认值）兼容。
- **已修订**：`LOW_LABELS` 从 analyzeMood 引入（中性位置）；取数基准用传入 `now`；冷却按类型独立键；测试标签「开心」→「平静」；隔离用 conftest。
