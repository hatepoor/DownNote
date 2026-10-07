"""模型接口测试：工厂构建、正常/流式调用、错误翻译、未配置判定。

对应模块：docx/v0.1.0/modules/03-模型接口.md
"""

import httpx
import openai
import pytest
from langchain_core.language_models import FakeListChatModel
from langchain_core.messages import AIMessage

from down_note.agent import llm
from down_note.config import ModelServiceConfig

CFG = ModelServiceConfig(baseUrl="http://model.local/v1", apiKey="sk-test", modelName="test-model")


class _BrokenModel(FakeListChatModel):
    """invoke 即抛连接错误的假模型。"""

    def _call(self, messages, stop=None, run_manager=None, **kwargs):
        raise httpx.ConnectError("连接被拒")


class _AuthBrokenModel(FakeListChatModel):
    """invoke 即抛鉴权失败的假模型。"""

    def _call(self, messages, stop=None, run_manager=None, **kwargs):
        request = httpx.Request("POST", "http://model.local/v1/chat/completions")
        raise openai.AuthenticationError(
                "bad key", response=httpx.Response(401, request=request), body=None
            )


def test_buildChatModelReturnsConfiguredInstance():
    model = llm.buildChatModel(CFG)
    assert model.model_name == "test-model"
    assert model.openai_api_base == "http://model.local/v1"


def test_buildChatModelUsesConfiguredGenerationParams():
    model = llm.buildChatModel(CFG)
    assert model.temperature == 1.1
    assert model.reasoning_effort == "low"

    quiet = ModelServiceConfig(
            baseUrl="http://model.local/v1",
            modelName="m",
            temperature=0.7,
            reasoningEffort="",
        )
    quietModel = llm.buildChatModel(quiet)
    assert quietModel.temperature == 0.7
    assert quietModel.reasoning_effort is None  # 关闭 = 不传该参数


def test_buildChatModelRaisesWhenNotConfigured():
    with pytest.raises(llm.ModelConfigError):
        llm.buildChatModel(ModelServiceConfig(baseUrl="", modelName="m"))
    with pytest.raises(llm.ModelConfigError):
        llm.buildChatModel(ModelServiceConfig(baseUrl="http://x", modelName=""))


def test_invokeModelReturnsText(monkeypatch):
    monkeypatch.setattr(llm, "buildChatModel", lambda cfg, **kw: FakeListChatModel(responses=["你好呀"]))
    assert llm.invokeModel(CFG, [{"role": "user", "content": "hi"}]) == "你好呀"


def test_invokeModelRetriesWithoutPenaltiesOnEmpty(monkeypatch):
    # 空回复（推理模型 + 惩罚参数兼容性问题）→ 去惩罚参数重试一次
    model = FakeListChatModel(responses=["", "正文在此"])
    monkeypatch.setattr(llm, "buildChatModel", lambda cfg, **kw: model)
    assert llm.invokeModel(CFG, [{"role": "user", "content": "hi"}]) == "正文在此"


def test_invokeModelTranslatesHttpxError(monkeypatch):
    monkeypatch.setattr(llm, "buildChatModel", lambda cfg, **kw: _BrokenModel(responses=[]))
    with pytest.raises(llm.ModelUnavailableError):
        llm.invokeModel(CFG, [])


def test_invokeModelTranslatesOpenaiAuthError(monkeypatch):
    monkeypatch.setattr(llm, "buildChatModel", lambda cfg, **kw: _AuthBrokenModel(responses=[]))
    with pytest.raises(llm.ModelUnavailableError):
        llm.invokeModel(CFG, [])


def test_streamModelYieldsText(monkeypatch):
    monkeypatch.setattr(llm, "buildChatModel", lambda cfg, **kw: FakeListChatModel(responses=["你好"]))
    assert list(llm.streamModel(CFG, [{"role": "user", "content": "hi"}])) == ["你", "好"]


def test_streamModelRetriesWithoutPenaltiesOnEmpty(monkeypatch):
    # 第一次流式产出为空（FakeListChatModel 的空响应会消耗游标），重试换第二个模型
    models_iter = iter([FakeListChatModel(responses=[""]), FakeListChatModel(responses=["正文"])])
    monkeypatch.setattr(llm, "buildChatModel", lambda cfg, **kw: next(models_iter))
    assert list(llm.streamModel(CFG, [{"role": "user", "content": "hi"}])) == ["正", "文"]


def test_streamModelFallsBackToNonStreamAfterEmptyStreams(monkeypatch):
    # 终极兜底：两次流式均零产出 → 非流式一次性产出全文（推理模式 + 流式的端点缺陷）
    models_iter = iter([
        FakeListChatModel(responses=[""]),
        FakeListChatModel(responses=[""]),
        FakeListChatModel(responses=["完整正文"]),
    ])
    monkeypatch.setattr(llm, "buildChatModel", lambda cfg, **kw: next(models_iter))
    assert list(llm.streamModel(CFG, [{"role": "user", "content": "hi"}])) == ["完整正文"]


def test_messageTextHandlesMultimodalContent():
    message = AIMessage(content=[
            {"type": "text", "text": "图"},
            {"type": "image_url", "image_url": {"url": "data:image/png;base64,x"}},
            {"type": "text", "text": "文混合"},
        ])
    assert llm.messageText(message) == "图文混合"
