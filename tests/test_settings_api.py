"""陪伴与人格设置接口测试：默认值、档位校验、soul.md 读写与 2000 字上限。

对应模块：docx/v0.2.0/modules/02-设置整理.md
"""

from fastapi.testclient import TestClient

from down_note.app import createApp
from down_note.core import persona


def _client() -> TestClient:
    return TestClient(createApp())


def test_companionDefaultsOff(dbFile):
    """陪伴默认关闭、档位默认「正常」——关闭时行为与现状一致的前提。

    日记回应（v0.3.0 01）是独立开关，默认开启：写日记是用户主动行为，回应属基础体验。
    """
    body = _client().get("/api/settings/companion").json()
    assert body == {"enabled": False, "tier": "normal", "diaryReplyEnabled": True}


def test_companionRoundtripAndValidation(dbFile):
    client = _client()
    resp = client.put("/api/settings/companion", json={"enabled": True, "tier": "caring"})
    assert resp.status_code == 200
    assert client.get("/api/settings/companion").json() == {
        "enabled": True,
        "tier": "caring",
        "diaryReplyEnabled": True,
    }
    bad = client.put("/api/settings/companion", json={"enabled": True, "tier": "hot"})
    assert bad.status_code == 400


def test_personaDefaultsToShippedOne(dbFile):
    """默认人格随包：预览文本是纯风格层，不含 {memories} 这类装配占位符。"""
    body = _client().get("/api/settings/persona").json()
    assert body["enabled"] is False
    assert body["content"] == ""
    assert body["maxLength"] == 2000
    assert "怎么说话（最重要）" in body["defaultPersona"]
    assert "{memories}" not in body["defaultPersona"]


def test_personaWriteAndReadBack(dbFile, dataDir):
    """保存写进数据目录 soul.md；空内容 → 文件为空、读取为空（运行时回退默认）。"""
    client = _client()
    content = "你是一个话不多的朋友，\n句子很短。"
    resp = client.put("/api/settings/persona", json={"enabled": True, "content": content})
    assert resp.status_code == 200
    assert persona.getSoulFile() == dataDir / "soul.md"
    assert persona.getSoulFile().read_text(encoding="utf-8") == content

    saved = client.get("/api/settings/persona").json()
    assert saved["content"] == content
    assert saved["enabled"] is True

    cleared = client.put("/api/settings/persona", json={"enabled": True, "content": "   "})
    assert cleared.status_code == 200
    assert client.get("/api/settings/persona").json()["content"] == ""


def test_personaRejectsOverlong(dbFile):
    """> 2000 字拒绝保存，且旧内容不被破坏（前端提示精简后再保存）。"""
    client = _client()
    client.put("/api/settings/persona", json={"enabled": True, "content": "短内容"})
    resp = client.put("/api/settings/persona", json={"enabled": True, "content": "长" * 2001})
    assert resp.status_code == 400
    assert client.get("/api/settings/persona").json()["content"] == "短内容"
