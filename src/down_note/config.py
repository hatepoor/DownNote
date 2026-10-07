"""用户数据目录定位与配置统一入口：模型配置读写、.env 密钥加载与保护。

数据布局：`<数据目录>/down_note.db`、`<数据目录>/.env`、`<数据目录>/images/`。
保护约定（ADR-0002）：api_key 只存 .env，不落库、不进接口响应原文、
日志与异常信息禁止输出密钥，对外只给 maskApiKey 的掩码。
对应开发文档：docx/v0.1.0/modules/02-数据库与配置.md
"""

import os
import sys
from dataclasses import dataclass
from pathlib import Path

from dotenv import load_dotenv, set_key
from sqlalchemy.orm import Session

from down_note.db import models

APP_DIR_NAME = "down_note"
ENV_FILE_NAME = ".env"
API_KEY_ENV_NAME = "DOWN_NOTE_API_KEY"


def getDataDir() -> Path:
    # 测试与便携场景用 DOWN_NOTE_DATA_DIR 重定向；其余按平台惯例
    override = os.environ.get("DOWN_NOTE_DATA_DIR")
    if override:
        dataDir = Path(override)
    elif os.name == "nt":
        dataDir = Path(os.environ["APPDATA"]) / APP_DIR_NAME
    elif sys.platform == "darwin":
        dataDir = Path.home() / "Library" / "Application Support" / APP_DIR_NAME
    else:
        dataDir = Path.home() / ".local" / "share" / APP_DIR_NAME
    dataDir.mkdir(parents=True, exist_ok=True)
    return dataDir


def getDatabaseFile() -> Path:
    return getDataDir() / "down_note.db"


def getImagesDir() -> Path:
    return getDataDir() / "images"


def getBundledRoot() -> Path:
    """静态资源基目录：PyInstaller 打包后为解包目录（_MEIPASS，即 _internal），开发态为仓库根。"""
    bundled = getattr(sys, "_MEIPASS", None)
    if bundled:
        return Path(bundled)
    return Path(__file__).resolve().parents[2]


def getEnvFile() -> Path:
    return getDataDir() / ENV_FILE_NAME


def loadEnv() -> bool:
    return load_dotenv(getEnvFile())


def getApiKey() -> str:
    return os.environ.get(API_KEY_ENV_NAME, "")


def setApiKey(apiKey: str) -> None:
    set_key(getEnvFile(), API_KEY_ENV_NAME, apiKey)
    os.environ[API_KEY_ENV_NAME] = apiKey


def maskApiKey(apiKey: str) -> str:
    if not apiKey:
        return ""
    if len(apiKey) <= 8:
        return "*" * len(apiKey)
    return f"{apiKey[:3]}***{apiKey[-4:]}"


DEFAULT_TEMPERATURE = 1.1
DEFAULT_REASONING_EFFORT = "low"  # "" 表示不向模型传该参数


@dataclass
class ModelServiceConfig:
    """模型服务三件套 + 生成参数。apiKey 可为空——本地服务（如 Ollama）常不需要。"""

    baseUrl: str = ""
    apiKey: str = ""
    modelName: str = ""
    temperature: float = DEFAULT_TEMPERATURE
    reasoningEffort: str = DEFAULT_REASONING_EFFORT

    def isConfigured(self) -> bool:
        return bool(self.baseUrl) and bool(self.modelName)


def getModelServiceConfig(db: Session) -> ModelServiceConfig:
    """汇总非敏感配置（settings 表）与密钥（.env）——模型服务配置的唯一读取入口。"""
    rawTemperature = models.getSetting(db, "temperature")
    try:
        temperature = float(rawTemperature) if rawTemperature else DEFAULT_TEMPERATURE
    except ValueError:
        temperature = DEFAULT_TEMPERATURE
    # 注意：思考强度允许空串（=不传该参数），只有"未设置过"才落默认值
    storedEffort = models.getSetting(db, "reasoning_effort")
    reasoningEffort = DEFAULT_REASONING_EFFORT if storedEffort is None else storedEffort
    return ModelServiceConfig(
            baseUrl=models.getSetting(db, "base_url") or "",
            apiKey=getApiKey(),
            modelName=models.getSetting(db, "model_name") or "",
            temperature=temperature,
            reasoningEffort=reasoningEffort,
        )
