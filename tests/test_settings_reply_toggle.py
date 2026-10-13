"""日记回应开关（v0.3.0 01）：默认开启、可关、读回。

隔离由 conftest 的 isolateDataDir 保证；不 monkeypatch database.DEFAULT_DB_PATH（不存在）。
"""
import pytest
from fastapi.testclient import TestClient

from down_note.app import createApp


@pytest.fixture()
def client(dbFile):
    return TestClient(createApp())


def test_default_on(client):
    assert client.get("/api/settings/companion").json()["diaryReplyEnabled"] is True


def test_toggle_off_persists(client):
    r = client.put("/api/settings/companion",
                   json={"enabled": False, "tier": "normal", "diaryReplyEnabled": False})
    assert r.status_code == 200
    assert client.get("/api/settings/companion").json()["diaryReplyEnabled"] is False
