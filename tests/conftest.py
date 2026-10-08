"""pytest 公共夹具：临时数据目录与已建表的数据库。

DOWN_NOTE_DATA_DIR 指向 tmp_path，使 config/database 全部落进临时目录，
测试不碰真实用户数据。切换目录后必须重置全局引擎与 checkpointer 缓存。
"""

import pytest

from down_note import config
from down_note.agent import checkpointer
from down_note.db import database


@pytest.fixture(autouse=True)
def isolateDataDir(tmp_path, monkeypatch):
    """每个用例都跑：数据目录一律指向临时目录。

    兜底作用——即使某个用例忘了请求 dataDir/dbFile 夹具，也不可能写到真实用户库
    （2026-10-08 踩坑：真实库的模型配置曾被一份测试载荷覆盖）。
    """
    monkeypatch.setenv("DOWN_NOTE_DATA_DIR", str(tmp_path))
    monkeypatch.delenv(config.API_KEY_ENV_NAME, raising=False)
    database.resetEngine()
    checkpointer.resetCheckpointer()
    yield
    database.resetEngine()
    checkpointer.resetCheckpointer()


@pytest.fixture()
def dataDir(tmp_path):
    """显式请求数据目录的用例用它（隔离由 isolateDataDir 统一保证）。"""
    return tmp_path


@pytest.fixture()
def dbFile(dataDir):
    databaseFile = config.getDatabaseFile()
    database.ensureSchema(databaseFile)
    return databaseFile
