"""对话会话：开始时间、最近活跃时间与上次记忆维护时间。

对应开发文档：docx/v0.1.0/modules/02-数据库与配置.md、docx/v0.1.2/modules/00-结构重构.md
"""

from sqlalchemy import select, String
from sqlalchemy.orm import Mapped, mapped_column, Session

from down_note.db.models.base import Base


class ChatSession(Base):
    __tablename__ = "sessions"

    session_id: Mapped[str] = mapped_column(String, primary_key=True)
    started_at: Mapped[str] = mapped_column(String)
    last_active_at: Mapped[str] = mapped_column(String)
    memory_maintained_at: Mapped[str | None] = mapped_column(String, default=None)


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


def listRecentSessions(db: Session, limit: int = 20) -> list[ChatSession]:
    return list(
            db.execute(
                    select(ChatSession).order_by(ChatSession.last_active_at.desc()).limit(limit)
                )
            .scalars()
            .all()
        )
