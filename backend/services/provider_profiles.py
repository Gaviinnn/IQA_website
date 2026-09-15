from __future__ import annotations

import asyncio
import json
import logging
import os
import secrets
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import aiosqlite

logger = logging.getLogger('iqa.providers')

BASE_DIR = Path(__file__).resolve().parent.parent
DEFAULT_UPLOAD_DIR = BASE_DIR / 'uploads'
UPLOAD_DIR = Path(os.getenv('UPLOAD_DIR', str(DEFAULT_UPLOAD_DIR)))
HISTORY_DB_FILE = Path(os.getenv('HISTORY_DB_FILE', str(UPLOAD_DIR / 'history.db')))

DEFAULT_ANTHROPIC_BASE_URL = 'https://api.anthropic.com/v1'
DEFAULT_AZURE_API_VERSION = '2024-10-21'
DEFAULT_ANTHROPIC_VERSION = '2023-06-01'

_schema_lock = asyncio.Lock()
_schema_ready = False

PROVIDER_PRESETS: list[dict[str, Any]] = [
    {
        'id': 'openai',
        'label': 'OpenAI',
        'protocol': 'openai_compatible',
        'default_base_url': 'https://api.openai.com/v1',
        'default_model': 'gpt-4.1-mini',
        'docs_url': 'https://platform.openai.com/docs/api-reference',
        'supports_multimodal': True,
    },
    {
        'id': 'azure_openai',
        'label': 'Azure OpenAI',
        'protocol': 'azure_openai',
        'default_base_url': 'https://YOUR_RESOURCE.openai.azure.com',
        'default_model': 'gpt-4.1-mini',
        'docs_url': 'https://learn.microsoft.com/azure/ai-services/openai/reference',
        'supports_multimodal': True,
        'requires_api_version': True,
    },
    {
        'id': 'anthropic',
        'label': 'Anthropic Claude',
        'protocol': 'anthropic_native',
        'default_base_url': DEFAULT_ANTHROPIC_BASE_URL,
        'default_model': 'claude-sonnet-4-5',
        'docs_url': 'https://docs.anthropic.com/en/api/messages',
        'supports_multimodal': True,
        'requires_api_version': True,
    },
    {
        'id': 'google_gemini',
        'label': 'Google Gemini',
        'protocol': 'openai_compatible',
        'default_base_url': 'https://generativelanguage.googleapis.com/v1beta/openai',
        'default_model': 'gemini-2.5-flash',
        'docs_url': 'https://ai.google.dev/gemini-api/docs/openai',
        'supports_multimodal': True,
    },
    {
        'id': 'qwen',
        'label': 'Alibaba Qwen',
        'protocol': 'openai_compatible',
        'default_base_url': 'https://dashscope.aliyuncs.com/compatible-mode/v1',
        'default_model': 'qwen3-vl-plus',
        'docs_url': 'https://www.alibabacloud.com/help/en/model-studio/compatibility-of-openai-with-dashscope',
        'supports_multimodal': True,
    },
    {
        'id': 'volcengine_ark',
        'label': 'Volcengine Ark / Doubao',
        'protocol': 'openai_compatible',
        'default_base_url': 'https://ark.cn-beijing.volces.com/api/v3',
        'default_model': 'YOUR_ARK_ENDPOINT_ID',
        'docs_url': 'https://www.volcengine.com/docs/82379/1298454',
        'supports_multimodal': True,
    },
    {
        'id': 'deepseek',
        'label': 'DeepSeek',
        'protocol': 'openai_compatible',
        'default_base_url': 'https://api.deepseek.com/v1',
        'default_model': 'deepseek-chat',
        'docs_url': 'https://api-docs.deepseek.com/',
        'supports_multimodal': True,
    },
    {
        'id': 'openrouter',
        'label': 'OpenRouter',
        'protocol': 'openai_compatible',
        'default_base_url': 'https://openrouter.ai/api/v1',
        'default_model': 'openai/gpt-4o-mini',
        'docs_url': 'https://openrouter.ai/docs/api-reference/overview',
        'supports_multimodal': True,
        'use_raw_model_name': True,
    },
    {
        'id': 'xai',
        'label': 'xAI Grok',
        'protocol': 'openai_compatible',
        'default_base_url': 'https://api.x.ai/v1',
        'default_model': 'grok-2-vision-latest',
        'docs_url': 'https://docs.x.ai/docs/overview',
        'supports_multimodal': True,
    },
    {
        'id': 'zhipu',
        'label': 'Zhipu GLM',
        'protocol': 'openai_compatible',
        'default_base_url': 'https://open.bigmodel.cn/api/paas/v4',
        'default_model': 'glm-4.5v',
        'docs_url': 'https://open.bigmodel.cn/dev/api#glm-4.5v',
        'supports_multimodal': True,
    },
    {
        'id': 'baidu_qianfan',
        'label': 'Baidu Qianfan',
        'protocol': 'openai_compatible',
        'default_base_url': 'https://qianfan.baidubce.com/v2',
        'default_model': 'ernie-4.0-8k-latest',
        'docs_url': 'https://cloud.baidu.com/doc/WENXINWORKSHOP/s/wm7xlt53j',
        'supports_multimodal': True,
    },
    {
        'id': 'tencent_hunyuan',
        'label': 'Tencent Hunyuan',
        'protocol': 'openai_compatible',
        'default_base_url': 'https://api.hunyuan.cloud.tencent.com/v1',
        'default_model': 'hunyuan-vision',
        'docs_url': 'https://cloud.tencent.com/document/product/1729',
        'supports_multimodal': True,
    },
    {
        'id': 'moonshot',
        'label': 'Moonshot Kimi',
        'protocol': 'openai_compatible',
        'default_base_url': 'https://api.moonshot.cn/v1',
        'default_model': 'kimi-k2-0711-preview',
        'docs_url': 'https://platform.moonshot.cn/docs/api-reference',
        'supports_multimodal': True,
    },
    {
        'id': 'minimax',
        'label': 'MiniMax',
        'protocol': 'openai_compatible',
        'default_base_url': 'https://api.minimax.chat/v1',
        'default_model': 'MiniMax-M1',
        'docs_url': 'https://platform.minimaxi.com/document/AI%20Hailuo/OpenAI%20API',
        'supports_multimodal': True,
    },
]

PRESET_BY_ID = {item['id']: item for item in PROVIDER_PRESETS}


@dataclass(slots=True)
class ProviderProfile:
    profile_id: str
    name: str
    provider_id: str
    protocol: str
    base_url: str | None
    model: str
    api_key: str | None
    api_version: str | None
    organization: str | None
    region: str | None
    access_key_id: str | None
    secret_access_key: str | None
    session_token: str | None
    extra_headers: dict[str, Any]
    extra_body: dict[str, Any]
    is_active: bool
    created_at: str
    updated_at: str

    def masked_dict(self) -> dict[str, Any]:
        return {
            'profile_id': self.profile_id,
            'name': self.name,
            'provider_id': self.provider_id,
            'protocol': self.protocol,
            'base_url': self.base_url,
            'model': self.model,
            'api_key_masked': _mask_secret(self.api_key),
            'api_version': self.api_version,
            'organization': self.organization,
            'region': self.region,
            'access_key_id_masked': _mask_secret(self.access_key_id),
            'secret_access_key_masked': _mask_secret(self.secret_access_key),
            'session_token_masked': _mask_secret(self.session_token),
            'extra_headers': self.extra_headers,
            'extra_body': self.extra_body,
            'is_active': self.is_active,
            'created_at': self.created_at,
            'updated_at': self.updated_at,
        }


def _mask_secret(value: str | None) -> str | None:
    if not value:
        return None
    if len(value) <= 8:
        return '*' * len(value)
    return f'{value[:4]}***{value[-4:]}'


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def list_provider_presets() -> list[dict[str, Any]]:
    return [dict(item) for item in PROVIDER_PRESETS]


async def _ensure_schema() -> None:
    global _schema_ready
    if _schema_ready:
        return

    async with _schema_lock:
        if _schema_ready:
            return
        async with aiosqlite.connect(HISTORY_DB_FILE) as db:
            await db.execute(
                """
                CREATE TABLE IF NOT EXISTS provider_profiles (
                    profile_id TEXT PRIMARY KEY,
                    name TEXT NOT NULL,
                    provider_id TEXT NOT NULL,
                    protocol TEXT NOT NULL,
                    base_url TEXT,
                    model TEXT NOT NULL,
                    api_key TEXT,
                    api_version TEXT,
                    organization TEXT,
                    region TEXT,
                    access_key_id TEXT,
                    secret_access_key TEXT,
                    session_token TEXT,
                    extra_headers TEXT,
                    extra_body TEXT,
                    is_active INTEGER NOT NULL DEFAULT 0,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                )
                """
            )
            await db.commit()
        _schema_ready = True
    await _bootstrap_default_profile()


async def _bootstrap_default_profile() -> None:
    async with aiosqlite.connect(HISTORY_DB_FILE) as db:
        db.row_factory = aiosqlite.Row
        cursor = await db.execute("SELECT COUNT(1) AS total FROM provider_profiles")
        total = (await cursor.fetchone())['total']
        await cursor.close()
        if total:
            return

        env_profile = _profile_from_env()
        if env_profile is None:
            return

        await db.execute(
            """
            INSERT INTO provider_profiles (
                profile_id, name, provider_id, protocol, base_url, model, api_key,
                api_version, organization, region, access_key_id, secret_access_key,
                session_token, extra_headers, extra_body, is_active, created_at, updated_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 1, ?, ?)
            """,
            (
                env_profile.profile_id,
                env_profile.name,
                env_profile.provider_id,
                env_profile.protocol,
                env_profile.base_url,
                env_profile.model,
                env_profile.api_key,
                env_profile.api_version,
                env_profile.organization,
                env_profile.region,
                env_profile.access_key_id,
                env_profile.secret_access_key,
                env_profile.session_token,
                json.dumps(env_profile.extra_headers, ensure_ascii=False),
                json.dumps(env_profile.extra_body, ensure_ascii=False),
                env_profile.created_at,
                env_profile.updated_at,
            ),
        )
        await db.commit()
        logger.info('Bootstrapped provider profile from env | provider=%s', env_profile.provider_id)


def _profile_from_env() -> ProviderProfile | None:
    now = _now_iso()
    if os.getenv('DOUBAO_API_KEY'):
        provider_id = 'volcengine_ark'
        preset = PRESET_BY_ID[provider_id]
        return ProviderProfile(
            profile_id='prf_env_volcengine_ark',
            name='Env Volcengine Ark',
            provider_id=provider_id,
            protocol=preset['protocol'],
            base_url=os.getenv('DOUBAO_API_URL') or preset['default_base_url'],
            model=os.getenv('DOUBAO_MODEL') or preset['default_model'],
            api_key=os.getenv('DOUBAO_API_KEY'),
            api_version=None,
            organization=None,
            region='cn-beijing',
            access_key_id=None,
            secret_access_key=None,
            session_token=None,
            extra_headers={},
            extra_body={},
            is_active=True,
            created_at=now,
            updated_at=now,
        )
    if os.getenv('OPENAI_API_KEY'):
        provider_id = 'openai'
        preset = PRESET_BY_ID[provider_id]
        return ProviderProfile(
            profile_id='prf_env_openai',
            name='Env OpenAI',
            provider_id=provider_id,
            protocol=preset['protocol'],
            base_url=os.getenv('OPENAI_BASE_URL') or preset['default_base_url'],
            model=os.getenv('OPENAI_MODEL') or preset['default_model'],
            api_key=os.getenv('OPENAI_API_KEY'),
            api_version=None,
            organization=os.getenv('OPENAI_ORGANIZATION'),
            region=None,
            access_key_id=None,
            secret_access_key=None,
            session_token=None,
            extra_headers={},
            extra_body={},
            is_active=True,
            created_at=now,
            updated_at=now,
        )
    return None


def _row_to_profile(row: aiosqlite.Row) -> ProviderProfile:
    return ProviderProfile(
        profile_id=row['profile_id'],
        name=row['name'],
        provider_id=row['provider_id'],
        protocol=row['protocol'],
        base_url=row['base_url'],
        model=row['model'],
        api_key=row['api_key'],
        api_version=row['api_version'],
        organization=row['organization'],
        region=row['region'],
        access_key_id=row['access_key_id'],
        secret_access_key=row['secret_access_key'],
        session_token=row['session_token'],
        extra_headers=json.loads(row['extra_headers']) if row['extra_headers'] else {},
        extra_body=json.loads(row['extra_body']) if row['extra_body'] else {},
        is_active=bool(row['is_active']),
        created_at=row['created_at'],
        updated_at=row['updated_at'],
    )


async def list_provider_profiles() -> list[dict[str, Any]]:
    await _ensure_schema()
    async with aiosqlite.connect(HISTORY_DB_FILE) as db:
        db.row_factory = aiosqlite.Row
        cursor = await db.execute(
            """
            SELECT * FROM provider_profiles
            ORDER BY is_active DESC, updated_at DESC, name ASC
            """
        )
        rows = await cursor.fetchall()
        await cursor.close()
    return [_row_to_profile(row).masked_dict() for row in rows]


async def get_provider_profile(profile_id: str) -> ProviderProfile | None:
    await _ensure_schema()
    async with aiosqlite.connect(HISTORY_DB_FILE) as db:
        db.row_factory = aiosqlite.Row
        cursor = await db.execute(
            "SELECT * FROM provider_profiles WHERE profile_id = ?",
            (profile_id,),
        )
        row = await cursor.fetchone()
        await cursor.close()
    return _row_to_profile(row) if row else None


async def get_active_provider_profile() -> ProviderProfile | None:
    await _ensure_schema()
    async with aiosqlite.connect(HISTORY_DB_FILE) as db:
        db.row_factory = aiosqlite.Row
        cursor = await db.execute(
            "SELECT * FROM provider_profiles WHERE is_active = 1 ORDER BY updated_at DESC LIMIT 1"
        )
        row = await cursor.fetchone()
        await cursor.close()
    return _row_to_profile(row) if row else None


async def upsert_provider_profile(payload: dict[str, Any]) -> dict[str, Any]:
    await _ensure_schema()

    provider_id = str(payload.get('provider_id') or '').strip()
    if provider_id not in PRESET_BY_ID:
        raise ValueError('Unsupported provider preset')

    preset = PRESET_BY_ID[provider_id]
    profile_id = str(payload.get('profile_id') or '').strip() or f"prf_{secrets.token_hex(8)}"
    existing = await get_provider_profile(profile_id)

    name = str(payload.get('name') or '').strip() or f"{preset['label']} Profile"
    model = str(payload.get('model') or '').strip() or preset['default_model']
    base_url = str(payload.get('base_url') or '').strip() or preset['default_base_url']
    api_version = str(payload.get('api_version') or '').strip() or None
    organization = str(payload.get('organization') or '').strip() or None
    region = str(payload.get('region') or '').strip() or None
    extra_headers = payload.get('extra_headers') or {}
    extra_body = payload.get('extra_body') or {}
    is_active = bool(payload.get('is_active'))

    now = _now_iso()
    profile = ProviderProfile(
        profile_id=profile_id,
        name=name,
        provider_id=provider_id,
        protocol=preset['protocol'],
        base_url=base_url,
        model=model,
        api_key=(payload.get('api_key') or '').strip() or (existing.api_key if existing else None),
        api_version=api_version or (DEFAULT_AZURE_API_VERSION if provider_id == 'azure_openai' else None),
        organization=organization or (existing.organization if existing else None),
        region=region or (existing.region if existing else None),
        access_key_id=(payload.get('access_key_id') or '').strip() or (existing.access_key_id if existing else None),
        secret_access_key=(payload.get('secret_access_key') or '').strip()
        or (existing.secret_access_key if existing else None),
        session_token=(payload.get('session_token') or '').strip() or (existing.session_token if existing else None),
        extra_headers=extra_headers if isinstance(extra_headers, dict) else {},
        extra_body=extra_body if isinstance(extra_body, dict) else {},
        is_active=is_active,
        created_at=existing.created_at if existing else now,
        updated_at=now,
    )

    async with aiosqlite.connect(HISTORY_DB_FILE) as db:
        if profile.is_active:
            await db.execute("UPDATE provider_profiles SET is_active = 0")
        await db.execute(
            """
            INSERT INTO provider_profiles (
                profile_id, name, provider_id, protocol, base_url, model, api_key,
                api_version, organization, region, access_key_id, secret_access_key,
                session_token, extra_headers, extra_body, is_active, created_at, updated_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(profile_id) DO UPDATE SET
                name = excluded.name,
                provider_id = excluded.provider_id,
                protocol = excluded.protocol,
                base_url = excluded.base_url,
                model = excluded.model,
                api_key = excluded.api_key,
                api_version = excluded.api_version,
                organization = excluded.organization,
                region = excluded.region,
                access_key_id = excluded.access_key_id,
                secret_access_key = excluded.secret_access_key,
                session_token = excluded.session_token,
                extra_headers = excluded.extra_headers,
                extra_body = excluded.extra_body,
                is_active = excluded.is_active,
                updated_at = excluded.updated_at
            """,
            (
                profile.profile_id,
                profile.name,
                profile.provider_id,
                profile.protocol,
                profile.base_url,
                profile.model,
                profile.api_key,
                profile.api_version,
                profile.organization,
                profile.region,
                profile.access_key_id,
                profile.secret_access_key,
                profile.session_token,
                json.dumps(profile.extra_headers, ensure_ascii=False),
                json.dumps(profile.extra_body, ensure_ascii=False),
                1 if profile.is_active else 0,
                profile.created_at,
                profile.updated_at,
            ),
        )
        await db.commit()

    if profile.is_active:
        logger.info('Provider profile activated on save | id=%s', profile.profile_id)
    return profile.masked_dict()


async def activate_provider_profile(profile_id: str) -> dict[str, Any]:
    profile = await get_provider_profile(profile_id)
    if profile is None:
        raise ValueError('Provider profile not found')

    async with aiosqlite.connect(HISTORY_DB_FILE) as db:
        await db.execute("UPDATE provider_profiles SET is_active = 0")
        await db.execute(
            "UPDATE provider_profiles SET is_active = 1, updated_at = ? WHERE profile_id = ?",
            (_now_iso(), profile_id),
        )
        await db.commit()

    updated = await get_provider_profile(profile_id)
    if updated is None:
        raise ValueError('Provider profile not found after activation')
    logger.info('Provider profile activated | id=%s', profile_id)
    return updated.masked_dict()


async def delete_provider_profile(profile_id: str) -> bool:
    await _ensure_schema()
    async with aiosqlite.connect(HISTORY_DB_FILE) as db:
        cursor = await db.execute("DELETE FROM provider_profiles WHERE profile_id = ?", (profile_id,))
        affected = cursor.rowcount or 0
        await cursor.close()
        await db.commit()
    return bool(affected)


def get_provider_preset(provider_id: str) -> dict[str, Any]:
    preset = PRESET_BY_ID.get(provider_id)
    if preset is None:
        raise ValueError(f'Unsupported provider preset: {provider_id}')
    return dict(preset)


def get_model_display_name(profile: ProviderProfile | None) -> str:
    if profile is None:
        return 'No active provider'
    preset = PRESET_BY_ID.get(profile.provider_id, {})
    label = preset.get('label') or profile.provider_id
    return f'{label} / {profile.model}'
