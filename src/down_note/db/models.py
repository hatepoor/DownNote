"""ORM 模型与数据访问函数：日记条目、心情记录、对话消息、模型配置。

SQLAlchemy 2.0 声明式映射（ADR-0006）。列名与 ORM 属性用 snake_case
（编码规范的"数据库约定字段"例外），API 层 JSON 输出再转驼峰。
表设计见 docx/v0.1.0/02-架构设计.md。
对应开发文档：docx/v0.1.0/modules/02-数据库与配置.md
"""

import json
from datetime import datetime

from sqlalchemy import case, CheckConstraint, ForeignKey, func, Index, String, Text, select, text
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship, joinedload, Session


class Base(DeclarativeBase):
    pass


class Entry(Base):
    __tablename__ = "entries"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    content: Mapped[str] = mapped_column(Text, default="")
    image_path: Mapped[str | None] = mapped_column(String, default=None)
    created_at: Mapped[str] = mapped_column(String)
    analyzed: Mapped[bool] = mapped_column(default=False)
    kind: Mapped[str] = mapped_column(String, default="entry")  # entry=当天条目 | daily=日整合日记

    mood: Mapped["Mood | None"] = relationship(
            back_populates="entry",
            uselist=False,
            cascade="all, delete-orphan",
        )

    __table_args__ = (
            Index("idx_entries_created_at", "created_at"),
            Index("idx_entries_unanalyzed", "analyzed", sqlite_where=text("analyzed = 0")),
        )


class Mood(Base):
    __tablename__ = "moods"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    entry_id: Mapped[int] = mapped_column(
            ForeignKey("entries.id", ondelete="CASCADE"),
            unique=True,
        )
    labels: Mapped[str] = mapped_column(Text)  # JSON 数组字符串
    intensity: Mapped[int] = mapped_column()
    summary: Mapped[str] = mapped_column(Text)
    crisis: Mapped[bool] = mapped_column(default=False)
    analyzed_at: Mapped[str] = mapped_column(String)
    model: Mapped[str] = mapped_column(String)

    entry: Mapped[Entry] = relationship(back_populates="mood")

    __table_args__ = (CheckConstraint("intensity BETWEEN 1 AND 10"),)


class Message(Base):
    __tablename__ = "messages"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    session_id: Mapped[str] = mapped_column(String)
    role: Mapped[str] = mapped_column(String)
    content: Mapped[str] = mapped_column(Text)
    created_at: Mapped[str] = mapped_column(String)

    __table_args__ = (
            CheckConstraint("role IN ('user', 'assistant')"),
            Index("idx_messages_session", "session_id", "created_at"),
        )


class Setting(Base):
    __tablename__ = "settings"

    key: Mapped[str] = mapped_column(String, primary_key=True)
    value: Mapped[str] = mapped_column(String)


class LongTermMemory(Base):
    __tablename__ = "long_term_memories"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    category: Mapped[str] = mapped_column(String)  # basic=基本信息 | psych=性格画像条目
    content: Mapped[str] = mapped_column(Text)  # 一句话事实，纯文本
    updated_by: Mapped[str] = mapped_column(String)  # agent | user
    created_at: Mapped[str] = mapped_column(String)
    updated_at: Mapped[str] = mapped_column(String)

    __table_args__ = (
            CheckConstraint("category IN ('basic', 'psych')"),
            CheckConstraint("updated_by IN ('agent', 'user')"),
        )


class ChatSession(Base):
    __tablename__ = "sessions"

    session_id: Mapped[str] = mapped_column(String, primary_key=True)
    started_at: Mapped[str] = mapped_column(String)
    last_active_at: Mapped[str] = mapped_column(String)
    memory_maintained_at: Mapped[str | None] = mapped_column(String, default=None)


def addEntry(db: Session, content: str, imagePath: str | None, createdAt: str) -> int:
    entry = Entry(content=content, image_path=imagePath, created_at=createdAt)
    db.add(entry)
    db.flush()
    return entry.id


def getEntry(db: Session, entryId: int) -> Entry | None:
    return db.get(Entry, entryId)


def listEntriesWithMood(db: Session, limit: int, offset: int) -> list[Entry]:
    return list(
            db.execute(
                    select(Entry)
                    .options(joinedload(Entry.mood))
                    .order_by(Entry.created_at.desc(), Entry.id.desc())
                    .limit(limit)
                    .offset(offset)
                )
            .scalars()
            .all()
        )


def markEntryAnalyzed(db: Session, entryId: int) -> None:
    entry = db.get(Entry, entryId)
    if entry is not None:
        entry.analyzed = True


def updateEntryContent(db: Session, entryId: int, content: str) -> bool:
    """改正文并置回未分析；时间更新为保存时刻（同一篇日记，id 不变、日期内容更新）。"""
    entry = db.get(Entry, entryId)
    if entry is None:
        return False
    entry.content = content
    entry.created_at = datetime.now().isoformat(timespec="seconds")
    entry.analyzed = False
    return True


def clearMood(db: Session, entryId: int) -> None:
    """删除某条目的心情记录（改过正文后旧记录作废）。"""
    mood = db.scalar(select(Mood).where(Mood.entry_id == entryId))
    if mood is not None:
        db.delete(mood)


def listUnanalyzedIds(db: Session) -> list[int]:
    return list(db.execute(select(Entry.id).where(Entry.analyzed == False)).scalars())  # noqa: E712


DIARY_MEMORY_DONE_PREFIX = "daily_memory_done:"  # settings 键前缀：该天日记已完成记忆沉淀


def addDailyEntry(db: Session, day: str, content: str) -> int:
    """创建某天的整合日记；created_at 落在当天末尾，便于按天取整与排序。"""
    entry = Entry(content=content, image_path=None, created_at=f"{day}T23:59:59", kind="daily")
    db.add(entry)
    db.flush()
    return entry.id


def mergeDayBlocks(blocks: list[tuple[str, str]]) -> str:
    """整合一天日记的正文：各条按时间序以空行相连（纯函数，日整合与格式迁移共用）。
    条目各自的心情由日页按条展示，正文里不加时间戳或分隔线。"""
    return "\n\n".join(content for _, content in blocks if content)


def getDailyEntry(db: Session, day: str) -> Entry | None:
    return db.execute(
            select(Entry).where(Entry.kind == "daily", Entry.created_at.like(f"{day}%"))
        ).scalar_one_or_none()


def listDayEntries(db: Session, day: str) -> list[Entry]:
    """某天的当天条目（不含整合日记），按时间升序；mood 预加载。"""
    return list(
            db.execute(
                    select(Entry)
                    .options(joinedload(Entry.mood))
                    .where(Entry.kind == "entry", Entry.created_at.like(f"{day}%"))
                    .order_by(Entry.created_at, Entry.id)
                )
            .scalars()
            .all()
        )


def searchEntries(db: Session, keyword: str, limit: int) -> list[Entry]:
    """按正文关键词搜索（含整合日记），时间倒序；mood 预加载。"""
    return list(
            db.execute(
                    select(Entry)
                    .options(joinedload(Entry.mood))
                    .where(Entry.content.contains(keyword, autoescape=True))
                    .order_by(Entry.created_at.desc(), Entry.id.desc())
                    .limit(limit)
                )
            .scalars()
            .all()
        )


def listEntryDays(db: Session, limit: int, offset: int) -> list[tuple[str, int]]:
    """历史按天分页：(日期, 当天条目数)，日期倒序；条目数不含整合日记。"""
    day = func.substr(Entry.created_at, 1, 10)
    rows = db.execute(
            select(day, func.sum(case((Entry.kind == "entry", 1), else_=0)))
            .group_by(day)
            .order_by(day.desc())
            .limit(limit)
            .offset(offset)
        ).all()
    return [(row[0], int(row[1] or 0)) for row in rows]


def listPastDaysMissingDigest(db: Session, today: str) -> list[str]:
    """已结束（早于今天）、有当天条目、但还没有整合日记的日期，按时间升序。"""
    day = func.substr(Entry.created_at, 1, 10)
    entryDays = db.execute(
            select(day)
            .where(Entry.kind == "entry", Entry.created_at < today)
            .group_by(day)
            .order_by(day)
        ).scalars().all()
    digestDays = set(
            db.execute(select(day).where(Entry.kind == "daily").group_by(day)).scalars().all()
        )
    return [value for value in entryDays if value not in digestDays]


def listDaysNeedingDiaryMemory(db: Session) -> list[str]:
    """已分析、但尚未完成记忆沉淀的整合日记日期，按时间升序。"""
    day = func.substr(Entry.created_at, 1, 10)
    analyzedDays = db.execute(
            select(day)
            .where(Entry.kind == "daily", Entry.analyzed.is_(True))
            .group_by(day)
            .order_by(day)
        ).scalars().all()
    doneKeys = set(
            db.execute(
                    select(Setting.key).where(Setting.key.like(f"{DIARY_MEMORY_DONE_PREFIX}%"))
                ).scalars().all()
        )
    return [
            value
            for value in analyzedDays
            if f"{DIARY_MEMORY_DONE_PREFIX}{value}" not in doneKeys
        ]


def upsertMood(
        db: Session,
        entryId: int,
        labels: list[str],
        intensity: int,
        summary: str,
        crisis: bool,
        analyzedAt: str,
        model: str,
    ) -> None:
    mood = db.scalar(select(Mood).where(Mood.entry_id == entryId))
    if mood is None:
        mood = Mood(entry_id=entryId)
        db.add(mood)
    mood.labels = json.dumps(labels, ensure_ascii=False)
    mood.intensity = intensity
    mood.summary = summary
    mood.crisis = crisis
    mood.analyzed_at = analyzedAt
    mood.model = model


def getMoodByEntry(db: Session, entryId: int) -> Mood | None:
    return db.scalar(select(Mood).where(Mood.entry_id == entryId))


def addMessage(db: Session, sessionId: str, role: str, content: str, createdAt: str) -> int:
    message = Message(session_id=sessionId, role=role, content=content, created_at=createdAt)
    db.add(message)
    db.flush()
    return message.id


def listMessages(db: Session, sessionId: str, limit: int = 200) -> list[Message]:
    latest = db.execute(
            select(Message)
            .where(Message.session_id == sessionId)
            .order_by(Message.created_at.desc(), Message.id.desc())
            .limit(limit)
        )
    return list(reversed(latest.scalars().all()))


def getSetting(db: Session, key: str) -> str | None:
    setting = db.get(Setting, key)
    return setting.value if setting is not None else None


def setSetting(db: Session, key: str, value: str) -> None:
    setting = db.get(Setting, key)
    if setting is None:
        setting = Setting(key=key, value=value)
        db.add(setting)
    else:
        setting.value = value


def listLongTermMemories(db: Session) -> list[LongTermMemory]:
    """全量加载长期记忆（category + id 排序），v0.1.0 不做检索式加载。"""
    return list(
            db.execute(
                    select(LongTermMemory).order_by(LongTermMemory.category, LongTermMemory.id)
                )
            .scalars()
            .all()
        )


def getLongTermMemory(db: Session, memoryId: int) -> LongTermMemory | None:
    return db.get(LongTermMemory, memoryId)


def addLongTermMemory(db: Session, category: str, content: str, updatedBy: str) -> int:
    now = datetime.now().isoformat(timespec="seconds")
    memory = LongTermMemory(
            category=category,
            content=content,
            updated_by=updatedBy,
            created_at=now,
            updated_at=now,
        )
    db.add(memory)
    db.flush()
    return memory.id


def updateLongTermMemory(db: Session, memoryId: int, content: str, updatedBy: str) -> bool:
    memory = db.get(LongTermMemory, memoryId)
    if memory is None:
        return False
    memory.content = content
    memory.updated_by = updatedBy
    memory.updated_at = datetime.now().isoformat(timespec="seconds")
    return True


def deleteLongTermMemory(db: Session, memoryId: int) -> bool:
    memory = db.get(LongTermMemory, memoryId)
    if memory is None:
        return False
    db.delete(memory)
    return True


def upsertChatSession(db: Session, sessionId: str, activeAt: str) -> None:
    session = db.get(ChatSession, sessionId)
    if session is None:
        db.add(ChatSession(session_id=sessionId, started_at=activeAt, last_active_at=activeAt))
    elif activeAt > session.last_active_at:
        session.last_active_at = activeAt


def listSessionsNeedingMaintenance(db: Session, now: str) -> list[str]:
    """有新消息的会话（从未维护过，或 last_active_at 晚于上次维护时间）。"""
    sessions = db.execute(select(ChatSession)).scalars().all()
    return [
            s.session_id
            for s in sessions
            if s.memory_maintained_at is None or s.last_active_at > s.memory_maintained_at
        ]


def markSessionMaintained(db: Session, sessionId: str, maintainedAt: str) -> None:
    session = db.get(ChatSession, sessionId)
    if session is not None:
        session.memory_maintained_at = maintainedAt


def listRecentMoods(db: Session, limit: int = 20) -> list[tuple[str, Mood]]:
    rows = db.execute(
            select(Entry.created_at, Mood)
            .join(Mood, Mood.entry_id == Entry.id)
            .order_by(Entry.created_at.desc(), Mood.id.desc())
            .limit(limit)
        ).all()
    return [(created_at, mood) for created_at, mood in rows]


def listRecentSessions(db: Session, limit: int = 20) -> list[ChatSession]:
    return list(
            db.execute(
                    select(ChatSession).order_by(ChatSession.last_active_at.desc()).limit(limit)
                )
            .scalars()
            .all()
        )


def firstUserMessage(db: Session, sessionId: str) -> str | None:
    return db.scalar(
            select(Message.content)
            .where(Message.session_id == sessionId, Message.role == "user")
            .order_by(Message.id.asc())
            .limit(1)
        )
