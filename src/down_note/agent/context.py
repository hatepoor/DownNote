"""智能体上下文材料拼装：对话转录、长期记忆、心情记录、最近日记、系统提示词与提示词刷新。

scheduler 与各接口的 build* 函数统一收敛于此，一处维护；系统提示词在这里做三段拼装
（风格层 / 数据段 / 工具与边界）——用户自定义人格走字符串拼接、绝不进 format()（04 模块）。
对应开发文档：docx/v0.1.0/modules/08-对话Agent.md、docx/v0.2.0/modules/04-人格模板.md
"""

import json
from datetime import datetime
from typing import TYPE_CHECKING

from langchain_core.messages import RemoveMessage, SystemMessage

from down_note.agent.prompts import BOUNDARY_SECTION, COMPANION_SYSTEM_PROMPT, CONTEXT_SECTION
from down_note.core import persona
from down_note.db import database, models

if TYPE_CHECKING:
    from down_note.db.models import Entry, LongTermMemory, Message, Mood


def nowIso() -> str:
    return datetime.now().isoformat(timespec="seconds")


def todayText() -> str:
    return datetime.now().strftime("%Y年%m月%d日")


def buildTranscript(messages: list["Message"]) -> str:
    roleNames = {"user": "用户", "assistant": "它"}
    return "\n".join(f"{roleNames.get(m.role, m.role)}：{m.content}" for m in messages)


def buildMemoriesText(memories: list["LongTermMemory"]) -> str:
    categoryName = {"basic": "基本信息", "psych": "性格画像"}
    return "\n".join(f"#{m.id} [{categoryName[m.category]}] {m.content}" for m in memories)


def buildMoodsText(pairs: list[tuple[str, "Mood"]]) -> str:
    lines = []
    for createdAt, mood in pairs:
        labels = "/".join(json.loads(mood.labels))
        lines.append(f"{createdAt} {labels}（强度 {mood.intensity}）——{mood.summary}")
    return "\n".join(lines)


def buildDiariesText(entries: list["Entry"], maxCharsPerEntry: int = 200) -> str:
    """最近日记 + 心情（唤醒注入用）；正文逐条截断，日期用完整年月日避免时间歧义。"""
    blocks = []
    for entry in entries:
        line = f"{_entryTime(entry)}\n{entry.content[:maxCharsPerEntry]}"
        if entry.mood is not None:
            labels = "/".join(json.loads(entry.mood.labels))
            line += f"\n心情：{labels}（强度 {entry.mood.intensity}）——{entry.mood.summary}"
        blocks.append(line)
    return "\n\n".join(blocks)


def _entryTime(entry: "Entry") -> str:
    day = entry.created_at[:10]
    if entry.kind == "daily":
        return f"{day} 整合日记"
    return f"{day} {entry.created_at[11:16]}"


def resolvePersonaText(db) -> str:
    """当前生效的自定义人格；开关关闭或内容为空返回 ""（= 用默认人格，04 的回退）。"""
    if not persona.isPersonaEnabled(db):
        return ""
    return persona.readCustomPersona()


def buildSystemPrompt(
        memoriesText: str,
        diariesText: str,
        nowText: str,
        personaText: str = "",
    ) -> str:
    """系统提示词三段拼装：风格层（默认或用户自定义）+ 数据段 + 工具与边界。

    默认路径与 v0.1.2 定稿逐字一致（逐字校验过）；用户自定义人格**走字符串拼接、绝不进
    format()**——用户内容里出现花括号（JSON / 代码块）会把格式化炸掉（04 的结构保证）。
    """
    if personaText:
        contextSection = CONTEXT_SECTION.format(
                memories=memoriesText or "（暂无）",
                diaries=diariesText or "（还没有日记）",
                now=nowText,
            )
        return personaText + "\n" + contextSection + "\n\n" + BOUNDARY_SECTION
    return COMPANION_SYSTEM_PROMPT.format(
            memories=memoriesText or "（暂无）",
            diaries=diariesText or "（还没有日记）",
            now=nowText,
        )


def promptBlocks(
        memoriesText: str,
        diariesText: str,
        personaText: str,
    ) -> tuple[str, str, str, str]:
    """提示词快照元组（日期取当下）——快照形状只在此处定义。"""
    return memoriesText, diariesText, todayText(), personaText


# 会话 → 提示词快照：判断是否需要重建（记忆/日记即时生效 + 人格改完即生效）
_promptBlocks: dict[str, tuple[str, str, str, str]] = {}


def currentPromptBlocks() -> tuple[str, str, str, str]:
    """当前「长期记忆 + 最近日记 + 日期 + 人格」快照（提示词是否重建的比较基准）。"""
    with database.getDb() as db:
        memoriesText = buildMemoriesText(models.listLongTermMemories(db))
        diariesText = buildDiariesText(models.listEntriesWithMood(db, limit=10, offset=0))
        personaText = resolvePersonaText(db)
    return promptBlocks(memoriesText, diariesText, personaText)


def primePromptBlocks(sessionId: str, blocks: tuple[str, str, str, str]) -> None:
    """唤醒时把刚写进图里的提示词快照登记进缓存（首个回合不必白重建一次）。"""
    _promptBlocks[sessionId] = blocks


def forgetPromptBlocks(sessionId: str) -> None:
    """会话删除时丢掉快照（03 模块：删除后旧快照不得残留）。"""
    _promptBlocks.pop(sessionId, None)


def refreshSystemPrompt(graph, sessionId: str, nowText: str) -> None:
    """记忆 / 日记 / 人格有变化（或应用重启后首次）才重建系统提示并原位替换。

    稳态（无变化）不动任何消息，保持追加式与前缀缓存；
    变化时删除旧 SystemMessage 再追加新的（放回合末尾，模型以最新为准）。
    """
    blocks = currentPromptBlocks()
    if _promptBlocks.get(sessionId) == blocks:
        return
    memoriesText, diariesText, _dateText, personaText = blocks
    systemText = buildSystemPrompt(memoriesText, diariesText, nowText, personaText)
    graphConfig = {"configurable": {"thread_id": sessionId}}
    state = graph.get_state(graphConfig)
    staleIds = [
            message.id
            for message in (state.values.get("messages") or [])
            if isinstance(message, SystemMessage) and message.id
        ]
    graph.update_state(
            graphConfig,
            {"messages": [
                    *(RemoveMessage(id=messageId) for messageId in staleIds),
                    SystemMessage(content=systemText),
                ]},
        )
    _promptBlocks[sessionId] = blocks
