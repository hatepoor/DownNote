"""长期记忆接口测试：用户侧增删改查、输入校验、与智能体侧共用同一张表、变更推送。

对应模块：docx/v0.1.0/modules/09-整合与降级.md、docx/v0.1.2/modules/10-记忆即时可见.md
"""

import asyncio

from fastapi.testclient import TestClient

from down_note.agent.context import buildMemoriesText
from down_note.api import memories as memoriesApi
from down_note.app import createApp
from down_note.core.events import MEMORY_EVENTS_CHANNEL, broker
from down_note.db import database, models


def _client() -> TestClient:
    return TestClient(createApp())


def test_memoryCrudRoundtrip(dbFile):
    client = _client()

    # 新增：updated_by 固定为 user（前端据此显示"你写的"），入库前 strip
    resp = client.post("/api/memories", json={"category": "basic", "content": " 名字是阿澈 "})
    assert resp.status_code == 201
    created = resp.json()
    assert created["category"] == "basic"
    assert created["content"] == "名字是阿澈"
    assert created["updatedBy"] == "user"
    assert created["createdAt"]

    resp = client.post("/api/memories", json={"category": "psych", "content": "习惯把心事写下来"})
    assert resp.status_code == 201

    # 列表：category 排序，basic 在前
    items = client.get("/api/memories").json()
    assert [item["category"] for item in items] == ["basic", "psych"]

    # 编辑：只改 content，来源仍落 user
    memoryId = created["id"]
    resp = client.put(f"/api/memories/{memoryId}", json={"content": "名字是阿澈，住杭州"})
    assert resp.status_code == 200
    updated = resp.json()
    assert updated["content"] == "名字是阿澈，住杭州"
    assert updated["updatedBy"] == "user"
    assert updated["category"] == "basic"  # 编辑不动类别

    # 删除：204 且列表减一
    resp = client.delete(f"/api/memories/{memoryId}")
    assert resp.status_code == 204
    items = client.get("/api/memories").json()
    assert len(items) == 1
    assert all(item["id"] != memoryId for item in items)

    # 不存在：404 兜底
    assert client.put("/api/memories/999", json={"content": "x"}).status_code == 404
    assert client.delete("/api/memories/999").status_code == 404


def test_rejectBadInput(dbFile):
    client = _client()
    assert client.post("/api/memories", json={"category": "hobby", "content": "x"}).status_code == 400
    assert client.post("/api/memories", json={"category": "basic", "content": ""}).status_code == 422
    assert client.post("/api/memories", json={"category": "basic", "content": "   "}).status_code == 400
    assert client.get("/api/memories").json() == []


def test_userEditFeedsAgentContext(dbFile):
    """用户在页面上改的，立刻进下一回合的系统提示词（对话每轮重新拼）。"""
    client = _client()
    client.post("/api/memories", json={"category": "psych", "content": "最近睡得很晚"})
    with database.getDb() as db:
        memoriesText = buildMemoriesText(models.listLongTermMemories(db))
    assert "[性格画像] 最近睡得很晚" in memoriesText


def test_updateMemoryCanRecategorize(dbFile):
    """编辑可改分类（归位用）：PUT 带 category 移动栏目；非法分类 400 且不动库。

    对应模块：docx/v0.1.2/modules/11-记忆分类与归位.md
    """
    client = _client()

    # 新增省略 category → 默认 basic（旧行为保持）
    defaulted = client.post("/api/memories", json={"content": "默认分类"})
    assert defaulted.status_code == 201
    assert defaulted.json()["category"] == "basic"

    created = client.post("/api/memories", json={"category": "basic", "content": "喜欢看漫画解说"})
    memoryId = created.json()["id"]

    # 带 category：内容与分类一并更新
    resp = client.put(
            f"/api/memories/{memoryId}",
            json={"content": "用户喜欢看漫画解说", "category": "psych"},
        )
    assert resp.status_code == 200
    assert resp.json()["category"] == "psych"
    assert resp.json()["content"] == "用户喜欢看漫画解说"

    # 省略 category：只改内容，分类不动（向后兼容）
    resp = client.put(f"/api/memories/{memoryId}", json={"content": "用户爱看漫画解说"})
    assert resp.status_code == 200
    assert resp.json()["category"] == "psych"

    # 非法分类：400 且库里不动
    bad = client.put(f"/api/memories/{memoryId}", json={"content": "x", "category": "hobby"})
    assert bad.status_code == 400
    with database.getDb() as db:
        kept = models.getLongTermMemory(db, memoryId)
        assert kept.category == "psych"
        assert kept.content == "用户爱看漫画解说"


def test_memoryEventStreamPushesChange(dataDir, dbFile):
    """记忆变更推送：向频道发布事件 → 事件流产出对应 SSE 帧（前端据此刷新，无需重启）。"""

    async def _drive() -> str:
        stream = memoriesApi.memoryEventStream()
        pending = asyncio.ensure_future(stream.__anext__())
        await asyncio.sleep(0)  # 让生成器先完成订阅
        broker.publish(MEMORY_EVENTS_CHANNEL, {"type": "memory"})
        frame = await asyncio.wait_for(pending, timeout=1)
        await stream.aclose()
        return frame

    frame = asyncio.run(_drive())
    assert frame == 'data: {"type": "memory"}\n\n'


def test_memoryWriteNotifiesFrontend(dbFile, monkeypatch):
    """写接口成功后确已通知前端：漏掉通知就退回"要重启才看得到"（2026-10-08 用户实测）。"""
    calls: list[str] = []
    monkeypatch.setattr(memoriesApi, "notifyMemoryChanged", lambda: calls.append("memory"))
    client = _client()

    created = client.post("/api/memories", json={"category": "psych", "content": "喜欢跑步"})
    assert created.status_code == 201
    memoryId = created.json()["id"]
    updated = client.put(f"/api/memories/{memoryId}", json={"content": "平时喜欢跑步"})
    assert updated.status_code == 200
    assert client.delete(f"/api/memories/{memoryId}").status_code == 204
    assert calls == ["memory", "memory", "memory"]

    # 失败路径（编号不存在）不通知
    calls.clear()
    assert client.put("/api/memories/999", json={"content": "x"}).status_code == 404
    assert client.delete("/api/memories/999").status_code == 404
    assert calls == []
