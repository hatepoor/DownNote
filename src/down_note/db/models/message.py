"""对话消息：会话 id + 角色 + 正文，按会话与时间索引。

对应开发文档：docx/v0.1.0/modules/02-数据库与配置.md、docx/v0.1.2/modules/00-结构重构.md、
docx/v0.2.0/modules/03-会话删除.md
"""

from sqlalchemy import CheckConstraint, delete, Index, select, String, Text
from sqlalchemy.orm import Mapped, mapped_column, Session

from down_note.db.models.base import Base


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


def firstUserMessage(db: Session, sessionId: str) -> str | None:
    return db.scalar(
            select(Message.content)
            .where(Message.session_id == sessionId, Message.role == "user")
            .order_by(Message.id.asc())
            .limit(1)
        )


def deleteSessionMessages(db: Session, sessionId: str) -> int:
    """物理删除该会话的全部消息（会话删除用；幂等，返回删除行数）。"""
    result = db.execute(delete(Message).where(Message.session_id == sessionId))
    return result.rowcount or 0


def hasUserMessageSince(db: Session, sinceIso: str) -> bool:
    """since 之后是否有用户消息——主动陪伴「未回退避」的"回了"判据（表四）。

    消息时间存 ISO 字符串、同格式可比；任一会话里发言都算（只打开通知不算）。
    """
    return (
            db.scalar(
                    select(Message.id)
                    .where(Message.role == "user", Message.created_at > sinceIso)
                    .limit(1)
                )
            is not None
        )
