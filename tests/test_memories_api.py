"""长期记忆接口测试：用户侧增删改查、输入校验、与智能体侧共用同一张表。

对应模块：docx/v0.1.0/modules/09-整合与降级.md
"""

from fastapi.testclient import TestClient

from down_note.agent.context import buildMemoriesText
from down_note.app import createApp
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
