# v0.3.0 陪伴感深化 实施计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 日记写完后 Agent 在条目下方留一两句回应（可点「聊聊」跳会话继续聊），且连续低落/强度突变时主动陪伴不等频率轮到、带着对近几天状态的关注主动开口。

**Architecture:** 日记回应挂分析管线尾部（异步、复用心情分析结果、独立生成调用），落 `entry_replies` 表、SSE 推送、不进会话；点「聊聊」把回应原文零模型调用地转移进最近活跃会话。信号触发是主动陪伴巡检环里的一个新检查项——纯程序判定心情记录，命中后提前开口、内容带近几天心情轨迹，完全复用既有让路/退避/窗口/上限。

**Tech Stack:** Python 3.12 · FastAPI · SQLAlchemy + SQLite · LangGraph · Vue 3 (Vite + TS) · Tauri 2 · pytest · uv

## Global Constraints

- 全程中文沟通与输出；代码标识符 camelCase（变量/函数/参数），类 PascalCase，常量 UPPER_SNAKE_CASE；数据库列名与外部约定字段名保留 snake_case（规范的强制例外）。
- 运行一律 `uv run <命令>`；加依赖用 `uv add`；测试 `uv run pytest`（现有基线 123 passed，不得回归）。
- 心情分析 prompt 标签枚举（低落/焦虑/愤怒/委屈/疲惫/平静/希望/孤独 各族）是「低落标签」判定的唯一来源，见 `core/prompts/analyzeMood.py`。
- 回应是对这篇日记的留言：**不进会话、不弹通知**（聊聊转移除外）；信号开口**完全遵守**普通主动开口的礼貌规则（窗口 09:00–22:30、当日上限、让路、未回退避）。
- 日记落库后不可删（产品铁规矩）；历史内容管理走记忆域。
- 回应开关键 `diary_reply_enabled`（settings 表），默认开启；信号无独立开关，随主动陪伴（`companion_enabled`）生效。
- 回应 prompt 走字符串拼接（`.format()` 会被用户日记里的花括号炸掉），人格经 `context.resolvePersonaText` 注入——与 04 人格模板的「只换风格层」约束一致。
- 每次提交前 `uv run pytest` 全绿；前端改动后 `cd frontend && npm run build` 通过。

---

### Task 0: 术语与文档同步（模块 00）

**Files:**
- Modify: `CONTEXT.md`（陪伴侧新增术语、修订「触发信号」）
- Modify: `docx/README.md`（路线图 v0.3.0 行、当前开发版本、顺延项）
- Modify: `AGENTS.md`（当前状态、v0.3.0 范围段）

**Interfaces:**
- Consumes: 无
- Produces: 术语「条目回应」（01 与前端组件命名遵循）；「触发信号」判据口径（02 实现遵循）

- [ ] **Step 1: CONTEXT.md 新增「条目回应」术语（陪伴侧，置于「人格模板」之后）**

```markdown
**条目回应**:
写下一条日记后，Agent 基于该条目及其心情记录自动生成的一两句留言，显示在日记条目下方；它是对这一篇的评论，不进会话、不弹通知；点击「聊聊」可带着它跳到最近活跃会话继续交谈。
_Avoid_: 日记评论、自动回复、留言板
```

- [ ] **Step 2: CONTEXT.md 修订「触发信号」**——把「第一版为连续低落与强度突变」的伏笔改成本版判据口径：连续 2 个自然日「当日有低落标签日记且日均强度 ≥5」；或单日日均强度比前 3 日均值突升 ≥4；检出后 48 小时冷却。

- [ ] **Step 3: docx/README.md**——路线图 v0.3.0 行改为「陪伴感深化（日记回应 + 信号触发）」，状态「未开始」；标注「回顾可视化、密钥加密存储顺延至后续版本」；「当前开发版本」段落指向 v0.3.0。

- [ ] **Step 4: AGENTS.md**——「当前状态」补一句 v0.3.0 进行中；MVP 边界后追加 v0.3.0 范围一段（日记回应 + 信号触发，详见 `docx/v0.3.0/README.md`）。

- [ ] **Step 5: 自查 + 提交**

Run: 通读三处改动，确认无自造同义词、「触发信号」新旧口径一致。
```bash
git add CONTEXT.md docx/README.md AGENTS.md
git commit -m "文档：v0.3.0 00 术语与文档同步（条目回应/触发信号判据）"
```

---

### Task 1: 数据层 `entry_replies` 表

**Files:**
- Create: `src/down_note/db/models/entryReply.py`
- Modify: `src/down_note/db/models/__init__.py`（汇总导出）
- Modify: `src/down_note/db/database.py`（SCHEMA_VERSION 7→8 + 迁移分支）
- Test: `tests/test_entry_reply.py`

**Interfaces:**
- Consumes: `db/models/base.py` 的 `Base`；`database.getDb()`
- Produces: `EntryReply`（ORM）、`createEntryReply(db, entryId, text) -> EntryReply | None`、`getReplyByEntry(db, entryId) -> EntryReply | None`、`markReplyTransferred(db, replyId, sessionId, messageId) -> None`——后续任务经 `models.xxx` 调用。

- [ ] **Step 1: 写失败测试**（建库、唯一约束、查询、转移标记、schema 版本推进）

```python
# tests/test_entry_reply.py
"""条目回应数据层（v0.3.0 01）：建库、一 entry 一回应、转移标记。"""
import pytest

from down_note.db import database, models


@pytest.fixture()
def db(tmp_path):
    database.ensureSchema(tmp_path / "t.db")
    with database.getDb(tmp_path / "t.db") as session:
        yield session


def _entry(db) -> int:
    return models.addEntry(db, "今天有点累", None, "2026-10-13T15:42:00")


def test_create_and_get(db):
    entryId = _entry(db)
    reply = models.createEntryReply(db, entryId, "累了就早点休息。")
    assert reply is not None
    got = models.getReplyByEntry(db, entryId)
    assert got is not None and got.reply_text == "累了就早点休息。"


def test_one_reply_per_entry(db):
    entryId = _entry(db)
    assert models.createEntryReply(db, entryId, "第一句") is not None
    assert models.createEntryReply(db, entryId, "第二句") is None  # 已存在则拒


def test_mark_transferred(db):
    entryId = _entry(db)
    reply = models.createEntryReply(db, entryId, "一句")
    models.markReplyTransferred(db, reply.id, "sess-1", 42)
    got = models.getReplyByEntry(db, entryId)
    assert got.session_id == "sess-1" and got.session_message_id == 42


def test_schema_version_bumped():
    assert database.SCHEMA_VERSION >= 8
```

- [ ] **Step 2: 跑测试确认失败**

Run: `uv run pytest tests/test_entry_reply.py -v`
Expected: FAIL（`AttributeError: module ... has no attribute 'createEntryReply'`）

- [ ] **Step 3: 实现 ORM 模型与访问函数** `src/down_note/db/models/entryReply.py`

```python
"""条目回应：一条目一回应（日记的附属留言，不进会话）。

对应开发文档：docx/v0.3.0/modules/01-日记回应.md
"""

from datetime import datetime

from sqlalchemy import ForeignKey, String, Text
from sqlalchemy.orm import Mapped, mapped_column, Session

from down_note.db.models.base import Base


class EntryReply(Base):
    __tablename__ = "entry_replies"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    entry_id: Mapped[int] = mapped_column(ForeignKey("entries.id", ondelete="CASCADE"), unique=True)
    reply_text: Mapped[str] = mapped_column(Text)
    session_id: Mapped[str | None] = mapped_column(String, default=None)  # 「聊聊」转移目标会话
    session_message_id: Mapped[int | None] = mapped_column(default=None)  # 转移后的会话消息 id
    created_at: Mapped[str] = mapped_column(String)


def createEntryReply(db: Session, entryId: int, text: str) -> EntryReply | None:
    """一 entry 一回应：已存在则返回 None（唯一约束兜底，重复生成被拒）。"""
    if getReplyByEntry(db, entryId) is not None:
        return None
    reply = EntryReply(
            entry_id=entryId,
            reply_text=text,
            created_at=datetime.now().isoformat(timespec="seconds"),
        )
    db.add(reply)
    db.flush()
    return reply


def getReplyByEntry(db: Session, entryId: int) -> EntryReply | None:
    return db.scalar(select(EntryReply).where(EntryReply.entry_id == entryId))


def markReplyTransferred(db: Session, replyId: int, sessionId: str, messageId: int) -> None:
    reply = db.get(EntryReply, replyId)
    if reply is None:
        return
    reply.session_id = sessionId
    reply.session_message_id = messageId
```

文件顶部 import 补 `from sqlalchemy import select`。

- [ ] **Step 4: 汇总导出**（`models/__init__.py` 追加）

```python
from down_note.db.models.entryReply import (
        EntryReply,
        createEntryReply,
        getReplyByEntry,
        markReplyTransferred,
    )
```

- [ ] **Step 5: schema 版本推进**（`database.py`）

`SCHEMA_VERSION = 7` 改 `8`；`ensureSchema` 在 `if version < 7:` 后追加：

```python
        if version < 8:
            _migrateToV8(conn)
```

文件底部加（新表由 `create_all` 幂等建，迁移分支仅留版本推进的显式钩子，与 v3/v7 同型——新表无需补列，保持分支存在以便版本记录）：

```python
def _migrateToV8(conn) -> None:
    """v7 → v8：新增 entry_replies 表（新库 create_all 已带；旧库由 create_all 补建）。"""
```

- [ ] **Step 6: 跑测试确认通过**

Run: `uv run pytest tests/test_entry_reply.py -v`
Expected: 4 passed

- [ ] **Step 7: 全量回归 + 提交**

Run: `uv run pytest -q`（Expected: 123 + 4 passed）
```bash
git add src/down_note/db/ tests/test_entry_reply.py
git commit -m "功能：v0.3.0 01 数据层 entry_replies 表（一条目一回应）"
```

---

### Task 2: 回应提示词 + 生成链路（挂分析管线尾）

**Files:**
- Create: `src/down_note/core/prompts/entryReply.py`
- Modify: `src/down_note/core/prompts/__init__.py`（导出）
- Create: `src/down_note/core/entryReply.py`（生成器）
- Modify: `src/down_note/core/analysis.py`（管线尾部挂回应步骤）
- Test: `tests/test_entry_reply_generate.py`

**Interfaces:**
- Consumes: Task 1 的 `createEntryReply`/`getReplyByEntry`；`analysis.MoodResult`；`llm.invokeModel`；`config.getModelServiceConfig`；`context.resolvePersonaText`；`database.getDb`；`broker`/`ENTRY_EVENTS_CHANNEL`
- Produces: `ENTRY_REPLY_PROMPT`（含 `{persona}` `{labels}` `{intensity}` `{summary}` `{content}` 占位）、`generateEntryReply(entryId: int) -> None`；SSE 事件 `{"type":"reply","entryId":N}` 发布到 `ENTRY_EVENTS_CHANNEL`。`LOW_LABELS`（低落族标签集合）定义在 `core/prompts/analyzeMood.py`（中性位置，signals.py 从那里 import，不反向依赖 entryReply）

回应与心情分析是**两次独立模型调用**：analysis 档强制关思考、800 预算且 prompt 是 JSON 观察员口吻，不适合一两句共情留言——回应用 chat 档（跟随用户温度/思考设置），单独一次调用。

- [ ] **Step 1: 写失败测试**（用 monkeypatch 拦截 `llm.invokeModel`，断言 prompt 装配与开关/降级行为）

```python
# tests/test_entry_reply_generate.py
"""条目回应生成链路（v0.3.0 01）：开关、降级、唯一、提示词装配。

隔离由 tests/conftest.py 的 autouse 夹具 isolateDataDir 保证（DOWN_NOTE_DATA_DIR 指向
tmp_path）。种子用无参 getDb()；调 generateEntryReply 不传 dbPath（用默认库=隔离库）。
人格测试通过写 tmp_path/soul.md 触发（config.getDataDir 已被夹具指向 tmp_path）。
"""
import pytest

from down_note.core import entryReply
from down_note.db import database, models


def _setup(monkeypatch, reply_text="抱抱，先喝口水。"):
    captured = {}

    def fakeInvoke(cfg, messages, *, profile="chat"):
        captured["system"] = messages[0].content
        return reply_text

    monkeypatch.setattr(entryReply.llm, "invokeModel", fakeInvoke)
    with database.getDb() as db:
        models.setSetting(db, "base_url", "http://x/v1")
        models.setSetting(db, "model_name", "m")
        entryId = models.addEntry(db, "今天面试砸了，胸口很闷。", None, "2026-10-13T15:42:00")
        models.upsertMood(db, entryId=entryId, labels=["低落"], intensity=7,
                          summary="面试砸了很闷", crisis=False,
                          analyzedAt="2026-10-13T15:42:05", model="m")
    return entryId, captured


def test_reply_generated_and_stored(monkeypatch):
    entryId, captured = _setup(monkeypatch)
    entryReply.generateEntryReply(entryId)
    with database.getDb() as db:
        got = models.getReplyByEntry(db, entryId)
    assert got is not None and got.reply_text == "抱抱，先喝口水。"
    assert "低落" in captured["system"] and "面试砸了" in captured["system"]


def test_disabled_switch_skips(monkeypatch):
    entryId, _ = _setup(monkeypatch)
    with database.getDb() as db:
        models.setSetting(db, "diary_reply_enabled", "0")
    entryReply.generateEntryReply(entryId)
    with database.getDb() as db:
        assert models.getReplyByEntry(db, entryId) is None


def test_unconfigured_model_skips(monkeypatch):
    with database.getDb() as db:  # 不配模型（无 base_url/model_name）
        entryId = models.addEntry(db, "x", None, "2026-10-13T15:42:00")
        models.upsertMood(db, entryId=entryId, labels=["平静"], intensity=3,
                          summary="普通", crisis=False, analyzedAt="x", model="m")
    monkeypatch.setattr(entryReply.llm, "invokeModel",
                        lambda *a, **k: pytest.fail("降级下不应调模型"))
    entryReply.generateEntryReply(entryId)
    with database.getDb() as db:
        assert models.getReplyByEntry(db, entryId) is None


def test_persona_injected(monkeypatch, tmp_path):
    entryId, captured = _setup(monkeypatch)
    with database.getDb() as db:
        models.setSetting(db, "persona_enabled", "1")
    (tmp_path / "soul.md").write_text("说话像损友，爱怼人。", encoding="utf-8")
    entryReply.generateEntryReply(entryId)
    assert "损友" in captured["system"]
```

- [ ] **Step 2: 跑测试确认失败**

Run: `uv run pytest tests/test_entry_reply_generate.py -v`
Expected: FAIL（`ModuleNotFoundError: down_note.core.entryReply`）

- [ ] **Step 3: 写回应提示词** `src/down_note/core/prompts/entryReply.py`

```python
"""条目回应提示词：对刚写完的这篇日记留一两句（v0.3.0 01）。

走字符串拼接（.format 会被日记原文里的花括号炸掉）；占位符在装配时逐个替换。
对应开发文档：docx/v0.3.0/modules/01-日记回应.md
"""

ENTRY_REPLY_PROMPT = """{persona}

用户刚写完一条日记，下面是它的心情记录和原文。请你以朋友的口吻留一两句话——像在朋友圈下面认真评论那样。

【心情记录】
情绪：{labels}（强度 {intensity}）——{summary}

【日记原文】
{content}

要求：
1. 一到两句话，口语、短，别端着、别文艺腔、别说教。
2. 低落就认真接住（先共情，不讲道理不给方案）；平静就简短打个招呼；开心就跟着开心。
3. 不总结、不用「加油」「坚强」这类口号；自称「我」，称对方「你」。
4. 只输出这句话本身，不要任何前后缀、引号或解释。"""

DEFAULT_REPLY_PERSONA = "你是一个真实、接地气的朋友，正在陪一个愿意写下心事的人。"
```

- [ ] **Step 4: 导出 + 中性位置定义低落标签**（两处）

`core/prompts/__init__.py` 追加：

```python
from down_note.core.prompts.entryReply import DEFAULT_REPLY_PERSONA, ENTRY_REPLY_PROMPT
```

`core/prompts/analyzeMood.py` 末尾追加（低落族标签是心情分析的属性，放中性位置供 signals.py 引用，避免 signals 反向依赖 entryReply）：

```python
# 低落族标签集合（v0.3.0 02 信号检测用）：与上文清单的低落族保持同步
LOW_LABELS = {"低落", "难过", "失落", "沮丧", "空虚", "麻木"}
```

（先看 `__init__.py` 现有导出风格，保持一致的 import 列表追加。）

- [ ] **Step 5: 实现生成器** `src/down_note/core/entryReply.py`

```python
"""条目回应生成：心情分析成功后，对这篇日记留一两句（v0.3.0 01）。

挂在分析管线尾部（异步、不阻塞分析返回）；复用心情分析产出，不重复分析条目。
失败静默跳过（不重试不补，与主动开口一致）；开关关闭或降级则不生成。
对应开发文档：docx/v0.3.0/modules/01-日记回应.md
"""

import json
import logging

from langchain_core.messages import HumanMessage, SystemMessage

from down_note import config
from down_note.agent import llm
from down_note.agent.context import resolvePersonaText
from down_note.core.events import ENTRY_EVENTS_CHANNEL, broker
from down_note.core.prompts import DEFAULT_REPLY_PERSONA, ENTRY_REPLY_PROMPT
from down_note.db import database, models

logger = logging.getLogger(__name__)

ENABLED_KEY = "diary_reply_enabled"  # settings 键：日记回应开关（"1"/"0"，缺省=开启）


def isReplyEnabled(db) -> bool:
    return models.getSetting(db, ENABLED_KEY) != "0"  # 缺省开启


def _buildPrompt(content: str, labels: list[str], intensity: int, summary: str, persona: str) -> str:
    return (
            ENTRY_REPLY_PROMPT
            .replace("{persona}", persona or DEFAULT_REPLY_PERSONA)
            .replace("{labels}", "/".join(labels))
            .replace("{intensity}", str(intensity))
            .replace("{summary}", summary)
            .replace("{content}", content)
        )


def generateEntryReply(entryId: int) -> None:
    """为一条已分析的日记生成回应并落库 + SSE 推送；任何失败静默跳过。"""
    with database.getDb() as db:
        if not isReplyEnabled(db):
            return
        if models.getReplyByEntry(db, entryId) is not None:
            return  # 一 entry 一回应
        entry = models.getEntry(db, entryId)
        mood = models.getMoodByEntry(db, entryId)
        if entry is None or mood is None or entry.kind != "entry":
            return
        cfg = config.getModelServiceConfig(db)
        if not cfg.isConfigured():
            return  # 降级：静默跳过不补
        persona = resolvePersonaText(db)
        content, labels = entry.content, json.loads(mood.labels)
        intensity, summary = mood.intensity, mood.summary

    prompt = _buildPrompt(content, labels, intensity, summary, persona)
    try:
        text = llm.invokeModel(
                cfg,
                [SystemMessage(content=prompt), HumanMessage(content="（刚写完这条日记）")],
            ).strip()
    except (llm.ModelConfigError, llm.ModelUnavailableError):
        logger.info("条目回应跳过：模型不可用（条目 %s）", entryId)
        return
    except Exception:
        logger.exception("条目回应生成失败（条目 %s）", entryId)
        return
    if not text:
        return

    with database.getDb() as db:
        reply = models.createEntryReply(db, entryId, text)
        if reply is None:
            return  # 并发下已被另一条任务生成
    broker.publish(ENTRY_EVENTS_CHANNEL, {"type": "reply", "entryId": entryId})
```

- [ ] **Step 6: 跑测试确认通过**

Run: `uv run pytest tests/test_entry_reply_generate.py -v`
Expected: 4 passed

- [ ] **Step 7: 挂分析管线尾**（`analysis.py`）

在 `analyzeEntry` 末尾（`_publishAnalyzeState(entryId, models.ANALYZE_DONE)` 之后、`return result` 之前）追加：

```python
    # 条目回应（v0.3.0 01）：分析成功的当天条目，异步留一两句；内部静默容错
    if entry.kind == "entry":
        try:
            entryReply.generateEntryReply(entryId)
        except Exception:
            logger.exception("条目回应步骤异常（条目 %s）", entryId)
```

文件头部 import 区追加 `from down_note.core import entryReply`（与 `from down_note.core import crisis` 同组）。注意 `analysis.py` 现有 `analyzeEntry` 中 `entry` 变量在第一个 `with database.getDb()` 块内取过（`entry = models.getEntry(db, entryId)`），确认 `entry.kind` 在该作用域可用。

- [ ] **Step 8: 全量回归 + 提交**

Run: `uv run pytest -q`（Expected: 123 + 4 + 4 passed，无回归）
```bash
git add src/down_note/core/ tests/test_entry_reply_generate.py
git commit -m "功能：v0.3.0 01 条目回应生成链路（提示词 + 管线尾部异步生成）"
```

---

### Task 3: 回应 API（读 + 「聊聊」转移 + 列表序列化）

**Files:**
- Modify: `src/down_note/api/entries.py`（EntryRead 加 reply 字段、新增转移端点）
- Test: `tests/test_entry_reply_api.py`

**Interfaces:**
- Consumes: Task 1 的 `getReplyByEntry`/`markReplyTransferred`；`models.addMessage`、`models.upsertChatSession`、`models.listRecentSessions`；`broker`
- Produces: `ReplyRead`（pydantic，字段 `replyText/createdAt/sessionId/transferred`）、`POST /api/entries/{entryId}/reply/chat -> ReplyRead`（幂等）；`EntryRead.reply: ReplyRead | None`（前端 Task 5 消费）

「聊聊」是零模型调用的纯转移：把回应原文作为 assistant 消息追加进最近活跃会话。只写 messages 表与会话活跃时间，与主动开口的落库方式一致（不直接动 graph state）。**幂等分支必须校验目标会话仍存在**（总纲：会话删除后回应保留、「聊聊」回到可点状态）——`session_message_id` 无指向会话的外键，会话被物理删除后该字段不会清空，不校验会把用户带到已消失的空会话。

- [ ] **Step 1: 写失败测试**

```python
# tests/test_entry_reply_api.py
"""条目回应接口（v0.3.0 01）：聊聊转移幂等、404。

隔离由 tests/conftest.py 的 autouse 夹具 isolateDataDir 保证（DOWN_NOTE_DATA_DIR 指向
tmp_path，getDb() 无参经 config.getDataDir() 落进临时库）；本文件不另设 monkeypatch——
不存在 database.DEFAULT_DB_PATH 这个常量，写了也是静默空操作。种子与断言都用无参 getDb()，
与 TestClient 里的 app 读同一个库。
"""
import pytest
from fastapi.testclient import TestClient

from down_note.app import app
from down_note.db import database, models


@pytest.fixture()
def client(dbFile):  # dbFile 建好隔离库；app 与种子同库
    return TestClient(app)


def _seed(entry_text="今天有点撑不住。", reply_text="撑不住就先靠一下。") -> int:
    with database.getDb() as db:
        entryId = models.addEntry(db, entry_text, None, "2026-10-13T15:42:00")
        models.createEntryReply(db, entryId, reply_text)
    return entryId


def test_chat_transfer_idempotent(client):
    entryId = _seed()
    r1 = client.post(f"/api/entries/{entryId}/reply/chat")
    assert r1.status_code == 200
    first = r1.json()
    assert first["transferred"] is True and first["sessionId"]
    r2 = client.post(f"/api/entries/{entryId}/reply/chat")
    assert r2.json()["sessionId"] == first["sessionId"]  # 幂等：不重复落库
    with database.getDb() as db:
        msgs = models.listMessages(db, first["sessionId"])
    assert sum(1 for m in msgs if m.content == "撑不住就先靠一下。") == 1


def test_chat_transfer_recovers_after_session_deleted(client):
    """总纲决策：会话删除后回应保留、「聊聊」回到可点状态——再次点击应转移到新会话。"""
    entryId = _seed()
    first = client.post(f"/api/entries/{entryId}/reply/chat").json()
    with database.getDb() as db:
        models.deleteSessionMessages(db, first["sessionId"])
        models.deleteChatSession(db, first["sessionId"])  # 物理删除目标会话
    second = client.post(f"/api/entries/{entryId}/reply/chat").json()
    assert second["transferred"] is True
    assert second["sessionId"] != first["sessionId"]  # 落到新的最近活跃会话（此处为新建）
    with database.getDb() as db:
        assert db.get(models.ChatSession, second["sessionId"]) is not None


def test_chat_transfer_404(client):
    with database.getDb() as db:
        entryId = models.addEntry(db, "x", None, "2026-10-13T15:42:00")  # 无回应
    assert client.post(f"/api/entries/{entryId}/reply/chat").status_code == 404
```

- [ ] **Step 2: 跑测试确认失败**

Run: `uv run pytest tests/test_entry_reply_api.py -v`
Expected: FAIL（404 路由不存在）

- [ ] **Step 3: 实现**（`api/entries.py`）

`EntryRead` 之后追加读模型：

```python
class ReplyRead(BaseModel):
    replyText: str
    createdAt: str
    sessionId: str | None
    transferred: bool
```

`EntryRead` 增加字段 `reply: ReplyRead | None = None`。

新增序列化与改造 `entryToRead`（需会话内查回应，给 `entryToRead` 加可选 `db` 参）：

```python
def replyToRead(reply: models.EntryReply | None) -> ReplyRead | None:
    if reply is None:
        return None
    return ReplyRead(
            replyText=reply.reply_text,
            createdAt=reply.created_at,
            sessionId=reply.session_id,
            transferred=reply.session_message_id is not None,
        )


def entryToRead(entry: models.Entry, db=None) -> EntryRead:
    reply = models.getReplyByEntry(db, entry.id) if db is not None else None
    return EntryRead(
            id=entry.id,
            content=entry.content,
            imageUrl=f"/api/images/{entry.image_path}" if entry.image_path else None,
            createdAt=entry.created_at,
            analyzed=bool(entry.analyzed),
            analyzeState=entry.analyze_state,
            kind=entry.kind,
            mood=moodToRead(entry.mood),
            reply=replyToRead(reply),
        )
```

`listEntries` 改为 `return [entryToRead(entry, db) for entry in entries]`（原 `entryToRead(entry)`，其余调用点不传 db 即可，回应为 None）。

新增转移端点（放 `getEntryMood` 附近）：

```python
@router.post("/entries/{entryId}/reply/chat")
def chatAboutReply(entryId: int) -> ReplyRead:
    """「聊聊」：把回应原文零模型调用地追加进最近活跃会话；幂等。

    幂等分支校验目标会话仍存在——会话被物理删除后 session_message_id 不会清空，
    不校验会把用户带到已消失的空会话；会话没了就当作未转移、重新落库。
    """
    with database.getDb() as db:
        reply = models.getReplyByEntry(db, entryId)
        if reply is None:
            raise HTTPException(status_code=404, detail="该条目还没有回应")
        if (
                reply.session_message_id is not None
                and reply.session_id is not None
                and db.get(models.ChatSession, reply.session_id) is not None
            ):
            return replyToRead(reply)  # 已转移且会话仍在：直接回现状，不重复落库
        sessions = models.listRecentSessions(db, limit=1)
        sessionId = sessions[0].session_id if sessions else uuid.uuid4().hex
        createdAt = _nowIso()
        if not sessions:
            models.upsertChatSession(db, sessionId, createdAt)
        messageId = models.addMessage(db, sessionId, "assistant", reply.reply_text, createdAt)
        models.upsertChatSession(db, sessionId, createdAt)  # 刷新最近活跃
        models.markReplyTransferred(db, reply.id, sessionId, messageId)
        result = replyToRead(models.getReplyByEntry(db, entryId))
    broker.publish(sessionId, {"type": "message", "message": {
            "role": "assistant", "content": reply.reply_text, "createdAt": createdAt}})
    return result
```

（文件已 import `uuid`；`broker` 需从 `down_note.core.events` 补入 import——现文件 import 行 `from down_note.core.events import ENTRY_EVENTS_CHANNEL, broker, sseFrame` 已含 broker，无需新增。）

- [ ] **Step 4: 跑测试确认通过**

Run: `uv run pytest tests/test_entry_reply_api.py -v`
Expected: 3 passed（含会话删除后恢复重转移）

- [ ] **Step 5: 全量回归 + 提交**

Run: `uv run pytest -q`
```bash
git add src/down_note/api/entries.py tests/test_entry_reply_api.py
git commit -m "功能：v0.3.0 01 回应读取与「聊聊」转移接口（幂等）"
```

---

### Task 4: 回应设置开关（独立，默认开启）

**Files:**
- Modify: `src/down_note/api/settings.py`（companion 读写带 diaryReplyEnabled）
- Modify: `frontend/src/api/types.ts`、`frontend/src/api/settings.ts`
- Test: `tests/test_settings_reply_toggle.py`

**Interfaces:**
- Consumes: `core/entryReply.ENABLED_KEY`（`diary_reply_enabled`）
- Produces: `GET/PUT /api/settings/companion` 读写 `diaryReplyEnabled: bool`（GET 缺省 true）；前端 `CompanionSettings.diaryReplyEnabled`、`saveCompanionSettings(enabled, tier, diaryReplyEnabled)`——Task 5 设置页消费。

- [ ] **Step 1: 写失败测试**

```python
# tests/test_settings_reply_toggle.py
"""日记回应开关（v0.3.0 01）：默认开启、可关、读回。

隔离由 conftest 的 isolateDataDir 保证；不 monkeypatch database.DEFAULT_DB_PATH（不存在）。
"""
import pytest
from fastapi.testclient import TestClient

from down_note.app import app


@pytest.fixture()
def client(dbFile):  # dbFile 建好隔离库
    return TestClient(app)


def test_default_on(client):
    assert client.get("/api/settings/companion").json()["diaryReplyEnabled"] is True


def test_toggle_off_persists(client):
    r = client.put("/api/settings/companion",
                   json={"enabled": False, "tier": "normal", "diaryReplyEnabled": False})
    assert r.status_code == 200
    assert client.get("/api/settings/companion").json()["diaryReplyEnabled"] is False
```

- [ ] **Step 2: 跑测试确认失败**

Run: `uv run pytest tests/test_settings_reply_toggle.py -v`
Expected: FAIL（KeyError 'diaryReplyEnabled'）

- [ ] **Step 3: 实现**（`api/settings.py`）

`CompanionSettingsRead` 加字段 `diaryReplyEnabled: bool`；`CompanionSettingsWrite` 加 `diaryReplyEnabled: bool = True`。
`getCompanionSettings` 的 `with database.getDb()` 块内加：

```python
        diaryReplyEnabled = models.getSetting(db, "diary_reply_enabled") != "0"
```

返回改为 `CompanionSettingsRead(enabled=enabled, tier=tier, diaryReplyEnabled=diaryReplyEnabled)`。
`saveCompanionSettings` 的写库块内加：

```python
        models.setSetting(db, "diary_reply_enabled", "1" if body.diaryReplyEnabled else "0")
```

- [ ] **Step 4: 前端类型与接口**

`types.ts` 的 `CompanionSettings` 加 `diaryReplyEnabled: boolean`。
`settings.ts` 的 `saveCompanionSettings` 签名改 `(enabled: boolean, tier: string, diaryReplyEnabled: boolean)`，body 加 `diaryReplyEnabled`。

- [ ] **Step 5: 测试 + 构建 + 提交**

Run: `uv run pytest tests/test_settings_reply_toggle.py -v`（2 passed）；`uv run pytest -q`；`cd frontend && npm run build`
```bash
git add src/down_note/api/settings.py frontend/src/api/types.ts frontend/src/api/settings.ts tests/test_settings_reply_toggle.py
git commit -m "功能：v0.3.0 01 日记回应开关（默认开启，存 settings）"
```

---

### Task 5: 前端回应卡片 + 「聊聊」跳转 + 设置页

**Files:**
- Create: `frontend/src/components/diary/EntryReplyCard.vue`
- Modify: `frontend/src/components/diary/EntryCard.vue`、`TodayEntryCard.vue`（嵌回应卡 + chat emit）
- Modify: `frontend/src/components/diary/DiaryPanel.vue`（接 reply SSE、聊聊跳转）
- Modify: `frontend/src/components/settings/CompanionSettingsPage.vue`（加回应开关）
- Modify: `frontend/src/api/entries.ts`（chatAboutReply）、`frontend/src/api/types.ts`（ReplyItem、EntryItem.reply）

**Interfaces:**
- Consumes: Task 3 的 `EntryRead.reply`、`POST /api/entries/{id}/reply/chat`；Task 4 的 `diaryReplyEnabled`；SSE 事件 `{type:'reply',entryId}`；appState 的 `requestOpenSession`（置 pendingSessionId 并切工作台）/`switchView`
- Produces: 无（终端 UI）

- [ ] **Step 1: 类型与 API**

`types.ts` 加：

```typescript
export interface ReplyItem {
  replyText: string
  createdAt: string
  sessionId: string | null
  transferred: boolean
}
```

`EntryItem` 加 `reply: ReplyItem | null`。

`entries.ts` 加：

```typescript
export async function chatAboutReply(entryId: number): Promise<ReplyItem> {
  const res = await api(`/api/entries/${entryId}/reply/chat`, { method: 'POST' })
  if (!res.ok) throw new Error('跳转失败')
  return res.json()
}
```

- [ ] **Step 2: 回应卡片组件** `EntryReplyCard.vue`

```vue
<script setup lang="ts">
// 条目回应卡（v0.3.0 01）：它对这篇日记的一两句留言 + 「聊聊 →」跳会话。
import type { ReplyItem } from '../../api'

defineProps<{ reply: ReplyItem }>()
const emit = defineEmits<{ chat: [] }>()
</script>

<template>
  <div class="reply-card">
    <p class="reply-text">它：{{ reply.replyText }}</p>
    <button class="m-link reply-chat" @click="emit('chat')">聊聊 →</button>
  </div>
</template>

<style scoped>
.reply-card {
  margin-top: 8px;
  padding: 10px 12px;
  border-left: 2px solid var(--accent, #c89b6d);
  background: var(--bg-soft, rgba(0, 0, 0, 0.03));
  border-radius: 6px;
}
.reply-text { margin: 0; font-size: var(--fs-helper); color: var(--ink-2); }
.reply-chat { float: right; }
</style>
```

- [ ] **Step 3: 嵌进两个条目卡**——`EntryCard.vue` 与 `TodayEntryCard.vue` 在心情记录 `</template>` 块之后各加：

```vue
    <EntryReplyCard v-if="entry.reply" :reply="entry.reply" @chat="emit('chat', entry.id)" />
```

并 `import EntryReplyCard from './EntryReplyCard.vue'`；两个组件的 `defineEmits` 都加 `chat: [entryId: number]`。

- [ ] **Step 4: DiaryPanel 接 SSE 与跳转**

DiaryPanel 已订阅 `openEntryEvents`。事件回调加 reply 分支：命中时重新拉取当前列表（调用现有的刷新函数）以拿到 `entry.reply`。新增处理函数：

```typescript
import { chatAboutReply } from '../../api'
import { requestOpenSession, switchView } from '../../stores/appState'

async function onReplyChat(entryId: number): Promise<void> {
  try {
    const result = await chatAboutReply(entryId)
    if (result.sessionId) requestOpenSession(result.sessionId)  // 置 pendingSessionId + 切工作台
    else switchView('workbench')
  } catch { /* 静默，按钮可重试 */ }
}
```

模板里两个卡片组件上加 `@chat="onReplyChat"`。SSE 的 `onEvent` 增加：`if (e.type === 'reply') { void 刷新函数() }`（用 DiaryPanel 现有的条目刷新函数重拉，使 `entry.reply` 到位）。

- [ ] **Step 5: 设置页加开关**——`CompanionSettingsPage.vue` 在「主动陪伴」行后加一行：

```vue
  <div class="row">
    <div class="row-text">
      <span class="row-label">日记回应</span>
      <p class="f-hint">写完一条日记，它会在下面留一两句话。关闭后新日记不再生成回应。</p>
    </div>
    <ToggleSwitch :model-value="diaryReplyEnabled" label="日记回应" @update:model-value="onReplyToggle" />
  </div>
```

script 加 `const diaryReplyEnabled = ref(true)`，onMounted 回填 `diaryReplyEnabled.value = settings.diaryReplyEnabled`；新增 `onReplyToggle`（置值 + `void persist()`）；`persist` 里 `saveCompanionSettings(enabled.value, tier.value, diaryReplyEnabled.value)`。

- [ ] **Step 6: 构建 + 提交**

Run: `cd frontend && npm run build`（成功）；`uv run pytest -q`（无回归）
```bash
git add frontend/src/
git commit -m "功能：v0.3.0 01 前端回应卡片 + 聊聊跳转 + 设置开关"
```

---

### Task 6: 信号触发（检测器 + 巡检集成 + 内容针对性）

**Files:**
- Create: `src/down_note/core/signals.py`（纯程序信号检测器）
- Modify: `src/down_note/core/companion.py`（巡检加信号检查项、信号开口内容）
- Modify: `src/down_note/agent/context.py`（信号开口上下文扩展）
- Modify: `src/down_note/agent/prompts/companion.py`（新增 SIGNAL_CARE_INSTRUCTION）
- Test: `tests/test_companion_signals.py`

**Interfaces:**
- Consumes: `models.listRecentMoods(db, limit)`（既有，返回 `[(created_at, Mood)]`）；`core/prompts/analyzeMood.LOW_LABELS`（中性位置）；companion 既有 `_skipReason`/`_openSession`/`_generateOpening`/`_scheduleNext`/状态键
- Produces: `detectSignal(db, now) -> SignalHit | None`；`SignalHit`（dataclass，`kind: "low"|"spike"`、`detail: str`）；`HANDLED_KEY_PREFIX`（按信号类型记冷却）；`markHandled(db, kind, now)`；`SIGNAL_CARE_INSTRUCTION`；companion `patrol` 在信号命中时提前开口（外部行为不变，仍返回 `{opened, reason, sessionId}`）

设计要点：信号检测挂在 `_skipReason` **之前**——信号命中时跳过「未到点」这一条等待（其余窗口/上限/让路/退避照常），其余情况走原有频率逻辑。

- [ ] **Step 1: 写失败测试**（检测器纯函数 + 巡检集成）

```python
# tests/test_companion_signals.py
"""信号触发（v0.3.0 02）：连续低落/强度突变判定、冷却、巡检提前开口。"""
from datetime import datetime, timedelta

import pytest

from down_note.core import signals
from down_note.db import database, models


@pytest.fixture()
def db_path(dbFile):  # conftest dbFile：隔离库已建表；种子用无参 getDb
    return dbFile


def _mood(db, day: str, labels, intensity: int, entry_id_offset: int = 0):
    entryId = models.addEntry(db, f"{day} 的日记", None, f"{day}T20:00:00")
    models.upsertMood(db, entryId=entryId, labels=labels, intensity=intensity,
                      summary="s", crisis=False, analyzedAt=f"{day}T20:00:01", model="m")
    return entryId


def test_no_signal_when_calm(db_path):
    with database.getDb(db_path) as db:
        _mood(db, "2026-10-12", ["平静"], 3)
        _mood(db, "2026-10-13", ["平静"], 3)
        assert signals.detectSignal(db, datetime(2026, 10, 13, 21, 0)) is None


def test_consecutive_low_triggers(db_path):
    with database.getDb(db_path) as db:
        _mood(db, "2026-10-12", ["低落"], 6)
        _mood(db, "2026-10-13", ["低落"], 7)
        hit = signals.detectSignal(db, datetime(2026, 10, 13, 21, 0))
    assert hit is not None and hit.kind == "low"


def test_consecutive_low_below_threshold_no_trigger(db_path):
    with database.getDb(db_path) as db:
        _mood(db, "2026-10-12", ["低落"], 3)  # 强度不足
        _mood(db, "2026-10-13", ["低落"], 4)
        assert signals.detectSignal(db, datetime(2026, 10, 13, 21, 0)) is None


def test_single_low_day_no_trigger(db_path):
    with database.getDb(db_path) as db:
        _mood(db, "2026-10-13", ["低落"], 8)  # 只有一天
        assert signals.detectSignal(db, datetime(2026, 10, 13, 21, 0)) is None


def test_intensity_spike_triggers(db_path):
    with database.getDb(db_path) as db:
        for d, i in (("2026-10-10", 3), ("2026-10-11", 3), ("2026-10-12", 4)):
            _mood(db, d, ["平静"], i)
        _mood(db, "2026-10-13", ["焦虑"], 9)  # 9 vs 前3日均值(3.3) 突升 ≥4
        hit = signals.detectSignal(db, datetime(2026, 10, 13, 21, 0))
    assert hit is not None and hit.kind == "spike"


def test_cooldown_suppresses_repeat(db_path):
    with database.getDb(db_path) as db:
        _mood(db, "2026-10-12", ["低落"], 6)
        _mood(db, "2026-10-13", ["低落"], 7)
        models.setSetting(db, signals.HANDLED_KEY_PREFIX + "low",
                          "2026-10-13T21:00:00")  # 1 小时前刚处理过低落
        assert signals.detectSignal(db, datetime(2026, 10, 13, 22, 0)) is None


def test_cooldown_is_per_kind(db_path):
    """低落开口的冷却不压制强度突变（两类信号独立冷却）。"""
    with database.getDb(db_path) as db:
        for d, i in (("2026-10-10", 3), ("2026-10-11", 3), ("2026-10-12", 4)):
            _mood(db, d, ["平静"], i)
        _mood(db, "2026-10-13", ["焦虑"], 9)
        models.setSetting(db, signals.HANDLED_KEY_PREFIX + "low",
                          "2026-10-13T21:00:00")  # 低落刚冷却，突变不受压制
        hit = signals.detectSignal(db, datetime(2026, 10, 13, 22, 0))
    assert hit is not None and hit.kind == "spike"


def test_low_streak_broken_resets(db_path):
    with database.getDb(db_path) as db:
        _mood(db, "2026-10-12", ["低落"], 6)
        _mood(db, "2026-10-13", ["平静"], 2)  # 中断（用枚举内标签）
        _mood(db, "2026-10-14", ["低落"], 7)  # 需重新累计
        assert signals.detectSignal(db, datetime(2026, 10, 14, 21, 0)) is None
```

- [ ] **Step 2: 跑测试确认失败**

Run: `uv run pytest tests/test_companion_signals.py -v`
Expected: FAIL（`ModuleNotFoundError: down_note.core.signals`）

- [ ] **Step 3: 实现检测器** `src/down_note/core/signals.py`

```python
"""触发信号检测（v0.3.0 02）：纯程序判定心情异常模式，检出后主动陪伴提前开口。

保守判据（宁漏勿扰）：
  连续低落 = 连续 2 个自然日「当日有低落标签日记 且 日均强度 ≥5」；
  强度突变 = 单日日均强度 比 前 3 日均值 突升 ≥4。
检出并开口后记 48 小时冷却（同一波低落不反复触发）；连续低落中断即重置。
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
WINDOW_DAYS = 7  # 「近几天」取数窗口（总纲待定项：定 7 天）


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

    两类信号各自独立冷却（「同一波低落不反复触发」——低落开口不压制突变）。
    判据从宽：「前 3 日」取最近 3 个有记录的日子，不强求连续自然日（有意从宽，见模块 02）。
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

Run: `uv run pytest tests/test_companion_signals.py -v`
Expected: 7 passed

- [ ] **Step 5: 提示词 + 上下文扩展**

`agent/prompts/companion.py` 末尾（`CARE_INSTRUCTION` 后）加：

```python
# 信号开口（02-信号触发）：检测到连续低落/强度突变，它带着对近几天状态的关注主动开口
SIGNAL_CARE_INSTRUCTION = "（这一轮是你主动开口，用户没有说话。你留意到他最近这几天的状态不太对劲，像朋友察觉到了一样自然地递一句话——别点破「我检测到你连续低落」，别开诊断腔、不下判断，就像随口问问「这两天还好吗」。一两句以内，短、口语。）"
```

并在 `agent/prompts/__init__.py` 导出 `SIGNAL_CARE_INSTRUCTION`。

`agent/context.py` 新增（供信号开口拼上下文）：

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

- [ ] **Step 6: 巡检集成**（`companion.py`）

`_generateOpening` 加可选指令参（默认沿用 `CARE_INSTRUCTION`）：

```python
def _generateOpening(cfg, sessionId: str, instruction: str = CARE_INSTRUCTION) -> str:
    ...
    for chunk, meta in graph.stream(
            {"messages": [HumanMessage(content=instruction)]},
            ...
```

`_patrolOnce` 在算 `reason = _skipReason(...)` **之前**插入信号判定，命中则绕过「未到点」但保留其余礼貌规则。最小侵入做法：新增 `_signalSkipReason`，与 `_skipReason` 的差别只是不做 `nextAt` 检查：

```python
from down_note.core import signals
from down_note.agent.prompts import SIGNAL_CARE_INSTRUCTION

def _patrolOnce(current, ignoreTiming=False):
    with database.getDb() as db:
        if models.getSetting(db, ENABLED_KEY) != "1":
            return {"opened": False, "reason": "主动陪伴未开启", "sessionId": None}
        tier = models.getSetting(db, TIER_KEY) or "normal"
        if tier not in TIERS:
            tier = "normal"
        state = _loadState(db)
        _rollDay(state, current)
        lastOpenAt = _parseTs(state.get("lastOpenAt"))
        if lastOpenAt is not None and models.hasUserMessageSince(db, lastOpenAt.isoformat(timespec="seconds")):
            state["missed"] = 0
        hit = signals.detectSignal(db, current)  # 02：信号优先于频率
        if hit is not None:
            reason = _skipReason(state, tier, current, ignoreTiming=True)  # 绕过「未到点」，窗口/上限/让路/退避照常
        else:
            reason = _skipReason(state, tier, current, ignoreTiming)
        if reason is not None:
            _saveState(db, state)
            return {"opened": False, "reason": reason, "sessionId": None}
        cfg = config.getModelServiceConfig(db)
        if not cfg.isConfigured():
            _saveState(db, state)
            return {"opened": False, "reason": "未配置模型", "sessionId": None}
        _saveState(db, state)

    sessionId = _openSession(current)
    instruction = (
            SIGNAL_CARE_INSTRUCTION + f"（{hit.detail}）" if hit is not None else CARE_INSTRUCTION
        )  # 信号开口把信号描述拼进指令（不动 refreshSystemPrompt 快照机制，风险最小）
    try:
        text = _generateOpening(cfg, sessionId, instruction)
    except (llm.ModelConfigError, llm.ModelUnavailableError):
        return {"opened": False, "reason": "模型不可用", "sessionId": sessionId}
    except Exception:
        logger.exception("主动开口生成失败")
        return {"opened": False, "reason": "生成失败", "sessionId": sessionId}
    if not text:
        return {"opened": False, "reason": "空回复", "sessionId": sessionId}

    createdAt = nowIso()
    with database.getDb() as db:
        if db.get(models.ChatSession, sessionId) is None:
            return {"opened": False, "reason": "目标会话已被删除", "sessionId": sessionId}
        models.addMessage(db, sessionId, "assistant", text, createdAt)
        models.upsertChatSession(db, sessionId, createdAt)
        if hit is not None:
            signals.markHandled(db, hit.kind, current)  # 开口成功才算处理（跳过不算），按信号类型记冷却
        state = _loadState(db)
        state["lastOpenAt"] = current.isoformat(timespec="seconds")
        state["dayCount"] = state.get("dayCount", 0) + 1
        state["missed"] = state.get("missed", 0) + 1
        _scheduleNext(state, tier, current)
        _saveState(db, state)

    broker.publish(sessionId, {"type": "message", "message": {
            "role": "assistant", "content": text, "createdAt": createdAt}})
    if _insideWindow(current):
        body = text if len(text) <= NOTIFY_BODY_MAX else text[:NOTIFY_BODY_MAX] + "…"
        notifyProactiveMessage(sessionId, NOTIFY_TITLE, body)
    logger.info("主动陪伴已开口%s：%s", "（信号）" if hit else "", sessionId)
    return {"opened": True, "reason": None, "sessionId": sessionId}
```

说明：信号上下文通过指令内嵌信号描述注入（`SIGNAL_CARE_INSTRUCTION + f"（{hit.detail}）"`），不动 `refreshSystemPrompt` 的快照机制，风险最小。Step 5 的 `buildSignalContextText` 为可选增强——若后续要把近几天心情轨迹也注入数据段再启用，本版先用指令内嵌即可。

- [ ] **Step 7: 巡检集成测试**（追加到 `tests/test_companion_signals.py`：信号命中提前开口、冷却期内走回频率逻辑、窗口外信号不开口）

```python
def test_patrol_signal_opens_early(db_path, monkeypatch):
    from down_note.core import companion
    with database.getDb(db_path) as db:
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
    with database.getDb(db_path) as db:
        models.upsertChatSession(db, "sess-1", "2026-10-13T10:00:00")
    result = companion.patrol(now=datetime(2026, 10, 13, 21, 0))
    assert result["opened"] is True  # 信号绕过「未到点」提前开口
    with database.getDb(db_path) as db:
        assert models.getSetting(db, signals.HANDLED_KEY_PREFIX + "low") is not None
```

- [ ] **Step 8: 全量回归 + 提交**

Run: `uv run pytest -q`（含既有 `test_companion_engine.py` 11 例不回归）
```bash
git add src/down_note/core/signals.py src/down_note/core/companion.py src/down_note/agent/ tests/test_companion_signals.py
git commit -m "功能：v0.3.0 02 信号触发（连续低落/强度突变提前开口 + 内容针对）"
```

---

### Task 7: 打包发布（模块 03）

**Files:**
- Modify: `pyproject.toml`、`frontend/src-tauri/tauri.conf.json`、`frontend/package.json`、`README.md`（版本号 + 功能一览）
- Build: `scripts/build.py`

**Interfaces:**
- Consumes: Task 0–6 全部完成且测试全绿
- Produces: `dist/DownNote_0.3.0_x64-setup.exe`

- [ ] **Step 1: 全量测试**

Run: `uv run pytest -q`（Expected: 全绿，含 01/02 新增用例，无回归）

- [ ] **Step 2: 版本号四处同步**——`pyproject.toml`（version）、`tauri.conf.json`（version + 产物名）、`frontend/package.json`（version）、`README.md` 徽章（0.2.0 → 0.3.0）；`uv lock` 使 `uv.lock` 同步。

- [ ] **Step 3: README 功能一览**补 v0.3.0 两项（日记回应、信号触发），下载说明版本号更新。

- [ ] **Step 4: 产包**

Run: `uv run python scripts/build.py` → 确认 `dist/DownNote_0.3.0_x64-setup.exe` 生成。

- [ ] **Step 5: 覆盖升级验证（用户实机）**——旧版本装 0.3.0：数据保留、日记回应出现、信号触发可验、历史条目无回应不报错；回填 v0.2.0 的 06 遗留验证状态。

- [ ] **Step 6: Release 文案**撰写；推送与挂附件（经用户同意后执行）。

```bash
git add pyproject.toml uv.lock frontend/src-tauri/tauri.conf.json frontend/package.json README.md
git commit -m "发布：v0.3.0 版本号同步 + 功能一览更新"
```

---

## Self-Review

**Spec coverage：** 00 术语 → Task 0；01 日记回应（数据层 Task 1、生成 Task 2、API Task 3、开关 Task 4、前端 Task 5）；02 信号触发 → Task 6；03 打包 → Task 7；04 记忆修复已完成（不在本计划）。总纲关键决策逐条可指：回应落点（Task 1/5）、回应条件（Task 2 prompt 分档）、聊聊转移（Task 3 幂等 + 会话删除后恢复重转移）、信号判据与冷却（Task 6 signals.py，两类信号独立冷却）、完全同礼貌规则（Task 6 巡检集成 `_skipReason` 复用）、降级静默跳过（Task 2）、会话删除不动回应且聊聊可恢复（Task 1 表无外键级联 + Task 3 幂等分支校验会话存在）。

**Placeholder scan：** 无 TBD/TODO；Task 5 Step 4 的「刷新函数」需实施者对照 DiaryPanel 实际的条目刷新函数名（已知存在，名称以代码为准）——这是有意保留的对照点，非占位。导航函数名已定为 `requestOpenSession`（appState.ts:71 真实导出）。

**Type consistency：** `createEntryReply/getReplyByEntry/markReplyTransferred`（Task 1 定义 → Task 2/3 消费）一致；`detectSignal -> SignalHit`、`markHandled(db, kind, now)`、`HANDLED_KEY_PREFIX`（Task 6 内部一致，两类信号独立冷却）；`diaryReplyEnabled`（Task 4 后端 → Task 5 前端）一致；`ReplyRead`/`ReplyItem` 字段 `replyText/createdAt/sessionId/transferred` 前后端一致；`LOW_LABELS` 定义于 `core/prompts/analyzeMood.py`（中性位置），signals.py 从该处 import。

**评审修订（2026-10-13，对照真实代码）**：① 删除两处 `monkeypatch.setattr(database, "DEFAULT_DB_PATH", ...)`（该常量不存在，隔离由 conftest `isolateDataDir` + `DOWN_NOTE_DATA_DIR` 保证；种子与断言改用无参 `getDb()`）；② 前端导航函数 `openSessionChat` → `requestOpenSession`（appState.ts:71）；③ 「聊聊」幂等分支补会话存在性校验（会话删除后恢复重转移，对齐总纲决策）；④ 信号冷却改按类型独立键（`signal_handled_at:low/spike`），避免低落开口压制突变；⑤ `detectSignal` 取数基准从 `datetime.now()` 改为传入的 `now`（否则跨日测试漂移）；⑥ `LOW_LABELS` 从 entryReply 挪到 analyzeMood（中性位置）；⑦ 测试样本标签「开心」→「平静」（枚举内）。
