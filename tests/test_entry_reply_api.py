"""条目回应接口（v0.3.0 01）：聊聊转移幂等、会话删除后恢复、404。

隔离由 tests/conftest.py 的 autouse 夹具 isolateDataDir 保证；本文件不另设 monkeypatch——
不存在 database.DEFAULT_DB_PATH 这个常量。种子与断言都用无参 getDb()，与 app 同库。
"""
import pytest
from fastapi.testclient import TestClient

from down_note.app import createApp
from down_note.db import database, models


@pytest.fixture()
def client(dbFile):  # dbFile 建好隔离库；app 与种子同库
    return TestClient(createApp())


def _seed() -> int:
    with database.getDb() as db:
        entryId = models.addEntry(db, "今天有点撑不住。", None, "2026-10-13T15:42:00")
        models.createEntryReply(db, entryId, "撑不住就先靠一下。")
    return entryId


def test_chat_transfer_idempotent(client):
    entryId = _seed()
    r1 = client.post(f"/api/entries/{entryId}/reply/chat")
    assert r1.status_code == 200
    first = r1.json()
    assert first["transferred"] is True and first["sessionId"]
    r2 = client.post(f"/api/entries/{entryId}/reply/chat")
    assert r2.json()["sessionId"] == first["sessionId"]  # 幂等：不重复落库
    with database.getDb() as db:
        msgs = models.listMessages(db, first["sessionId"])
    assert sum(1 for m in msgs if m.content == "撑不住就先靠一下。") == 1


def test_chat_transfer_recovers_after_session_deleted(client):
    """总纲决策：会话删除后回应保留、「聊聊」回到可点状态——再次点击应转移到新会话。"""
    entryId = _seed()
    first = client.post(f"/api/entries/{entryId}/reply/chat").json()
    with database.getDb() as db:
        models.deleteSessionMessages(db, first["sessionId"])
        models.deleteChatSession(db, first["sessionId"])  # 物理删除目标会话
    second = client.post(f"/api/entries/{entryId}/reply/chat").json()
    assert second["transferred"] is True
    assert second["sessionId"] != first["sessionId"]  # 落到新的最近活跃会话（此处为新建）
    with database.getDb() as db:
        assert db.get(models.ChatSession, second["sessionId"]) is not None


def test_chat_transfer_404(client):
    with database.getDb() as db:
        entryId = models.addEntry(db, "x", None, "2026-10-13T15:42:00")  # 无回应
    assert client.post(f"/api/entries/{entryId}/reply/chat").status_code == 404


def test_chat_transfer_injectsIntoGraph(client):
    """转移的留言必须进主图状态：只写 messages 表会出现「界面有、模型不知道」。

    用户点完「聊聊」随后问「你摸到什么」，模型却看不见那条留言——即本用例守的回归。
    """
    from langchain_core.messages import AIMessage

    from down_note.agent.checkpointer import getCheckpointer

    entryId = _seed()
    with database.getDb() as db:
        models.setSetting(db, "base_url", "http://model.local/v1")
        models.setSetting(db, "model_name", "test-model")

    first = client.post(f"/api/entries/{entryId}/reply/chat").json()
    graphConfig = {"configurable": {"thread_id": first["sessionId"]}}

    def _injectedMessages():
        checkpoint = getCheckpointer().get_tuple(graphConfig)
        return [
                message
                for message in checkpoint.checkpoint["channel_values"]["messages"]
                if isinstance(message, AIMessage) and message.content == "撑不住就先靠一下。"
            ]

    assert len(_injectedMessages()) == 1  # 进图了，下一轮模型看得见

    client.post(f"/api/entries/{entryId}/reply/chat")  # 幂等重复点击
    assert len(_injectedMessages()) == 1  # 图里不重复注入


def test_list_and_day_detail_carry_reply(client):
    """列表与某一天页面都要装配回应——日页曾漏传 db，导致历史日的回应卡片永不显示。"""
    _seed()
    listed = client.get("/api/entries").json()
    assert listed[0]["reply"] is not None
    assert listed[0]["reply"]["replyText"] == "撑不住就先靠一下。"
    detail = client.get("/api/diaries/2026-10-13").json()
    assert detail["entries"][0]["reply"] is not None
    assert detail["entries"][0]["reply"]["replyText"] == "撑不住就先靠一下。"
