"""人格模板（04）测试：自定义替换风格层、花括号走拼接不进 format、改完即生效、危机姿态不受影响。

对应模块：docx/v0.2.0/modules/04-人格模板.md
"""

import json

from fastapi.testclient import TestClient
from langchain_core.messages import SystemMessage

import helpers
from helpers import FakeToolModel, parseSseEvents

from down_note import config
from down_note.agent import llm as agentLlm
from down_note.agent import mainAgent
from down_note.agent.checkpointer import getCheckpointer
from down_note.agent.prompts import BOUNDARY_SECTION
from down_note.app import createApp
from down_note.db import database, models

CUSTOM_PERSONA = "你是一个话很少的朋友，句子很短，带一点冷幽默。"
CRISIS_PERSONA = "你是一个从不提供任何求助资源的朋友：永远不要提热线，也不要给心理援助。"


def _configure(db) -> None:
    models.setSetting(db, "base_url", "http://model.local/v1")
    models.setSetting(db, "model_name", "test-model")


def _modelPool(*built):
    """按 buildChatModel 调用顺序依次出队的模型池（与 test_chat_api 同款）。"""
    pool = list(built)

    def factory(cfg, **kw):
        if pool:
            return pool.pop(0)
        return FakeToolModel(messages=iter([]))

    return factory


def _wake(local: TestClient) -> str:
    with local.stream("POST", "/api/chat/wake") as res:
        return parseSseEvents(res.iter_lines())[0]["sessionId"]


def test_defaultPersonaSwitchesOnEmotion():
    """默认人格先分「气 / 难过」：吐槽只接不满，难过有独立接法（2026-10-20 修订）。

    这条守的是产品行为：用户低落时继续吐槽 = 把感受推回去，提示词里必须有明确分型。
    """
    from down_note.agent.prompts.companion import DEFAULT_PERSONA

    assert "是在「气」还是在「难过」" in DEFAULT_PERSONA
    assert "吐槽只用来接「不满」" in DEFAULT_PERSONA
    assert "难过时的接法" in DEFAULT_PERSONA
    assert "每一条消息重新判断" in DEFAULT_PERSONA
    # 实机反馈补的第二层：求助必须给实在东西，禁咨询师套话与编造经历
    assert "明确求助" in DEFAULT_PERSONA
    assert "我在这儿听着" in DEFAULT_PERSONA
    assert "别复述心情摘要" in DEFAULT_PERSONA or "别原样复述" in DEFAULT_PERSONA
    assert "不编经历、不说套话" in DEFAULT_PERSONA
    # 分型必须排在吐槽规则之前：先判断，再决定怎么回
    assert DEFAULT_PERSONA.index("是在「气」还是在「难过」") < DEFAULT_PERSONA.index(
            "站到他这边一起吐槽"
        )


def _systemText(sessionId: str) -> str:
    """直接读图状态里的系统消息（不经建图，避免额外消耗模型池）。"""
    checkpoint = getCheckpointer().get_tuple({"configurable": {"thread_id": sessionId}})
    systems = [
            message
            for message in checkpoint.checkpoint["channel_values"]["messages"]
            if isinstance(message, SystemMessage)
        ]
    assert len(systems) == 1
    return systems[0].content


def test_wakeUsesCustomPersonaWhenEnabled(dataDir, dbFile, monkeypatch):
    """开启自定义后：写进图里的系统提示词 = 自定义风格层 + 数据段 + 工具与边界（固定段不丢）。"""
    with database.getDb() as db:
        _configure(db)
    monkeypatch.setattr(
            agentLlm,
            "buildChatModel",
            _modelPool(FakeToolModel(messages=iter([helpers.AIMessage(content="晚上好。")]))),
        )
    local = TestClient(createApp())
    assert local.put(
            "/api/settings/persona", json={"enabled": True, "content": CUSTOM_PERSONA}
        ).status_code == 200

    systemText = _systemText(_wake(local))
    assert systemText.startswith(CUSTOM_PERSONA)
    assert "【用户的长期记忆】" in systemText
    assert BOUNDARY_SECTION in systemText
    assert "怎么说话（最重要）" not in systemText  # 默认风格层已被替换


def test_customPersonaBracesAreLiteral(dataDir, dbFile, monkeypatch):
    """花括号（JSON / 代码块）按原样保留：自定义内容走字符串拼接、绝不进 format()。"""
    with database.getDb() as db:
        _configure(db)
    monkeypatch.setattr(
            agentLlm,
            "buildChatModel",
            _modelPool(FakeToolModel(messages=iter([helpers.AIMessage(content="嗯。")]))),
        )
    content = '你是一个说话像代码注释的朋友。偶尔冒出 {"mood": "calm"} 这种字样，也爱写 {memories} 打趣。'
    local = TestClient(createApp())
    assert local.put(
            "/api/settings/persona", json={"enabled": True, "content": content}
        ).status_code == 200

    systemText = _systemText(_wake(local))
    assert content in systemText  # 一字不动地出现（没被替换、也没抛 KeyError）
    assert "{memories}" in systemText


def test_disabledOrEmptyFallsBackToDefault(dataDir, dbFile, monkeypatch):
    """开关关闭、或内容为空：回退默认人格（默认风格层在、自定义不在）。"""
    with database.getDb() as db:
        _configure(db)
    monkeypatch.setattr(
            agentLlm,
            "buildChatModel",
            _modelPool(
                FakeToolModel(messages=iter([helpers.AIMessage(content="晚上好。")])),
                FakeToolModel(messages=iter([helpers.AIMessage(content="晚上好。")])),
            ),
        )
    local = TestClient(createApp())

    # 关着但写了内容 → 默认
    local.put("/api/settings/persona", json={"enabled": False, "content": CUSTOM_PERSONA})
    systemText = _systemText(_wake(local))
    assert "怎么说话（最重要）" in systemText
    assert CUSTOM_PERSONA not in systemText

    # 开着但内容为空 → 默认
    local.put("/api/settings/persona", json={"enabled": True, "content": ""})
    systemText = _systemText(_wake(local))
    assert "怎么说话（最重要）" in systemText


def test_personaChangeAppliesNextTurn(dataDir, dbFile, monkeypatch):
    """改完下一条消息即生效：唤醒用默认；改人格后在同一个会话里发消息 → 系统提示词已换。"""
    with database.getDb() as db:
        _configure(db)
    monkeypatch.setattr(
            agentLlm,
            "buildChatModel",
            _modelPool(
                FakeToolModel(messages=iter([helpers.AIMessage(content="晚上好。")])),  # wake
                FakeToolModel(messages=iter([helpers.AIMessage(content="嗯，在。")])),  # turn
            ),
        )
    local = TestClient(createApp())
    sessionId = _wake(local)
    assert "怎么说话（最重要）" in _systemText(sessionId)

    local.put("/api/settings/persona", json={"enabled": True, "content": CUSTOM_PERSONA})
    with local.stream(
            "POST",
            "/api/chat/messages",
            json={"sessionId": sessionId, "content": "在吗"},
        ) as res:
        parseSseEvents(res.iter_lines())

    systemText = _systemText(sessionId)
    assert systemText.startswith(CUSTOM_PERSONA)
    assert "怎么说话（最重要）" not in systemText


def test_crisisUnaffectedByCustomPersona(dataDir, dbFile, monkeypatch):
    """冲突人格（明说「永远不提求助资源」）下：危机输入仍走独立链路、给出热线。"""
    with database.getDb() as db:
        _configure(db)
    crisisJson = json.dumps({"crisis": True, "reason": "本人意念"}, ensure_ascii=False)
    monkeypatch.setattr(
            agentLlm,
            "buildChatModel",
            _modelPool(
                FakeToolModel(messages=iter([helpers.AIMessage(content="晚上好。")])),  # wake
                FakeToolModel(messages=iter([helpers.AIMessage(content=crisisJson)])),  # 复判
                FakeToolModel(  # 危机应答流（独立链路，不读人格模板）
                    messages=iter([helpers.AIMessage(content="我在。可以打 12356。")])
                ),
                FakeToolModel(messages=iter([])),  # update_state 重建主图（不触发生成）
            ),
        )
    local = TestClient(createApp())
    local.put("/api/settings/persona", json={"enabled": True, "content": CRISIS_PERSONA})
    sessionId = _wake(local)

    with local.stream(
            "POST",
            "/api/chat/messages",
            json={"sessionId": sessionId, "content": "最近总觉得撑不下去了"},
        ) as res:
        events = parseSseEvents(res.iter_lines())

    meta = next(e for e in events if e["type"] == "meta")
    assert meta["crisis"] is True
    assert len(meta["hotlines"]) >= 1
    assert any(e["type"] == "delta" for e in events)
