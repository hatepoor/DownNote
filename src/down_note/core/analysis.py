"""分析管线：日记条目 → 心情记录（标签 + 强度 1-10 + 一句话摘要）。

调用链：buildChatModel（agent/llm.py 工厂）→ 非流式 → JSON 校验 → 落库。
失败语义（不制造焦虑）：模型未配置/不可用 → 静默跳过，条目保持 analyzed=0，
由兜底扫描收口；输出非法 → 带修正提示重试一次，仍失败则跳过。
对应开发文档：docx/v0.1.0/modules/05-分析管线.md
"""

import json
from dataclasses import dataclass
from datetime import datetime

from langchain_core.messages import AIMessage, HumanMessage, SystemMessage

from down_note import config
from down_note.agent import llm
from down_note.core import crisis
from down_note.core.prompts import ANALYZE_MOOD_PROMPT
from down_note.db import database, models

RETRY_GUIDANCE = "上一次输出不是合法 JSON。请严格按照约定只输出一个 JSON 对象，不要任何多余文字。"


@dataclass
class MoodResult:
    labels: list[str]
    intensity: int
    summary: str
    crisis: bool


def _parseMoodJson(raw: str) -> MoodResult:
    data = json.loads(llm.stripCodeFence(raw))
    labels = data.get("labels")
    intensity = data.get("intensity")
    summary = data.get("summary")
    if not isinstance(labels, list) or not labels or not all(isinstance(x, str) and x.strip() for x in labels):
        raise ValueError("labels 必须是非空字符串数组")
    if isinstance(intensity, bool) or not isinstance(intensity, int) or not 1 <= intensity <= 10:
        raise ValueError("intensity 必须是 1-10 的整数")
    if not isinstance(summary, str):
        raise ValueError("summary 必须是字符串")
    # crisis 由 analyzeEntry 对条目原文做两级判定后覆盖，此处恒 False
    return MoodResult(
            labels=[x.strip() for x in labels][:3],
            intensity=intensity,
            summary=summary.strip(),
            crisis=False,
        )


def _buildMessages(content: str, imagePath: str | None) -> list:
    messages: list = [SystemMessage(content=ANALYZE_MOOD_PROMPT)]
    if imagePath:
        messages.append(llm.buildImageMessage(content, config.getImagesDir() / imagePath))
    else:
        messages.append(HumanMessage(content=content))
    return messages


def analyzeEntry(entryId: int) -> MoodResult | None:
    """分析单条日记并落库；返回 None 表示本次未产出（未配置/不可用/两次非法）。"""
    with database.getDb() as db:
        entry = models.getEntry(db, entryId)
        if entry is None or entry.analyzed:
            return None
        cfg = config.getModelServiceConfig(db)
        if not cfg.isConfigured():
            return None  # 降级：不构造多模态载荷，条目保持 analyzed=0 等兜底

    messages = _buildMessages(entry.content, entry.image_path)
    result: MoodResult | None = None
    for _ in range(2):
        try:
            raw = llm.invokeModel(cfg, messages)
        except (llm.ModelConfigError, llm.ModelUnavailableError):
            return None  # 服务问题不业务重试：SDK 层已重试过，跳过等兜底
        try:
            result = _parseMoodJson(raw)
            break
        except (ValueError, KeyError):
            messages = messages + [
                    AIMessage(content=raw),
                    HumanMessage(content=RETRY_GUIDANCE),
                ]

    if result is None:
        return None
    # 危机判定评条目原文（两级：初筛 + 复判），而非 20 字摘要——摘要可能丢信号
    result.crisis = crisis.assessEntryText(entry.content, cfg)
    with database.getDb() as db:
        models.upsertMood(
                db,
                entryId=entryId,
                labels=result.labels,
                intensity=result.intensity,
                summary=result.summary,
                crisis=result.crisis,
                analyzedAt=datetime.now().isoformat(timespec="seconds"),
                model=cfg.modelName,
            )
        models.markEntryAnalyzed(db, entryId)
    return result
