"""条目回应：一条目一回应（日记的附属留言，不进会话）。

回应是条目的附属物，与会话体系解耦——删除会话不动它；
「聊聊」转移后记录目标会话与消息 id（会话被删由接口层校验后重转移）。
对应开发文档：docx/v0.3.0/modules/01-日记回应.md
"""

from datetime import datetime

from sqlalchemy import ForeignKey, String, Text, select
from sqlalchemy.exc import IntegrityError
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
    try:
        db.flush()
    except IntegrityError:
        # 并发下另一任务已穿过上面的检查并抢先落库：让位（唯一约束是最后一道闸）
        db.rollback()
        return None
    return reply


def getReplyByEntry(db: Session, entryId: int) -> EntryReply | None:
    return db.scalar(select(EntryReply).where(EntryReply.entry_id == entryId))


def getRepliesByEntries(db: Session, entryIds: list[int]) -> dict[int, EntryReply]:
    """一次取回多条条目的回应，键为 entryId（列表装配用，避免逐条查询）。"""
    if not entryIds:
        return {}
    rows = db.scalars(select(EntryReply).where(EntryReply.entry_id.in_(entryIds))).all()
    return {row.entry_id: row for row in rows}


def markReplyTransferred(db: Session, replyId: int, sessionId: str, messageId: int) -> None:
    reply = db.get(EntryReply, replyId)
    if reply is None:
        return
    reply.session_id = sessionId
    reply.session_message_id = messageId
