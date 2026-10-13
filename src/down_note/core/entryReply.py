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


def _buildPrompt(
        content: str,
        labels: list[str],
        intensity: int,
        summary: str,
        persona: str,
    ) -> str:
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
