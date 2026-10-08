"""长期记忆：基本信息与性格画像条目，用户可见可改可删。

对应开发文档：docx/v0.1.0/modules/07-长期记忆.md、docx/v0.1.2/modules/00-结构重构.md、
docx/v0.1.2/modules/11-记忆分类与归位.md
"""

from datetime import datetime

from sqlalchemy import CheckConstraint, select, String, Text
from sqlalchemy.orm import Mapped, mapped_column, Session

from down_note.db.models.base import Base


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


def updateLongTermMemory(
        db: Session,
        memoryId: int,
        content: str,
        updatedBy: str,
        category: str | None = None,
    ) -> bool:
    """改内容；category 给了就一并改分类（发现放错时归位，不传保持原行为）。"""
    memory = db.get(LongTermMemory, memoryId)
    if memory is None:
        return False
    memory.content = content
    if category is not None:
        memory.category = category
    memory.updated_by = updatedBy
    memory.updated_at = datetime.now().isoformat(timespec="seconds")
    return True


def deleteLongTermMemory(db: Session, memoryId: int) -> bool:
    memory = db.get(LongTermMemory, memoryId)
    if memory is None:
        return False
    db.delete(memory)
    return True
