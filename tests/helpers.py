"""测试共享工具：支持 bind_tools 的假模型、tool_call 消息构造、SSE 解析。"""

import json

from langchain_core.language_models import GenericFakeChatModel
from langchain_core.messages import AIMessage


class FakeToolModel(GenericFakeChatModel):
    """GenericFakeChatModel 不实现 bind_tools；测试用直接返回自身。"""

    def bind_tools(self, tools, **kwargs):
        return self


def toolCall(name: str, args: dict, callId: str) -> AIMessage:
    return AIMessage(
            content="",
            tool_calls=[{"name": name, "args": args, "id": callId, "type": "tool_call"}],
        )


def parseSseEvents(lines) -> list[dict]:
    events = []
    for line in lines:
        if isinstance(line, bytes):
            line = line.decode("utf-8")
        if line.startswith("data: "):
            events.append(json.loads(line[len("data: "):]))
    return events
