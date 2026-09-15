from __future__ import annotations

import ast
import asyncio
import json
import logging
import re
from dataclasses import dataclass
from typing import Any, Dict, List

import httpx
from openai import AsyncAzureOpenAI, AsyncOpenAI

from backend.services.provider_profiles import (
    DEFAULT_ANTHROPIC_BASE_URL,
    DEFAULT_ANTHROPIC_VERSION,
    DEFAULT_AZURE_API_VERSION,
    ProviderProfile,
    get_active_provider_profile,
    get_model_display_name,
    get_provider_profile,
)

logger = logging.getLogger('iqa.llm_gateway')

TIMEOUT_SECONDS = 30
DEFAULT_MODEL = 'active-provider'


class DoubaoError(RuntimeError):
    def __init__(self, message: str, *, raw_text: str | None = None):
        super().__init__(message)
        self.raw_text = raw_text


@dataclass(slots=True)
class DoubaoResult:
    caption: str | None
    objects: List[dict[str, Any]]
    raw_text: str


@dataclass(slots=True)
class DoubaoStructuredResult:
    payload: Dict[str, Any]
    raw_text: str


def _clip01(x: Any) -> float:
    try:
        value = float(x)
    except Exception:
        return 0.0
    if value > 1.0 and value <= 100.0:
        value = value / 100.0
    return max(0.0, min(1.0, float(value)))


def _sanitize_objects(objs: Any) -> List[Dict[str, Any]]:
    out: List[Dict[str, Any]] = []
    if isinstance(objs, list):
        for item in objs:
            if isinstance(item, dict):
                label = item.get('label') or item.get('name') or item.get('category')
                score = item.get('score') if 'score' in item else item.get('confidence')
                if isinstance(label, str) and label.strip():
                    out.append({'label': label.strip(), 'score': _clip01(score if score is not None else 0.0)})
            elif isinstance(item, str) and item.strip():
                if ':' in item:
                    label, score = item.split(':', 1)
                    out.append({'label': label.strip(), 'score': _clip01(score)})
                else:
                    out.append({'label': item.strip(), 'score': 0.0})
    elif isinstance(objs, dict):
        for key, value in objs.items():
            if isinstance(key, str) and key.strip():
                out.append({'label': key.strip(), 'score': _clip01(value)})

    seen: set[str] = set()
    deduped: List[Dict[str, Any]] = []
    for item in out:
        label = item.get('label', '')
        if label in seen:
            continue
        seen.add(label)
        deduped.append(item)
    return deduped


def _extract_text_from_message(message: Dict[str, Any]) -> str:
    content_field = message.get('content')
    if isinstance(content_field, str):
        return content_field.strip()
    if isinstance(content_field, list):
        chunks: List[str] = []
        for segment in content_field:
            if isinstance(segment, dict):
                text = segment.get('text')
                if isinstance(text, str) and text.strip():
                    chunks.append(text.strip())
        return '\n'.join(chunks).strip()
    return ''


def _normalize_json_candidate(candidate: str) -> str:
    normalized = candidate.strip()
    normalized = re.sub(r'^```(?:json)?\s*', '', normalized, flags=re.IGNORECASE)
    normalized = re.sub(r'\s*```$', '', normalized)
    translation_table = str.maketrans(
        {
            '“': '"',
            '”': '"',
            '‘': "'",
            '’': "'",
            '：': ':',
            '，': ',',
            '；': ';',
        }
    )
    return normalized.translate(translation_table).strip()


def _iter_json_candidates(raw: str) -> list[str]:
    candidates: list[str] = []
    normalized_raw = _normalize_json_candidate(raw)
    if normalized_raw:
        candidates.append(normalized_raw)

    start = -1
    depth = 0
    for index, char in enumerate(raw):
        if char == '{':
            if depth == 0:
                start = index
            depth += 1
        elif char == '}':
            if depth == 0:
                continue
            depth -= 1
            if depth == 0 and start >= 0:
                fragment = _normalize_json_candidate(raw[start:index + 1])
                if fragment:
                    candidates.append(fragment)
                start = -1

    seen: set[str] = set()
    unique: list[str] = []
    for candidate in candidates:
        if candidate in seen:
            continue
        seen.add(candidate)
        unique.append(candidate)
    return unique


def _extract_json_object(text: str) -> Dict[str, Any] | None:
    raw = (text or '').strip()
    if not raw:
        return None

    for candidate in _iter_json_candidates(raw):
        try:
            data = json.loads(candidate)
        except Exception:
            try:
                data = ast.literal_eval(candidate)
            except Exception:
                continue
        if isinstance(data, dict):
            return data
    return None


def _parse_as_contract(text: str) -> tuple[str | None, List[Dict[str, Any]]]:
    payload = _extract_json_object(text)
    if isinstance(payload, dict):
        caption = payload.get('caption')
        objects = _sanitize_objects(payload.get('objects'))
        if isinstance(caption, str) or objects:
            return caption.strip() if isinstance(caption, str) else None, objects

    raw = (text or '').strip()
    return (raw or None), []


def _normalize_openai_base_url(base_url: str | None) -> str:
    normalized = (base_url or '').strip().rstrip('/')
    if not normalized:
        raise DoubaoError('Provider base_url is required')
    for suffix in ('/chat/completions', '/multimodal/completions'):
        if normalized.endswith(suffix):
            normalized = normalized[: -len(suffix)]
            break
    return normalized


def _resolve_timeout(timeout: int | None) -> int:
    if timeout is None or timeout <= 0:
        return TIMEOUT_SECONDS
    return timeout


def _validate_multimodal_model(profile: ProviderProfile, model_name: str, image_base64: str | None) -> None:
    if not image_base64:
        return

    normalized = (model_name or '').strip().lower()
    provider_id = profile.provider_id

    # Qwen's plain `qwen-plus` style models are text-centric; image analysis should use a VL variant.
    if provider_id == 'qwen' and 'vl' not in normalized:
        raise DoubaoError(
            'Selected Qwen model does not look multimodal. Use a vision model such as qwen3-vl-plus or qwen-vl-max.'
        )


async def _resolve_profile(profile_id: str | None) -> ProviderProfile:
    profile = await (get_provider_profile(profile_id) if profile_id else get_active_provider_profile())
    if profile is None:
        raise DoubaoError('No active provider profile configured')
    return profile


def _build_openai_content(prompt: str, *, image_base64: str | None, image_detail: str) -> Any:
    if image_base64:
        return [
            {
                'type': 'image_url',
                'image_url': {
                    'url': f'data:image/jpeg;base64,{image_base64}',
                    'detail': image_detail,
                },
            },
            {'type': 'text', 'text': prompt},
        ]
    return prompt


async def _call_openai_compatible(
    profile: ProviderProfile,
    *,
    prompt: str,
    model: str | None,
    image_base64: str | None,
    image_detail: str,
    timeout: int,
) -> str:
    selected_model = model or profile.model
    _validate_multimodal_model(profile, selected_model, image_base64)

    client = AsyncOpenAI(
        base_url=_normalize_openai_base_url(profile.base_url),
        api_key=profile.api_key or 'missing-api-key',
        organization=profile.organization or None,
    )
    response = await client.chat.completions.create(
        model=selected_model,
        messages=[{'role': 'user', 'content': _build_openai_content(prompt, image_base64=image_base64, image_detail=image_detail)}],
        temperature=0.2,
        top_p=1.0,
        max_tokens=512,
        timeout=timeout,
        extra_headers=profile.extra_headers or None,
        extra_body=profile.extra_body or None,
    )
    payload = response.model_dump()
    choices = payload.get('choices') or []
    if not choices:
        raise DoubaoError('Empty response from provider')
    message = choices[0].get('message', {})
    text = _extract_text_from_message(message)
    return text.strip()


async def _call_azure_openai(
    profile: ProviderProfile,
    *,
    prompt: str,
    model: str | None,
    image_base64: str | None,
    image_detail: str,
    timeout: int,
) -> str:
    selected_model = model or profile.model
    _validate_multimodal_model(profile, selected_model, image_base64)

    client = AsyncAzureOpenAI(
        azure_endpoint=(profile.base_url or '').strip(),
        api_key=profile.api_key or 'missing-api-key',
        api_version=profile.api_version or DEFAULT_AZURE_API_VERSION,
    )
    response = await client.chat.completions.create(
        model=selected_model,
        messages=[{'role': 'user', 'content': _build_openai_content(prompt, image_base64=image_base64, image_detail=image_detail)}],
        temperature=0.2,
        top_p=1.0,
        max_tokens=512,
        timeout=timeout,
        extra_headers=profile.extra_headers or None,
        extra_body=profile.extra_body or None,
    )
    payload = response.model_dump()
    choices = payload.get('choices') or []
    if not choices:
        raise DoubaoError('Empty response from Azure OpenAI')
    message = choices[0].get('message', {})
    text = _extract_text_from_message(message)
    return text.strip()


async def _call_anthropic(
    profile: ProviderProfile,
    *,
    prompt: str,
    model: str | None,
    image_base64: str | None,
    timeout: int,
) -> str:
    selected_model = model or profile.model
    _validate_multimodal_model(profile, selected_model, image_base64)

    base_url = (profile.base_url or DEFAULT_ANTHROPIC_BASE_URL).rstrip('/')
    headers = {
        'x-api-key': profile.api_key or '',
        'anthropic-version': profile.api_version or DEFAULT_ANTHROPIC_VERSION,
        'content-type': 'application/json',
    }
    headers.update({key: str(value) for key, value in (profile.extra_headers or {}).items()})

    if image_base64:
        content: Any = [
            {
                'type': 'image',
                'source': {
                    'type': 'base64',
                    'media_type': 'image/jpeg',
                    'data': image_base64,
                },
            },
            {'type': 'text', 'text': prompt},
        ]
    else:
        content = prompt

    body: dict[str, Any] = {
        'model': selected_model,
        'max_tokens': 512,
        'messages': [{'role': 'user', 'content': content}],
    }
    if profile.extra_body:
        body.update(profile.extra_body)

    async with httpx.AsyncClient(timeout=timeout) as client:
        response = await client.post(f'{base_url}/messages', headers=headers, json=body)
        response.raise_for_status()
        payload = response.json()

    content_items = payload.get('content') or []
    texts = [
        item.get('text', '').strip()
        for item in content_items
        if isinstance(item, dict) and item.get('type') == 'text' and item.get('text')
    ]
    text = '\n'.join(texts).strip()
    if not text:
        raise DoubaoError('Empty response from Anthropic')
    return text


async def _call_text(
    prompt: str,
    *,
    model: str | None = None,
    image_base64: str | None = None,
    image_detail: str = 'low',
    timeout: int = TIMEOUT_SECONDS,
    profile_id: str | None = None,
) -> str:
    profile = await _resolve_profile(profile_id)
    resolved_timeout = _resolve_timeout(timeout)

    try:
        if profile.protocol == 'openai_compatible':
            return await _call_openai_compatible(
                profile,
                prompt=prompt,
                model=model,
                image_base64=image_base64,
                image_detail=image_detail,
                timeout=resolved_timeout,
            )
        if profile.protocol == 'azure_openai':
            return await _call_azure_openai(
                profile,
                prompt=prompt,
                model=model,
                image_base64=image_base64,
                image_detail=image_detail,
                timeout=resolved_timeout,
            )
        if profile.protocol == 'anthropic_native':
            return await _call_anthropic(
                profile,
                prompt=prompt,
                model=model,
                image_base64=image_base64,
                timeout=resolved_timeout,
            )
        raise DoubaoError(f'Unsupported provider protocol: {profile.protocol}')
    except httpx.HTTPStatusError as exc:
        logger.error('Provider HTTP error | provider=%s | status=%s', profile.provider_id, exc.response.status_code)
        raise DoubaoError(f'Provider HTTP error: {exc.response.status_code}') from exc
    except DoubaoError:
        raise
    except Exception as exc:
        logger.error('LLM gateway error | provider=%s | %s', profile.provider_id, exc)
        raise DoubaoError(str(exc)) from exc


async def call_doubao(
    *,
    base64_image: str,
    detail: str = 'low',
    prompt: str | None = None,
    model: str | None = None,
    profile_id: str | None = None,
) -> DoubaoResult:
    final_prompt = (
        prompt
        or '请只返回 JSON：{"caption": string, "objects": [{"label": string, "score": number}]}。score 范围为 0-1，使用中文，不要输出额外说明。'
    )
    text = await _call_text(
        final_prompt,
        model=model,
        image_base64=base64_image,
        image_detail=detail,
        timeout=TIMEOUT_SECONDS,
        profile_id=profile_id,
    )
    caption, objects = _parse_as_contract(text)
    return DoubaoResult(caption=caption, objects=objects, raw_text=text)


async def call_text_model(
    prompt: str,
    *,
    model: str | None = None,
    timeout: int | None = None,
    image_base64: str | None = None,
    image_detail: str = 'low',
    profile_id: str | None = None,
) -> str:
    return await _call_text(
        prompt,
        model=model,
        image_base64=image_base64,
        image_detail=image_detail,
        timeout=_resolve_timeout(timeout),
        profile_id=profile_id,
    )


def parse_vision_response_text(text: str) -> DoubaoResult:
    caption, objects = _parse_as_contract(text)
    return DoubaoResult(caption=caption, objects=objects, raw_text=text)


async def ping() -> bool:
    ok, _ = await ping_profile(None)
    return ok


async def ping_profile(profile_id: str | None) -> tuple[bool, str]:
    try:
        profile = await _resolve_profile(profile_id)
        text = await _call_text('请回复 pong。', model=profile.model, timeout=8, profile_id=profile.profile_id)
        return True, f'{get_model_display_name(profile)} | {text[:80]}'
    except Exception as exc:
        return False, str(exc)


async def call_with_timeout(*, timeout: int = TIMEOUT_SECONDS, **kwargs: Any) -> DoubaoResult:
    return await asyncio.wait_for(call_doubao(**kwargs), timeout=_resolve_timeout(timeout))


async def call_structured_vision(
    *,
    base64_image: str,
    prompt: str,
    detail: str = 'low',
    model: str | None = None,
    timeout: int = TIMEOUT_SECONDS,
    profile_id: str | None = None,
) -> DoubaoStructuredResult:
    raw_text = await asyncio.wait_for(
        _call_text(
            prompt,
            model=model,
            image_base64=base64_image,
            image_detail=detail,
            timeout=timeout,
            profile_id=profile_id,
        ),
        timeout=_resolve_timeout(timeout),
    )
    payload = _extract_json_object(raw_text)
    if payload is None:
        raise DoubaoError('Failed to parse structured JSON response', raw_text=raw_text)
    return DoubaoStructuredResult(payload=payload, raw_text=raw_text)


def call_doubao_model(
    prompt: str,
    *,
    model: str | None = None,
    timeout: int | None = None,
    image_base64: str | None = None,
    image_detail: str = 'low',
    profile_id: str | None = None,
) -> str:
    async def runner() -> str:
        return await _call_text(
            prompt,
            model=model,
            image_base64=image_base64,
            image_detail=image_detail,
            timeout=_resolve_timeout(timeout),
            profile_id=profile_id,
        )

    try:
        loop = asyncio.get_running_loop()
    except RuntimeError:
        return asyncio.run(runner())

    future = asyncio.run_coroutine_threadsafe(runner(), loop)
    return future.result(_resolve_timeout(timeout) + 5)
