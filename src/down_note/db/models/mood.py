"""心情记录：条目分析产出的标签、强度与摘要，一条目一记录。

对应开发文档：docx/v0.1.0/modules/02-数据库与配置.md、docx/v0.1.2/modules/00-结构重构.md
"""

import json

from sqlalchemy import CheckConstraint, ForeignKey, select, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship, Session

from down_note.db.models.base import Base
from down_note.db.models.entry import Entry


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


def clearMood(db: Session, entryId: int) -> None:
    """删除某条目的心情记录（改过正文后旧记录作废）。"""
    mood = db.scalar(select(Mood).where(Mood.entry_id == entryId))
    if mood is not None:
        db.delete(mood)


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


def listRecentMoods(db: Session, limit: int = 20) -> list[tuple[str, Mood]]:
    rows = db.execute(
            select(Entry.created_at, Mood)
            .join(Mood, Mood.entry_id == Entry.id)
            .order_by(Entry.created_at.desc(), Mood.id.desc())
            .limit(limit)
        ).all()
    return [(created_at, mood) for created_at, mood in rows]
