"""模型配置接口：读取与直接更换（OpenAI 兼容三件套 + 生成参数）。

api_key 只存 .env：GET 只回掩码，PUT 时空 key 表示"保持原密钥不变"。
温度与思考强度存 settings 表（0–2 / 空串=不传），保存即生效。
对应开发文档：docx/v0.1.0/modules/03-模型接口.md、12-体验修订.md
"""

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from down_note import config
from down_note.db import database, models

router = APIRouter(prefix="/api/settings", tags=["settings"])

REASONING_EFFORTS = ("", "low", "medium", "high")  # "" = 不向模型传该参数


class ModelSettingsRead(BaseModel):
    baseUrl: str
    modelName: str
    apiKeyMasked: str
    temperature: float
    reasoningEffort: str
    configured: bool


class ModelSettingsWrite(BaseModel):
    baseUrl: str
    modelName: str
    apiKey: str = ""
    temperature: float = config.DEFAULT_TEMPERATURE
    reasoningEffort: str = config.DEFAULT_REASONING_EFFORT


@router.get("/model")
def getModelSettings() -> ModelSettingsRead:
    with database.getDb() as db:
        cfg = config.getModelServiceConfig(db)
    return ModelSettingsRead(
            baseUrl=cfg.baseUrl,
            modelName=cfg.modelName,
            apiKeyMasked=config.maskApiKey(cfg.apiKey),
            temperature=cfg.temperature,
            reasoningEffort=cfg.reasoningEffort,
            configured=cfg.isConfigured(),
        )


@router.put("/model")
def saveModelSettings(body: ModelSettingsWrite) -> dict[str, bool]:
    if not 0 <= body.temperature <= 2:
        raise HTTPException(status_code=400, detail="温度需在 0–2 之间")
    if body.reasoningEffort not in REASONING_EFFORTS:
        raise HTTPException(status_code=400, detail="思考强度取值不合法")
    with database.getDb() as db:
        models.setSetting(db, "base_url", body.baseUrl.strip())
        models.setSetting(db, "model_name", body.modelName.strip())
        models.setSetting(db, "temperature", str(body.temperature))
        models.setSetting(db, "reasoning_effort", body.reasoningEffort)
    if body.apiKey:
        config.setApiKey(body.apiKey)
    return {"ok": True}
