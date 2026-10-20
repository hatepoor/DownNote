"""模型配置接口：读取与直接更换（OpenAI 兼容三件套 + 生成参数）。

api_key 只存 .env：GET 只回掩码，PUT 时空 key 表示"保持原密钥不变"。
温度与思考强度存 settings 表（0–2 / 空串=不传），保存即生效。
v0.2.0 02 起同一路由承载陪伴设置（开关 + 档位）与人格设置（开关 + soul.md 内容）。
对应开发文档：docx/v0.1.0/modules/03-模型接口.md、12-体验修订.md、
docx/v0.2.0/modules/02-设置整理.md
"""

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from down_note import config
from down_note.agent.prompts.companion import DEFAULT_PERSONA
from down_note.core import companion, entryReply, persona
from down_note.db import database, models

router = APIRouter(prefix="/api/settings", tags=["settings"])

REASONING_EFFORTS = ("", "low", "medium", "high")  # "" = 不向模型传该参数
DEFAULT_COMPANION_TIER = "normal"


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


class CompanionSettingsRead(BaseModel):
    enabled: bool
    tier: str
    diaryReplyEnabled: bool  # 条目回应开关（v0.3.0 01）：独立于主动陪伴，默认开启


class CompanionSettingsWrite(BaseModel):
    enabled: bool
    tier: str = DEFAULT_COMPANION_TIER
    diaryReplyEnabled: bool = True


class PersonaSettingsRead(BaseModel):
    enabled: bool
    content: str
    defaultPersona: str
    maxLength: int


class PersonaSettingsWrite(BaseModel):
    enabled: bool
    content: str = ""


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


@router.get("/companion")
def getCompanionSettings() -> CompanionSettingsRead:
    with database.getDb() as db:
        enabled = models.getSetting(db, companion.ENABLED_KEY) == "1"
        tier = models.getSetting(db, companion.TIER_KEY) or DEFAULT_COMPANION_TIER
        diaryReplyEnabled = entryReply.isReplyEnabled(db)
    return CompanionSettingsRead(enabled=enabled, tier=tier, diaryReplyEnabled=diaryReplyEnabled)


@router.put("/companion")
def saveCompanionSettings(body: CompanionSettingsWrite) -> dict[str, bool]:
    if body.tier not in companion.TIERS:
        raise HTTPException(status_code=400, detail="档位取值不合法")
    with database.getDb() as db:
        models.setSetting(db, companion.ENABLED_KEY, "1" if body.enabled else "0")
        models.setSetting(db, companion.TIER_KEY, body.tier)
        models.setSetting(db, entryReply.ENABLED_KEY, "1" if body.diaryReplyEnabled else "0")
    return {"ok": True}


@router.get("/persona")
def getPersonaSettings() -> PersonaSettingsRead:
    with database.getDb() as db:
        enabled = persona.isPersonaEnabled(db)
    return PersonaSettingsRead(
            enabled=enabled,
            content=persona.readCustomPersona(),
            defaultPersona=DEFAULT_PERSONA,
            maxLength=persona.CONTENT_MAX_LENGTH,
        )


@router.put("/persona")
def savePersonaSettings(body: PersonaSettingsWrite) -> dict[str, bool]:
    try:
        content = persona.normalizeContent(body.content)
    except ValueError as error:
        raise HTTPException(status_code=400, detail=str(error)) from error
    persona.writeCustomPersona(content)
    with database.getDb() as db:
        models.setSetting(db, persona.PERSONA_ENABLED_KEY, "1" if body.enabled else "0")
    return {"ok": True}
