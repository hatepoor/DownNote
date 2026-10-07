"""pytest 公共夹具：临时数据目录与已建表的数据库。

DOWN_NOTE_DATA_DIR 指向 tmp_path，使 config/database 全部落进临时目录，
测试不碰真实用户数据。切换目录后必须重置全局引擎与 checkpointer 缓存。
"""

import pytest

from down_note import config
from down_note.agent import checkpointer
from down_note.db import database


@pytest.fixture()
def dataDir(tmp_path, monkeypatch):
    monkeypatch.setenv("DOWN_NOTE_DATA_DIR", str(tmp_path))
    monkeypatch.delenv(config.API_KEY_ENV_NAME, raising=False)
    database.resetEngine()
    checkpointer.resetCheckpointer()
    yield tmp_path
    database.resetEngine()
    checkpointer.resetCheckpointer()


@pytest.fixture()
def dbFile(dataDir):
    databaseFile = config.getDatabaseFile()
    database.ensureSchema(databaseFile)
    return databaseFile
