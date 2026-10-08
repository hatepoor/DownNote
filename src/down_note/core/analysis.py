"""分析管线：日记条目 → 心情记录（标签 + 强度 1-10 + 一句话摘要）。

调用链：buildChatModel（agent/llm.py 工厂，analysis 档：不开启思考）→ 非流式 → JSON 校验 → 落库。
失败语义（不制造焦虑）：模型未配置 → 静默跳过（降级，保持 pending 不置 failed）；
不可用 / 两次非法 / 超出总预算 → 落 failed（界面显示「分析失败」+ 刷新，兜底扫描随后重试）；
正文在分析期间被改 → 丢弃本次结果并回 pending。
对应开发文档：docx/v0.1.0/modules/05-分析管线.md、docx/v0.1.2/modules/02-分析提速.md
"""

import json
import logging
import time
from dataclasses import dataclass
from datetime import datetime

from langchain_core.messages import AIMessage, HumanMessage, SystemMessage

from down_note import config
from down_note.agent import llm
from down_note.core import crisis
from down_note.core.events import ENTRY_EVENTS_CHANNEL, broker
from down_note.core.prompts import ANALYZE_MOOD_PROMPT
from down_note.db import database, models

logger = logging.getLogger(__name__)

RETRY_GUIDANCE = "上一次输出不是合法 JSON。请严格按照约定只输出一个 JSON 对象，不要任何多余文字。"

# 生成链路总时间预算：超出即落 failed——分析不再长时间挂着
ANALYSIS_TOTAL_BUDGET_SECONDS = 90.0


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


def _publishAnalyzeState(entryId: int, state: str) -> None:
    """推送分析状态：前端据此即时刷新，无需轮询（无订阅者时事件自然消散）。"""
    broker.publish(
            ENTRY_EVENTS_CHANNEL,
            {"type": "analysis", "entryId": entryId, "analyzeState": state},
        )


def _failAnalysis(entryId: int, reason: str) -> None:
    """失败收口：落 failed（界面显示「分析失败」+ 刷新；兜底扫描随后会再试）。"""
    logger.warning("条目 %s 分析失败：%s", entryId, reason)
    with database.getDb() as db:
        models.setAnalyzeState(db, entryId, models.ANALYZE_FAILED)
    _publishAnalyzeState(entryId, models.ANALYZE_FAILED)


def analyzeEntry(entryId: int) -> MoodResult | None:
    """分析单条日记并落库；返回 None 表示本次未产出。

    未产出四情形：未配置（降级，保持 pending 不置 failed）、认领失败（已有任务在跑）、
    模型不可用 / 两次非法 / 超出总预算（落 failed）、正文在分析期间被改（丢弃结果回 pending）。
    """
    with database.getDb() as db:
        entry = models.getEntry(db, entryId)
        if entry is None or entry.analyze_state == models.ANALYZE_DONE:
            return None
        cfg = config.getModelServiceConfig(db)
        if not cfg.isConfigured():
            return None  # 降级：不置 failed，配置恢复后由兜底扫描处理
        if not models.claimForAnalysis(db, entryId):
            return None  # 已有任务在跑，本次让位
        content, imagePath = entry.content, entry.image_path
        claimedVersion = (entry.content, entry.created_at)

    messages = _buildMessages(content, imagePath)
    deadline = time.monotonic() + ANALYSIS_TOTAL_BUDGET_SECONDS
    result: MoodResult | None = None
    for _ in range(2):
        if time.monotonic() > deadline:
            _failAnalysis(entryId, "超出总时间预算")
            return None
        try:
            raw = llm.invokeModel(cfg, messages, profile=llm.PROFILE_ANALYSIS)
        except (llm.ModelConfigError, llm.ModelUnavailableError):
            _failAnalysis(entryId, "模型服务不可用")
            return None
        try:
            result = _parseMoodJson(raw)
            break
        except (ValueError, KeyError):
            messages = messages + [
                    AIMessage(content=raw),
                    HumanMessage(content=RETRY_GUIDANCE),
                ]

    if result is None:
        _failAnalysis(entryId, "两次输出均为非法 JSON")
        return None
    # 危机判定评条目原文（两级：初筛 + 复判），而非 20 字摘要——摘要可能丢信号
    result.crisis = crisis.assessEntryText(content, cfg)
    with database.getDb() as db:
        current = models.getEntry(db, entryId)
        if current is None or (current.content, current.created_at) != claimedVersion:
            models.setAnalyzeState(db, entryId, models.ANALYZE_PENDING)
            discarded = True  # 正文已变：丢弃本次结果，交给针对最新正文的任务
        else:
            discarded = False
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
            models.setAnalyzeState(db, entryId, models.ANALYZE_DONE)
    # 状态事件在事务提交后推送——避免前端先收到事件、却读到未提交的旧状态
    if discarded:
        _publishAnalyzeState(entryId, models.ANALYZE_PENDING)
        return None
    _publishAnalyzeState(entryId, models.ANALYZE_DONE)
    return result
