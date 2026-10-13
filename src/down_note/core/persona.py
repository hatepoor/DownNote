"""人格模板：默认人格（随包，`agent/prompts/companion.py` 的 `DEFAULT_PERSONA`）
与用户自定义（数据目录 `soul.md`）的唯一读写入口。

自定义内容只替换 system prompt 的风格层，数据段与「工具与边界」固定保留（见 04 模块）；
本模块只做文件读写与校验，提示词装配在 04。
对应开发文档：docx/v0.2.0/modules/02-设置整理.md、04-人格模板.md
"""

from pathlib import Path

from sqlalchemy.orm import Session

from down_note import config
from down_note.db import models

SOUL_FILE_NAME = "soul.md"
PERSONA_ENABLED_KEY = "persona_enabled"  # settings 键：自定义人格开关（"1"/"0"）
CONTENT_MAX_LENGTH = 2000  # 去首尾空白后的字符数上限


def getSoulFile() -> Path:
    return config.getDataDir() / SOUL_FILE_NAME


def readCustomPersona() -> str:
    """soul.md 原文（strip 后）；文件不存在或纯空白视为"未自定义"。"""
    soulFile = getSoulFile()
    if not soulFile.is_file():
        return ""
    return soulFile.read_text(encoding="utf-8").strip()


def writeCustomPersona(content: str) -> None:
    getSoulFile().write_text(content.strip(), encoding="utf-8")


def isPersonaEnabled(db: Session) -> bool:
    return models.getSetting(db, PERSONA_ENABLED_KEY) == "1"


def normalizeContent(raw: str) -> str:
    """规整并校验自定义内容；超过 2000 字抛 ValueError（调用方转 400）。"""
    content = raw.strip()
    if len(content) > CONTENT_MAX_LENGTH:
        raise ValueError(f"人格内容最多 {CONTENT_MAX_LENGTH} 字，请精简后再保存")
    return content
