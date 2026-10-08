"""设置表：键值对与日整合记忆沉淀标记。

对应开发文档：docx/v0.1.0/modules/02-数据库与配置.md、docx/v0.1.2/modules/00-结构重构.md
"""

from sqlalchemy import String
from sqlalchemy.orm import Mapped, mapped_column, Session

from down_note.db.models.base import Base

DIARY_MEMORY_DONE_PREFIX = "daily_memory_done:"  # settings 键前缀：该天日记已完成记忆沉淀


class Setting(Base):
    __tablename__ = "settings"

    key: Mapped[str] = mapped_column(String, primary_key=True)
    value: Mapped[str] = mapped_column(String)


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
