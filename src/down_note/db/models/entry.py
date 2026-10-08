"""日记条目：当天条目与整合日记（同一张表，kind 区分）+ 派生查询与整合。

对应开发文档：docx/v0.1.0/modules/02-数据库与配置.md、docx/v0.1.2/modules/00-结构重构.md、
docx/v0.1.2/modules/02-分析提速.md
"""

from datetime import datetime

from sqlalchemy import case, func, Index, select, String, Text, text, update
from sqlalchemy.orm import joinedload, Mapped, mapped_column, relationship, Session

from down_note.db.models.base import Base
from down_note.db.models.setting import DIARY_MEMORY_DONE_PREFIX, Setting

ANALYZE_PENDING = "pending"  # 待分析：新建 / 编辑后 / 重启恢复 / 降级未开始
ANALYZE_RUNNING = "running"  # 后台任务已认领、进行中
ANALYZE_FAILED = "failed"  # 最终失败：重试与总预算耗尽 / 服务不可用
ANALYZE_DONE = "done"  # 已完成并落库


class Entry(Base):
    __tablename__ = "entries"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    content: Mapped[str] = mapped_column(Text, default="")
    image_path: Mapped[str | None] = mapped_column(String, default=None)
    created_at: Mapped[str] = mapped_column(String)
    analyzed: Mapped[bool] = mapped_column(default=False)  # 兼容镜像：analyze_state == 'done'
    analyze_state: Mapped[str] = mapped_column(String, default=ANALYZE_PENDING)  # pending|running|failed|done
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


def setAnalyzeState(db: Session, entryId: int, state: str) -> None:
    """写分析状态，并同步兼容镜像 analyzed（done → True）。"""
    entry = db.get(Entry, entryId)
    if entry is None:
        return
    entry.analyze_state = state
    entry.analyzed = state == ANALYZE_DONE


def claimForAnalysis(db: Session, entryId: int) -> bool:
    """认领：pending / failed → running（条件更新，天然互斥）。

    返回 True 表示认领成功；False 表示已有任务在跑——手动刷新与兜底扫描不重复分析同一条。
    """
    result = db.execute(
            update(Entry)
            .where(Entry.id == entryId, Entry.analyze_state.in_((ANALYZE_PENDING, ANALYZE_FAILED)))
            .values(analyze_state=ANALYZE_RUNNING)
        )
    return result.rowcount == 1


def resetStaleRunning(db: Session) -> int:
    """启动恢复：上次运行遗留的 running 置回 pending。

    只在启动时调用——运行期间不重置，避免误伤进行中的任务、破坏认领互斥。
    """
    result = db.execute(
            update(Entry)
            .where(Entry.analyze_state == ANALYZE_RUNNING)
            .values(analyze_state=ANALYZE_PENDING)
        )
    return result.rowcount


def markEntryAnalyzed(db: Session, entryId: int) -> None:
    setAnalyzeState(db, entryId, ANALYZE_DONE)


def updateEntryContent(db: Session, entryId: int, content: str) -> bool:
    """改正文并置回未分析；时间更新为保存时刻（同一篇日记，id 不变、日期内容更新）。"""
    entry = db.get(Entry, entryId)
    if entry is None:
        return False
    entry.content = content
    entry.created_at = datetime.now().isoformat(timespec="seconds")
    entry.analyze_state = ANALYZE_PENDING  # 编辑后重新分析：状态不同步会把新正文卡在 done
    entry.analyzed = False
    return True


def listUnanalyzedIds(db: Session) -> list[int]:
    """待分析或上次失败的条目 id，供兜底扫描认领（含重启后遗留的 pending）。"""
    return list(
            db.execute(
                    select(Entry.id).where(
                            Entry.analyze_state.in_((ANALYZE_PENDING, ANALYZE_FAILED))
                        )
                ).scalars()
        )


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
            .where(Entry.kind == "daily", Entry.analyze_state == ANALYZE_DONE)
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
