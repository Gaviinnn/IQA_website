from __future__ import annotations

from typing import Any

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from backend.models.doubao_api import ping_profile
from backend.services.provider_profiles import (
    activate_provider_profile,
    delete_provider_profile,
    get_active_provider_profile,
    list_provider_presets,
    list_provider_profiles,
    upsert_provider_profile,
)

router = APIRouter(prefix='/providers', tags=['providers'])


class ProviderProfileRequest(BaseModel):
    profile_id: str | None = Field(None)
    name: str = Field(..., min_length=1)
    provider_id: str = Field(..., min_length=1)
    base_url: str | None = Field(None)
    model: str = Field(..., min_length=1)
    api_key: str | None = Field(None)
    api_version: str | None = Field(None)
    organization: str | None = Field(None)
    region: str | None = Field(None)
    access_key_id: str | None = Field(None)
    secret_access_key: str | None = Field(None)
    session_token: str | None = Field(None)
    extra_headers: dict[str, Any] | None = Field(default_factory=dict)
    extra_body: dict[str, Any] | None = Field(default_factory=dict)
    is_active: bool = Field(False)


class ProviderProfileIdRequest(BaseModel):
    profile_id: str = Field(..., min_length=1)


@router.get('/presets')
async def provider_presets_route() -> dict[str, Any]:
    return {'presets': list_provider_presets()}


@router.get('/profiles')
async def provider_profiles_route() -> dict[str, Any]:
    profiles = await list_provider_profiles()
    active = await get_active_provider_profile()
    return {
        'profiles': profiles,
        'active_profile_id': active.profile_id if active else None,
    }


@router.get('/active')
async def active_provider_route() -> dict[str, Any]:
    active = await get_active_provider_profile()
    return {'profile': active.masked_dict() if active else None}


@router.post('/profiles')
async def upsert_provider_route(payload: ProviderProfileRequest) -> dict[str, Any]:
    try:
        profile = await upsert_provider_profile(payload.model_dump())
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return {'profile': profile}


@router.post('/profiles/activate')
async def activate_provider_route(payload: ProviderProfileIdRequest) -> dict[str, Any]:
    try:
        profile = await activate_provider_profile(payload.profile_id.strip())
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    return {'profile': profile}


@router.delete('/profiles/{profile_id}')
async def delete_provider_route(profile_id: str) -> dict[str, bool]:
    deleted = await delete_provider_profile(profile_id.strip())
    if not deleted:
        raise HTTPException(status_code=404, detail='Provider profile not found')
    return {'deleted': True}


@router.post('/test')
async def test_provider_route(payload: ProviderProfileIdRequest) -> dict[str, Any]:
    ok, detail = await ping_profile(payload.profile_id.strip())
    return {'ok': ok, 'detail': detail}
