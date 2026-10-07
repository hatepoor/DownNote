"""ChatOpenAI 工厂：模型服务三件套 → 模型实例，统一错误归类与空回复兜底。

分析、危机复判与全部智能体共用此工厂（ADR-0005）。
ModelConfigError / ModelUnavailableError 属可降级错误，业务层捕获后进入降级模式；
其余异常视为程序 bug，不拦截。
兼容性已知问题（2026-10-06 实测）：部分推理模型（deepseek v4.1 flash）在
惩罚参数 + 触发深度思考时会返回空内容——invokeModel/streamModel 对空回复
自动去掉惩罚参数重试一次。
对应开发文档：docx/v0.1.0/modules/03-模型接口.md
"""

import base64
import json
from collections.abc import Iterator
from pathlib import Path
from typing import TYPE_CHECKING, Any

import httpx
import openai
from langchain_core.language_models.chat_models import BaseChatModel
from langchain_core.messages import BaseMessage
from langchain_openai import ChatOpenAI

if TYPE_CHECKING:
    from down_note.config import ModelServiceConfig

REQUEST_TIMEOUT_SECONDS = 60.0

# 陪伴话术的生成参数：温度与思考强度可由用户在设置里调整（config.ModelServiceConfig），
# 这里只保留固定项——偏宽核采样与轻惩罚，措辞多样不走车轱辘话
GENERATION_TOP_P = 0.95
GENERATION_PRESENCE_PENALTY = 0.6
GENERATION_FREQUENCY_PENALTY = 0.3
GENERATION_MAX_TOKENS = 5000
# 注意：推理模型（deepseek v4.1 等）的思考 token 计入 max_tokens，且思考长度波动大
# （实测 170~1600+）；正文本身约 200 token，5000 为思考留足余量（2026-10-06 议定，
# 用户拍板 800→2000→5000）。
# 思考强度走配置（reasoning_effort，OpenAI 格式）："low" 压缩思考长度，空串则不传该参数

# SDK 层瞬态错误（连接/超时/5xx/限流）自动重试上限；输出质量重试归业务层
SDK_MAX_RETRIES = 5


class ModelConfigError(Exception):
    """模型服务三件套未配置完整（缺 base_url 或 model_name），属可降级错误。"""


class ModelUnavailableError(Exception):
    """模型服务不可用（连接失败、超时、鉴权失败、HTTP 错误），属可降级错误。"""


def ensureConfigured(cfg: "ModelServiceConfig") -> None:
    missing = [name for name, value in (("base_url", cfg.baseUrl), ("model_name", cfg.modelName)) if not value]
    if missing:
        raise ModelConfigError(f"模型服务未配置，缺少：{', '.join(missing)}")


def buildChatModel(cfg: "ModelServiceConfig", *, timeout: float = REQUEST_TIMEOUT_SECONDS, withPenalties: bool = True) -> BaseChatModel:
    """三件套 → ChatOpenAI 实例。全系统模型实例的唯一来源。

    withPenalties=False 用于空回复兜底重试（见模块 docstring 的兼容性说明）。
    """
    ensureConfigured(cfg)
    params: dict = {
            "model": cfg.modelName,
            "api_key": cfg.apiKey or "EMPTY",
            "base_url": cfg.baseUrl,
            "timeout": timeout,
            "max_retries": SDK_MAX_RETRIES,
            "max_tokens": GENERATION_MAX_TOKENS,
            "temperature": cfg.temperature,
        }
    if cfg.reasoningEffort:
        params["reasoning_effort"] = cfg.reasoningEffort
    if withPenalties:
        params.update(
                top_p=GENERATION_TOP_P,
                presence_penalty=GENERATION_PRESENCE_PENALTY,
                frequency_penalty=GENERATION_FREQUENCY_PENALTY,
            )
    return ChatOpenAI(**params)


def messageText(message: BaseMessage) -> str:
    content: Any = message.content
    if isinstance(content, str):
        return content
    return "".join(part.get("text", "") for part in content if isinstance(part, dict))


def _isEmptyReply(message: BaseMessage) -> bool:
    return not messageText(message) and not getattr(message, "tool_calls", None)


def _translateModelCallError(func, *args, **kwargs):
    """执行一次模型调用，把服务类异常翻译为可降级错误。"""
    try:
        return func(*args, **kwargs)
    except (openai.APIError, httpx.HTTPError) as e:
        raise ModelUnavailableError(f"模型服务调用失败：{e}") from e


def invokeModel(cfg: "ModelServiceConfig", messages: list) -> str:
    """非流式调用，返回回复文本。空回复（推理模型兼容性）去惩罚参数重试一次。"""
    res = _translateModelCallError(lambda: buildChatModel(cfg).invoke(messages))
    if _isEmptyReply(res):
        res = _translateModelCallError(lambda: buildChatModel(cfg, withPenalties=False).invoke(messages))
    return messageText(res)


def streamModel(cfg: "ModelServiceConfig", messages: list) -> Iterator[str]:
    """流式调用，逐段产出文本增量。三级兜底：带惩罚流式 → 无惩罚流式 → 非流式。

    兜底原因（2026-10-06 实测）：部分端点在"推理模式 + 流式"下把全部 token
    放进 reasoning_content、正文恒为空且不报错——只有非流式能拿到正文。
    """

    def _drain(withPenalties: bool, producedFlag: list) -> Iterator[str]:
        model = buildChatModel(cfg, withPenalties=withPenalties)
        for chunk in model.stream(messages):
            piece = messageText(chunk)
            if piece:
                producedFlag.append(1)
                yield piece

    def _raiseIfServiceError(e: Exception) -> None:
        if isinstance(e, (openai.APIError, httpx.HTTPError)):
            raise ModelUnavailableError(f"模型服务调用失败：{e}") from e

    produced: list = []
    try:
        for text in _drain(True, produced):
            yield text
    except (openai.APIError, httpx.HTTPError, ValueError) as e:
        _raiseIfServiceError(e)
    if produced:
        return
    try:
        for text in _drain(False, produced):
            yield text
    except (openai.APIError, httpx.HTTPError, ValueError) as e:
        _raiseIfServiceError(e)
    if not produced:
        # 终极兜底：非流式。思考 token 计入预算且长度随机（实测 170~1600+），
        # 单次仍可能超限——给两次机会，连续两次超限的概率很小。
        for _ in range(2):
            res = _translateModelCallError(lambda: buildChatModel(cfg, withPenalties=False).invoke(messages))
            text = messageText(res)
            if text:
                yield text
                break


def stripCodeFence(text: str) -> str:
    """剥离模型输出可能包裹的 ```json 围栏（字符串方法实现，不用正则）。"""
    stripped = text.strip()
    if stripped.startswith("```"):
        lineBreak = stripped.find("\n")
        if lineBreak != -1:
            stripped = stripped[lineBreak + 1 :]
    if stripped.endswith("```"):
        stripped = stripped[: stripped.rfind("```")]
    return stripped.strip()


def buildImageMessage(text: str, imagePath: str | Path) -> dict:
    """文字 + 单图的多模态 user 消息（图片转 base64 data URL，原文直发 ADR-0002）。"""
    suffix = Path(imagePath).suffix.lstrip(".").lower()
    if suffix == "jpg":
        suffix = "jpeg"
    data = base64.b64encode(Path(imagePath).read_bytes()).decode("ascii")
    return {
            "role": "user",
            "content": [
                    {"type": "text", "text": text},
                    {"type": "image_url", "image_url": {"url": f"data:image/{suffix};base64,{data}"}},
                ],
        }
