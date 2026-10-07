"""接口层测试（FastAPI TestClient + mock 模型）。

对应模块：docx/v0.1.0/modules/01-项目骨架.md（/api/health）、03-模型接口.md（配置接口）
"""

from datetime import date

from sqlalchemy import text
from fastapi.testclient import TestClient

from down_note import config
from down_note.db import database, models
from down_note.app import createApp

client = TestClient(createApp())


def test_healthReturnsOk():
    res = client.get("/api/health")
    assert res.status_code == 200
    assert res.json() == {"status": "ok"}


def test_startupCreatesSchema(dataDir):
    # 回归：真实启动链路（lifespan）必须建表，否则运行时 500
    with TestClient(createApp()) as local:
        assert local.get("/api/health").status_code == 200
    with database.getDb() as db:
        names = set(
                db.execute(
                        text("SELECT name FROM sqlite_master WHERE type = 'table'")
                    ).scalars()
            )
        assert {"entries", "moods", "messages", "settings"} <= names


def test_modelSettingsRoundtrip(dataDir, dbFile):
    local = TestClient(createApp())

    body = local.get("/api/settings/model").json()
    assert body == {
            "baseUrl": "",
            "modelName": "",
            "apiKeyMasked": "",
            "temperature": 1.1,
            "reasoningEffort": "low",
            "configured": False,
        }

    res = local.put(
            "/api/settings/model",
            json={"baseUrl": "https://api.example.com/v1", "modelName": "agent-x", "apiKey": "sk-abcdef123456"},
        )
    assert res.status_code == 200
    assert res.json() == {"ok": True}

    body = local.get("/api/settings/model").json()
    assert body["configured"] is True
    assert body["baseUrl"] == "https://api.example.com/v1"
    assert body["apiKeyMasked"] == "sk-***3456"

    # 密钥进 .env（临时数据目录），不进数据库
    assert config.getApiKey() == "sk-abcdef123456"
    with database.getDb() as db:
        assert models.getSetting(db, "api_key") is None


def test_modelSettingsGenerationParams(dataDir, dbFile):
    local = TestClient(createApp())
    res = local.put(
            "/api/settings/model",
            json={
                "baseUrl": "https://a.com",
                "modelName": "m1",
                "temperature": 0.6,
                "reasoningEffort": "",
            },
        )
    assert res.status_code == 200

    body = local.get("/api/settings/model").json()
    assert body["temperature"] == 0.6
    assert body["reasoningEffort"] == ""
    # 落库（真实生效：ModelServiceConfig 从 settings 读）
    with database.getDb() as db:
        assert config.getModelServiceConfig(db).temperature == 0.6
        assert config.getModelServiceConfig(db).reasoningEffort == ""

    # 校验：温度越界 / 思考强度非法
    assert local.put(
            "/api/settings/model",
            json={"baseUrl": "a", "modelName": "m", "temperature": 3},
        ).status_code == 400
    assert local.put(
            "/api/settings/model",
            json={"baseUrl": "a", "modelName": "m", "reasoningEffort": "max"},
        ).status_code == 400
    assert local.put(
            "/api/settings/model",
            json={"baseUrl": "a", "modelName": "m", "temperature": -0.1},
        ).status_code == 400


def test_modelSettingsPutKeepsKeyWhenBlank(dataDir, dbFile):
    local = TestClient(createApp())
    local.put(
            "/api/settings/model",
            json={"baseUrl": "https://a.com", "modelName": "m1", "apiKey": "sk-old12345678"},
        )
    local.put("/api/settings/model", json={"baseUrl": "https://b.com", "modelName": "m2", "apiKey": ""})

    assert config.getApiKey() == "sk-old12345678"
    with database.getDb() as db:
        assert models.getSetting(db, "base_url") == "https://b.com"


PNG_BYTES = b"\x89PNG\r\n\x1a\n" + b"0" * 64


def _createEntry(local, content="", files=None):
    return local.post("/api/entries", data={"content": content}, files=files)


def test_createTextEntryAndReadback(dataDir, dbFile):
    local = TestClient(createApp())
    res = _createEntry(local, content="今天有点低落")
    assert res.status_code == 200
    body = res.json()
    assert body["content"] == "今天有点低落"
    assert body["imageUrl"] is None
    assert body["analyzed"] is False

    listed = local.get("/api/entries").json()
    assert len(listed) == 1
    assert listed[0]["id"] == body["id"]


def test_createImageEntryAndFetchImage(dataDir, dbFile):
    local = TestClient(createApp())
    res = _createEntry(local, content="带图的一天", files={"image": ("a.png", PNG_BYTES, "image/png")})
    assert res.status_code == 200
    imageUrl = res.json()["imageUrl"]
    assert imageUrl and imageUrl.startswith("/api/images/")

    img = local.get(imageUrl)
    assert img.status_code == 200
    assert img.content == PNG_BYTES

    listed = local.get("/api/entries").json()
    assert listed[0]["imageUrl"] == imageUrl


def test_createEntryRejectsEmpty(dataDir, dbFile):
    local = TestClient(createApp())
    assert _createEntry(local).status_code == 400


def test_createEntryRejectsNonImage(dataDir, dbFile):
    local = TestClient(createApp())
    res = _createEntry(local, content="附了个文本", files={"image": ("a.txt", b"text", "text/plain")})
    assert res.status_code == 400


def test_createEntryRejectsOversize(dataDir, dbFile, monkeypatch):
    from down_note.api import entries as entriesApi

    monkeypatch.setattr(entriesApi, "MAX_IMAGE_BYTES", 100)
    local = TestClient(createApp())
    big = PNG_BYTES + b"0" * 100
    res = _createEntry(local, files={"image": ("big.png", big, "image/png")})
    assert res.status_code == 400


def test_listEntriesOrderAndPagination(dataDir, dbFile):
    local = TestClient(createApp())
    for i in range(3):
        _createEntry(local, content=f"第{i}条")
    listed = local.get("/api/entries", params={"limit": 2}).json()
    assert [e["content"] for e in listed] == ["第2条", "第1条"]
    page2 = local.get("/api/entries", params={"limit": 2, "offset": 2}).json()
    assert [e["content"] for e in page2] == ["第0条"]


def test_getImageRejectsPathTraversal(dataDir, dbFile):
    local = TestClient(createApp())
    assert local.get("/api/images/..").status_code == 404
    assert local.get("/api/images/%2E%2E").status_code == 404
    assert local.get("/api/images/nope.png").status_code == 404


def test_entryMoodEndpointAndListJoin(dataDir, dbFile):
    local = TestClient(createApp())
    created = local.post("/api/entries", data={"content": "心情端点测试"}).json()
    assert local.get(f"/api/entries/{created['id']}/mood").status_code == 404

    # 直接落一条心情记录（绕过 LLM），验证读取与列表 JOIN
    with database.getDb() as db:
        models.upsertMood(
                db,
                entryId=created["id"],
                labels=["低落", "焦虑"],
                intensity=6,
                summary="测试摘要",
                crisis=False,
                analyzedAt="2026-10-05T21:30:00",
                model="test",
            )
        models.markEntryAnalyzed(db, created["id"])

    mood = local.get(f"/api/entries/{created['id']}/mood").json()
    assert mood["labels"] == ["低落", "焦虑"]
    assert mood["intensity"] == 6
    assert mood["summary"] == "测试摘要"
    assert mood["analyzedAt"] == "2026-10-05T21:30:00"

    listed = local.get("/api/entries").json()
    assert listed[0]["analyzed"] is True
    assert listed[0]["mood"]["summary"] == "测试摘要"


def test_updateEntryOnlyTodayAllowed(dataDir, dbFile):
    local = TestClient(createApp())
    todayPrefix = date.today().isoformat()
    with database.getDb() as db:
        entryId = models.addEntry(db, "改之前", None, f"{todayPrefix}T00:00:01")
        models.upsertMood(
                db,
                entryId=entryId,
                labels=["平静"],
                intensity=4,
                summary="旧心情",
                crisis=False,
                analyzedAt="2026-10-06T19:00:00",
                model="test",
            )
        models.markEntryAnalyzed(db, entryId)

    res = local.put(f"/api/entries/{entryId}", json={"content": "改之后"})
    assert res.status_code == 200
    body = res.json()
    assert body["id"] == entryId  # 同一篇：id 不变
    assert body["content"] == "改之后"
    assert body["analyzed"] is False
    assert body["mood"] is None  # 旧的"心情记录"作废，等重新分析
    # 日期更新为保存时刻
    assert body["createdAt"].startswith(todayPrefix)
    assert body["createdAt"] != f"{todayPrefix}T00:00:01"

    # 过去的日子一律锁定（单条原文与整合日记都不例外）
    with database.getDb() as db:
        pastId = models.addEntry(db, "旧日记", None, "2026-10-05T21:00:00")
        dailyId = models.addDailyEntry(db, "2026-10-05", "整合后的日记")
    assert local.put(f"/api/entries/{pastId}", json={"content": "偷改"}).status_code == 400
    assert local.put(f"/api/entries/{dailyId}", json={"content": "偷改"}).status_code == 400

    # 不存在 / 空内容
    assert local.put("/api/entries/999", json={"content": "x"}).status_code == 404
    assert local.put(f"/api/entries/{entryId}", json={"content": "   "}).status_code == 400


def test_corsPreflightForTauriShell():
    """Tauri 壳页面（tauri.localhost）跨源访问本地后端：预检与实际请求都放行。"""
    client = TestClient(createApp())
    preflight = client.options(
        "/api/settings/model",
        headers={
            "Origin": "http://tauri.localhost",
            "Access-Control-Request-Method": "PUT",
        },
    )
    assert preflight.status_code == 200
    assert preflight.headers["access-control-allow-origin"] == "http://tauri.localhost"

    saved = client.put(
        "/api/settings/model",
        headers={"Origin": "http://tauri.localhost"},
        json={
            "baseUrl": "http://model.local/v1",
            "modelName": "test-model",
            "apiKey": "",
            "temperature": 1,
            "reasoningEffort": "low",
        },
    )
    assert saved.headers["access-control-allow-origin"] == "http://tauri.localhost"
