"""危机信号判定：关键词初筛（纯本地、可离线测）+ LLM 复判。

两级流水线：初筛负责"绝不漏"（宽词表、零成本），复判负责"不误伤"（语境辨认）。
应对姿态见 ADR-0003：先共情接住，再温和提供求助资源，不评判、不中断、不上报。
对应开发文档：docx/v0.1.0/modules/06-危机应对.md
"""

import json
import logging
from pathlib import Path
from typing import TYPE_CHECKING

from langchain_core.messages import HumanMessage, SystemMessage

from down_note import config
from down_note.agent import llm
from down_note.core.prompts import CRISIS_ASSESS_PROMPT

if TYPE_CHECKING:
    from down_note.config import ModelServiceConfig

logger = logging.getLogger(__name__)

# 初筛词表：宁敏感勿遗漏（ADR-0003）。子串匹配即可，误报由 LLM 复判兜底；
# 词表必须保持可离线测试（不依赖任何模型）。
CRISIS_KEYWORDS: tuple[str, ...] = (
    # 自伤行为
    "自残", "自伤", "割腕", "划伤自己", "伤害自己", "打自己", "撞墙", "掐自己",
    # 自杀意念与计划
    "自杀", "轻生", "想死", "不想活", "活不下去", "活着的意义", "了结",
    "结束生命", "结束自己", "跳楼", "跳桥", "吞药", "安眠药", "遗书",
    # 绝望表达（含常见变体："撑不住""扛不住"来自真实对话验证，2026-10-06）
    "撑不下去", "撑不住", "坚持不下去了", "扛不住", "受不了了", "没有意义了", "解脱",
    # 英文兜底（用户可能夹杂英文输入）
    "suicide", "kill myself", "want to die", "self harm", "end it all",
)

RESOURCES_FILE_NAME = "hotlines.json"


def screen(text: str) -> bool:
    """纯本地初筛：文本命中任一关键词即返回 True。毫秒级、零依赖、可离线测。"""
    lowered = text.lower()
    return any(keyword in lowered for keyword in CRISIS_KEYWORDS)


def assess(text: str, cfg: "ModelServiceConfig") -> bool:
    """LLM 复判：判定文本是否表达针对"作者本人"的自伤/自杀意念、计划或行为。

    转述新闻、他人经历、文艺引用 → 非危机；拿不准 → 保守判危机。
    复判失败（服务不可用等）→ 保守返回 True：词表已命中且无法排除，
    误标只是一枚安静的照顾标记，静默漏标的代价不可接受（ADR-0003）。
    """
    try:
        raw = llm.invokeModel(
                cfg,
                [
                    SystemMessage(content=CRISIS_ASSESS_PROMPT),
                    HumanMessage(content=text),
                ],
            )
        data = json.loads(llm.stripCodeFence(raw))
        return bool(data.get("crisis"))
    except (llm.ModelConfigError, llm.ModelUnavailableError, ValueError, KeyError):
        logger.warning("危机复判不可用，按保守策略标记危机")
        return True


def assessEntryText(text: str, cfg: "ModelServiceConfig") -> bool:
    """完整两级判定：初筛未命中直接 False（不调模型）；命中才走 LLM 复判。"""
    if not screen(text):
        return False
    return assess(text, cfg)


def _packagedResourcesFile() -> Path:
    return Path(__file__).resolve().parents[1] / "resources" / RESOURCES_FILE_NAME


def loadHotlines(dataDir: Path | None = None) -> list[dict]:
    """求助资源：用户数据目录同名文件存在则整体覆盖，否则读包内预置数据。"""
    candidate = (dataDir or config.getDataDir()) / RESOURCES_FILE_NAME
    source = candidate if candidate.is_file() else _packagedResourcesFile()
    data = json.loads(source.read_text(encoding="utf-8"))
    resources = data.get("resources", [])
    return [r for r in resources if r.get("name") and r.get("phone")]
