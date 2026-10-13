# 01-日记回应 · 实施计划

> **For agentic workers:** REQUIRED SUB-SKILL: superpowers:subagent-driven-development 或 superpowers:executing-plans。步骤用 `- [ ]` 追踪。

**Goal:** 日记写完、心情分析成功后，Agent 在该条目下方留一两句回应（可点「聊聊」零模型调用地跳进最近活跃会话继续聊）。

**Architecture:** 回应挂分析管线尾部（异步、复用心情分析结果、独立一次 chat 档模型调用），落 `entry_replies` 表（一 entry 一回应）、SSE 推送、不进会话不弹通知；「聊聊」把回应原文追加进最近活跃会话（幂等 + 会话删除后恢复重转移）。

**所属版本：** v0.3.0 ｜ **前置依赖：** 00（术语）

## Global Constraints

- 代码 camelCase（变量/函数/参数），类 PascalCase，常量 UPPER_SNAKE_CASE；DB 列名 snake_case（规范例外）。
- 运行 `uv run <命令>`；测试 `uv run pytest`（基线 123 passed 不得回归）；前端 `cd frontend && npm run build` 通过。
- 回应**不进会话、不弹通知**（聊聊转移除外）；日记落库后不可删（铁规矩）。
- 回应开关键 `diary_reply_enabled`（settings 表），**默认开启**；降级模式静默跳过不补。
- 回应 prompt 走字符串拼接（`.format()` 会被日记花括号炸掉），人格经 `context.resolvePersonaText` 注入（只换风格层）。
- 测试隔离：conftest `isolateDataDir`（autouse，`DOWN_NOTE_DATA_DIR`→tmp_path）+ `dbFile` 夹具建表；种子与断言用**无参 `getDb()`**，与 TestClient 的 app 同库。**不存在 `database.DEFAULT_DB_PATH`**——不要 monkeypatch 它。
- `LOW_LABELS`（低落族标签集合）定义在 `core/prompts/analyzeMood.py`（中性位置），本任务 Step 2 一并加入（供 02 信号检测引用）。

## Interfaces（本任务对外的产出契约）

- 数据层：`EntryReply`（ORM）、`createEntryReply(db, entryId, text) -> EntryReply | None`、`getReplyByEntry(db, entryId) -> EntryReply | None`、`markReplyTransferred(db, replyId, sessionId, messageId) -> None`
- 生成器：`generateEntryReply(entryId: int) -> None`（无 dbPath 参，用默认库）；SSE 事件 `{"type":"reply","entryId":N}` 发到 `ENTRY_EVENTS_CHANNEL`
- 提示词：`ENTRY_REPLY_PROMPT`（占位 `{persona}` `{labels}` `{intensity}` `{summary}` `{content}`）、`DEFAULT_REPLY_PERSONA`
- API：`EntryRead.reply: ReplyRead | None`；`POST /api/entries/{entryId}/reply/chat -> ReplyRead`（幂等，会话删除后恢复重转移）；`ReplyRead{replyText,createdAt,sessionId,transferred}`
- 设置：`GET/PUT /api/settings/companion` 带 `diaryReplyEnabled: bool`（GET 缺省 true）
- 前端：`ReplyItem` 类型、`EntryItem.reply`、`chatAboutReply(entryId)`、`EntryReplyCard.vue`、DiaryPanel 的 `onReplyChat`（用 `requestOpenSession`/`switchView`）

---

### Task 1.1: 数据层 `entry_replies` 表

**Files:**
- Create: `src/down_note/db/models/entryReply.py`
- Modify: `src/down_note/db/models/__init__.py`、`src/down_note/db/database.py`（SCHEMA_VERSION 7→8）
- Test: `tests/test_entry_reply.py`

- [ ] **Step 1: 写失败测试**

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
Expected: FAIL（`AttributeError: ... no attribute 'createEntryReply'`）

- [ ] **Step 3: 实现** `src/down_note/db/models/entryReply.py`（文件顶部 import `from sqlalchemy import ForeignKey, String, Text, select`）

```python
"""条目回应：一条目一回应（日记的附属留言，不进会话）。

对应开发文档：docx/v0.3.0/modules/01-日记回应.md
"""

from datetime import datetime

from sqlalchemy import ForeignKey, String, Text, select
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

- [ ] **Step 4: 汇总导出**（`models/__init__.py` 追加）

```python
from down_note.db.models.entryReply import (
        EntryReply,
        createEntryReply,
        getReplyByEntry,
        markReplyTransferred,
    )
```

- [ ] **Step 5: schema 版本推进**（`database.py`）——`SCHEMA_VERSION = 7` 改 `8`；`ensureSchema` 在 `if version < 7:` 后加 `if version < 8: _migrateToV8(conn)`；文件底部加：

```python
def _migrateToV8(conn) -> None:
    """v7 → v8：新增 entry_replies 表（新库 create_all 已带；旧库由 create_all 补建）。"""
```

- [ ] **Step 6: 跑测试确认通过**

Run: `uv run pytest tests/test_entry_reply.py -v`（Expected: 4 passed）

- [ ] **Step 7: 全量回归 + 提交**

Run: `uv run pytest -q`（Expected: 123 + 4 passed）
```bash
git add src/down_note/db/ tests/test_entry_reply.py
git commit -m "功能：v0.3.0 01 数据层 entry_replies 表（一条目一回应）"
```

---

### Task 1.2: 回应提示词 + 生成链路（挂分析管线尾）

**Files:**
- Create: `src/down_note/core/prompts/entryReply.py`、`src/down_note/core/entryReply.py`
- Modify: `src/down_note/core/prompts/__init__.py`、`src/down_note/core/prompts/analyzeMood.py`（LOW_LABELS）、`src/down_note/core/analysis.py`
- Test: `tests/test_entry_reply_generate.py`

回应与心情分析是**两次独立模型调用**：analysis 档强制关思考、800 预算且 prompt 是 JSON 观察员口吻，不适合共情留言——回应用 chat 档（跟随用户温度/思考设置），单独一次调用。

- [ ] **Step 1: 写失败测试**（monkeypatch 拦 `llm.invokeModel`；种子用无参 `getDb()`，隔离靠 conftest）

```python
# tests/test_entry_reply_generate.py
"""条目回应生成链路（v0.3.0 01）：开关、降级、唯一、提示词装配。

隔离由 tests/conftest.py 的 autouse 夹具 isolateDataDir 保证；种子用无参 getDb()，
调 generateEntryReply 不传 dbPath（默认库=隔离库）。人格测试写 tmp_path/soul.md 触发
（config.getDataDir 已被夹具指向 tmp_path）。
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
    with database.getDb() as db:  # 不配模型
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

Run: `uv run pytest tests/test_entry_reply_generate.py -v`（Expected: FAIL `ModuleNotFoundError`）

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

- [ ] **Step 4: 导出 + 中性位置定义低落标签**

`core/prompts/__init__.py` 追加 `from down_note.core.prompts.entryReply import DEFAULT_REPLY_PERSONA, ENTRY_REPLY_PROMPT`（先看现有导出风格保持一致）。
`core/prompts/analyzeMood.py` 末尾追加（供 02 信号检测引用，避免 signals 反向依赖 entryReply）：

```python
# 低落族标签集合（v0.3.0 02 信号检测用）：与上文清单的低落族保持同步
LOW_LABELS = {"低落", "难过", "失落", "沮丧", "空虚", "麻木"}
```

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

Run: `uv run pytest tests/test_entry_reply_generate.py -v`（Expected: 4 passed）

- [ ] **Step 7: 挂分析管线尾**（`analysis.py`）

`analyzeEntry` 末尾（`_publishAnalyzeState(entryId, models.ANALYZE_DONE)` 之后、`return result` 之前）追加：

```python
    # 条目回应（v0.3.0 01）：分析成功的当天条目，异步留一两句；内部静默容错
    if entry.kind == "entry":
        try:
            entryReply.generateEntryReply(entryId)
        except Exception:
            logger.exception("条目回应步骤异常（条目 %s）", entryId)
```

头部 import 区加 `from down_note.core import entryReply`（与 `from down_note.core import crisis` 同组）。`entry` 变量在第一个 `with database.getDb()` 块已取（`expire_on_commit=False`），`entry.kind` 可用。

- [ ] **Step 8: 全量回归 + 提交**

Run: `uv run pytest -q`（Expected: 123 + 4 + 4 passed）
```bash
git add src/down_note/core/ tests/test_entry_reply_generate.py
git commit -m "功能：v0.3.0 01 条目回应生成链路（提示词 + 管线尾部异步生成）"
```

---

### Task 1.3: 回应 API（读 + 「聊聊」转移 + 列表序列化）

**Files:**
- Modify: `src/down_note/api/entries.py`
- Test: `tests/test_entry_reply_api.py`

「聊聊」是零模型调用的纯转移。**幂等分支必须校验目标会话仍存在**（总纲：会话删除后回应保留、「聊聊」回到可点状态）——`session_message_id` 无指向会话的外键，会话被物理删除后该字段不会清空，不校验会把用户带到已消失的空会话。

- [ ] **Step 1: 写失败测试**（隔离靠 conftest；种子与断言用无参 `getDb()`）

```python
# tests/test_entry_reply_api.py
"""条目回应接口（v0.3.0 01）：聊聊转移幂等、会话删除后恢复、404。

隔离由 tests/conftest.py 的 autouse 夹具 isolateDataDir 保证；本文件不另设 monkeypatch——
不存在 database.DEFAULT_DB_PATH 这个常量。种子与断言都用无参 getDb()，与 app 同库。
"""
import pytest
from fastapi.testclient import TestClient

from down_note.app import app
from down_note.db import database, models


@pytest.fixture()
def client(dbFile):  # dbFile 建好隔离库；app 与种子同库
    return TestClient(app)


def _seed() -> int:
    with database.getDb() as db:
        entryId = models.addEntry(db, "今天有点撑不住。", None, "2026-10-13T15:42:00")
        models.createEntryReply(db, entryId, "撑不住就先靠一下。")
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

Run: `uv run pytest tests/test_entry_reply_api.py -v`（Expected: FAIL 404 路由不存在）

- [ ] **Step 3: 实现**（`api/entries.py`）

`EntryRead` 之后加读模型；`EntryRead` 加 `reply: ReplyRead | None = None`：

```python
class ReplyRead(BaseModel):
    replyText: str
    createdAt: str
    sessionId: str | None
    transferred: bool
```

新增 `replyToRead` 并改造 `entryToRead` 加可选 `db` 参：

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

`listEntries` 改 `return [entryToRead(entry, db) for entry in entries]`（其余调用点不传 db，回应为 None——updateEntry/reanalyzeEntry 返回的 reply 恒 null 属可接受取舍，前端靠 reply SSE 兜底）。

新增转移端点（放 `getEntryMood` 附近；`broker`、`uuid` 文件已 import）：

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

- [ ] **Step 4: 跑测试确认通过**

Run: `uv run pytest tests/test_entry_reply_api.py -v`（Expected: 3 passed）

- [ ] **Step 5: 全量回归 + 提交**

Run: `uv run pytest -q`
```bash
git add src/down_note/api/entries.py tests/test_entry_reply_api.py
git commit -m "功能：v0.3.0 01 回应读取与「聊聊」转移接口（幂等 + 会话删除恢复）"
```

---

### Task 1.4: 回应设置开关（独立，默认开启）

**Files:**
- Modify: `src/down_note/api/settings.py`、`frontend/src/api/types.ts`、`frontend/src/api/settings.ts`
- Test: `tests/test_settings_reply_toggle.py`

- [ ] **Step 1: 写失败测试**（隔离靠 conftest `dbFile`）

```python
# tests/test_settings_reply_toggle.py
"""日记回应开关（v0.3.0 01）：默认开启、可关、读回。

隔离由 conftest 的 isolateDataDir 保证；不 monkeypatch database.DEFAULT_DB_PATH（不存在）。
"""
import pytest
from fastapi.testclient import TestClient

from down_note.app import app


@pytest.fixture()
def client(dbFile):
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

Run: `uv run pytest tests/test_settings_reply_toggle.py -v`（Expected: FAIL KeyError）

- [ ] **Step 3: 实现**（`api/settings.py`）——`CompanionSettingsRead` 加 `diaryReplyEnabled: bool`；`CompanionSettingsWrite` 加 `diaryReplyEnabled: bool = True`；`getCompanionSettings` 读库块内加 `diaryReplyEnabled = models.getSetting(db, "diary_reply_enabled") != "0"` 并传入返回；`saveCompanionSettings` 写库块内加 `models.setSetting(db, "diary_reply_enabled", "1" if body.diaryReplyEnabled else "0")`。

- [ ] **Step 4: 前端类型与接口**——`types.ts` 的 `CompanionSettings` 加 `diaryReplyEnabled: boolean`；`settings.ts` 的 `saveCompanionSettings` 签名改 `(enabled, tier, diaryReplyEnabled)`，body 加 `diaryReplyEnabled`。

- [ ] **Step 5: 测试 + 构建 + 提交**

Run: `uv run pytest tests/test_settings_reply_toggle.py -v`（2 passed）；`uv run pytest -q`；`cd frontend && npm run build`
```bash
git add src/down_note/api/settings.py frontend/src/api/types.ts frontend/src/api/settings.ts tests/test_settings_reply_toggle.py
git commit -m "功能：v0.3.0 01 日记回应开关（默认开启，存 settings）"
```

---

### Task 1.5: 前端回应卡片 + 「聊聊」跳转 + 设置页

**Files:**
- Create: `frontend/src/components/diary/EntryReplyCard.vue`
- Modify: `frontend/src/components/diary/EntryCard.vue`、`TodayEntryCard.vue`、`DiaryPanel.vue`、`frontend/src/components/settings/CompanionSettingsPage.vue`、`frontend/src/api/entries.ts`、`frontend/src/api/types.ts`

导航用 `requestOpenSession`（appState.ts:71 真实导出，置 pendingSessionId + 切工作台），不是 `openSessionChat`。

- [ ] **Step 1: 类型与 API**——`types.ts` 加 `ReplyItem{replyText,createdAt,sessionId,transferred}`；`EntryItem` 加 `reply: ReplyItem | null`。`entries.ts` 加：

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

- [ ] **Step 3: 嵌进两个条目卡**——`EntryCard.vue` 与 `TodayEntryCard.vue` 在心情记录块后各加 `<EntryReplyCard v-if="entry.reply" :reply="entry.reply" @chat="emit('chat', entry.id)" />`；并 import + `defineEmits` 加 `chat: [entryId: number]`。

- [ ] **Step 4: DiaryPanel 接 SSE 与跳转**——`onEvent` 加 `if (e.type === 'reply')` 分支重拉当前条目列表（调用 DiaryPanel 现有刷新函数）使 `entry.reply` 到位；新增 `onReplyChat`：

```typescript
import { chatAboutReply } from '../../api'
import { requestOpenSession, switchView } from '../../stores/appState'

async function onReplyChat(entryId: number): Promise<void> {
  try {
    const result = await chatAboutReply(entryId)
    if (result.sessionId) requestOpenSession(result.sessionId)
    else switchView('workbench')
  } catch { /* 静默，按钮可重试 */ }
}
```

模板两个卡片组件上加 `@chat="onReplyChat"`。

- [ ] **Step 5: 设置页加开关**——`CompanionSettingsPage.vue` 在「主动陪伴」行后加「日记回应」行（ToggleSwitch + 提示文案）；script 加 `diaryReplyEnabled = ref(true)`、onMounted 回填、`onReplyToggle`（置值 + `void persist()`）、`persist` 里 `saveCompanionSettings(enabled.value, tier.value, diaryReplyEnabled.value)`。

- [ ] **Step 6: 构建 + 提交**

Run: `cd frontend && npm run build`（成功）；`uv run pytest -q`（无回归）
```bash
git add frontend/src/
git commit -m "功能：v0.3.0 01 前端回应卡片 + 聊聊跳转 + 设置开关"
```

---

## Self-Review

- **覆盖**：数据层(1.1)、生成(1.2)、API(1.3)、开关(1.4)、前端(1.5) 五段覆盖总纲 01 全部决策。
- **占位**：无 TBD；Step 1.5-4 的「DiaryPanel 现有刷新函数」以代码实际函数名为准（有意保留的对照点）。
- **类型一致**：`createEntryReply/getReplyByEntry/markReplyTransferred`（1.1→1.2/1.3）、`generateEntryReply(entryId)` 无 dbPath 参（1.2 定义=调用）、`ReplyRead`/`ReplyItem` 字段前后端一致、`diaryReplyEnabled`（1.4 后端→1.5 前端）一致。
- **已修订**：测试隔离用 conftest（无 DEFAULT_DB_PATH）；导航用 `requestOpenSession`；聊聊幂等校验会话存在；`LOW_LABELS` 在 analyzeMood 中性位置。
