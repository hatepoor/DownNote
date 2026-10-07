"""智能体上下文材料拼装：对话转录、长期记忆、心情记录、最近日记、系统提示词。

scheduler 与各接口的 build* 函数统一收敛于此，一处维护。
对应开发文档：docx/v0.1.0/modules/08-对话Agent.md
"""

import json
from datetime import datetime
from typing import TYPE_CHECKING

from down_note.agent.prompts import COMPANION_SYSTEM_PROMPT

if TYPE_CHECKING:
    from down_note.db.models import Entry, LongTermMemory, Message, Mood


def nowIso() -> str:
    return datetime.now().isoformat(timespec="seconds")


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


def buildSystemPrompt(memoriesText: str, diariesText: str, nowText: str) -> str:
    return COMPANION_SYSTEM_PROMPT.format(
            memories=memoriesText or "（暂无）",
            diaries=diariesText or "（还没有日记）",
            now=nowText,
        )
