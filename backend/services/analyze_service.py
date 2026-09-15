from __future__ import annotations

import asyncio
import logging
import os
import secrets
import time
from typing import Any, Dict, List

from fastapi import HTTPException

from backend.services.history_service import persist_analysis_result
from backend.services.skill_base import SkillContext, SkillRuntimeOptions
from backend.services.skill_registry import resolve_skills
from .uploads import PUBLIC_PREFIX, StoredUpload, load_metadata

logger = logging.getLogger('iqa.analyze.service')

MAX_CONCURRENCY = max(1, int(os.getenv('ANALYZE_MAX_CONCURRENCY', '3')))
_sem = asyncio.Semaphore(MAX_CONCURRENCY)


async def _run_skill_safe(skill: Any, context: SkillContext) -> tuple[str, Any]:
    started = time.perf_counter()
    try:
        outcome = await skill.run(context)
        return 'ok', outcome, int((time.perf_counter() - started) * 1000)
    except asyncio.TimeoutError:
        logger.warning('Skill timeout | id=%s | skill=%s', context.upload.upload_id, skill.skill_id)
        return 'timeout', None, int((time.perf_counter() - started) * 1000)
    except Exception as exc:  # pragma: no cover - defensive
        logger.exception('Skill failed | id=%s | skill=%s', context.upload.upload_id, skill.skill_id)
        return 'error', exc, int((time.perf_counter() - started) * 1000)


def _build_execution_stages(requested_skills: list[Any]) -> list[list[Any]]:
    stages: list[list[Any]] = []
    completed: set[str] = set()
    pending = list(requested_skills)

    while pending:
        stage = [
            skill for skill in pending
            if all(dependency in completed for dependency in getattr(skill, 'dependencies', ()))
        ]
        if not stage:
            unresolved = ', '.join(skill.skill_id for skill in pending)
            raise RuntimeError(f'Unresolved skill dependencies: {unresolved}')
        stages.append(stage)
        for skill in stage:
            completed.add(skill.skill_id)
        pending = [skill for skill in pending if skill.skill_id not in completed]
    return stages


async def analyze_uploads(
    upload_ids: List[str],
    *,
    detail: str = 'low',
    prompt: str | None = None,
    model: str | None = None,
    skills: List[str] | None = None,
    provider_profile_id: str | None = None,
) -> List[Dict[str, Any]]:
    uploads: List[StoredUpload] = []
    missing: List[str] = []
    batch_id = _make_batch_id()

    for upload_id in upload_ids:
        info = await load_metadata(upload_id)
        if info is None or not info.path.exists():
            missing.append(upload_id)
        else:
            uploads.append(info)

    if missing:
        logger.warning('Analyze missing uploads | ids=%s', missing)
        raise HTTPException(status_code=404, detail='文件不存在或已清理')

    try:
        resolved_skills = resolve_skills(skills)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    tasks = [
        asyncio.create_task(
            _analyze_with_lock(
                upload,
                detail=detail,
                prompt=prompt,
                model=model,
                requested_skills=resolved_skills,
                provider_profile_id=provider_profile_id,
                batch_id=batch_id,
                batch_size=len(uploads),
            )
        )
        for upload in uploads
    ]

    return await asyncio.gather(*tasks)


async def _analyze_with_lock(
    upload: StoredUpload,
    *,
    detail: str,
    prompt: str | None,
    model: str | None,
    requested_skills: list[Any],
    provider_profile_id: str | None,
    batch_id: str,
    batch_size: int,
) -> Dict[str, Any]:
    async with _sem:
        return await _analyze_single(
            upload,
            detail=detail,
            prompt=prompt,
            model=model,
            requested_skills=requested_skills,
            provider_profile_id=provider_profile_id,
            batch_id=batch_id,
            batch_size=batch_size,
        )


async def _analyze_single(
    upload: StoredUpload,
    *,
    detail: str,
    prompt: str | None,
    model: str | None,
    requested_skills: list[Any],
    provider_profile_id: str | None,
    batch_id: str,
    batch_size: int,
) -> Dict[str, Any]:
    logger.info('Running analysis pipeline | id=%s | skills=%s', upload.upload_id, [s.skill_id for s in requested_skills])
    start = time.perf_counter()

    context = SkillContext(
        upload=upload,
        runtime=SkillRuntimeOptions(
            detail=detail,
            prompt=prompt,
            model=model,
            provider_profile_id=provider_profile_id,
        ),
    )

    result: Dict[str, Any] = {
        'upload_id': upload.upload_id,
        'filename': upload.filename,
        'quality': None,
        'diagnostics': None,
        'quality_evidence': None,
        'quality_judge': None,
        'quality_fusion': None,
        'content': None,
        'semantic': None,
    }
    models: Dict[str, str] = {}
    warnings: list[str] = []
    skill_status: Dict[str, str] = {}
    skill_durations_ms: Dict[str, int] = {}

    for stage in _build_execution_stages(requested_skills):
        task_pairs = [
            (skill, asyncio.create_task(_run_skill_safe(skill, context)))
            for skill in stage
        ]

        for skill, task in task_pairs:
            status, payload, duration_ms = await task
            skill_durations_ms[skill.skill_id] = duration_ms
            if status == 'timeout':
                warnings.append(f'{skill.skill_id}: timeout')
                skill_status[skill.skill_id] = 'timeout'
                logger.warning('Skill finished | id=%s | skill=%s | status=%s | elapsed_ms=%s', upload.upload_id, skill.skill_id, status, duration_ms)
                continue
            if status == 'error':
                warnings.append(f'{skill.skill_id}: {payload}')
                skill_status[skill.skill_id] = 'error'
                logger.warning('Skill finished | id=%s | skill=%s | status=%s | elapsed_ms=%s', upload.upload_id, skill.skill_id, status, duration_ms)
                continue

            outcome = payload
            result.update(outcome.data)
            await context.merge_shared(outcome.data)
            models.update(outcome.models)
            warnings.extend(f'{skill.skill_id}: {warning}' for warning in outcome.warnings)
            skill_status[skill.skill_id] = 'ok'
            logger.info('Skill finished | id=%s | skill=%s | status=%s | elapsed_ms=%s', upload.upload_id, skill.skill_id, status, duration_ms)

    elapsed_ms = int((time.perf_counter() - start) * 1000)
    saved_at = _now_iso()
    degraded = any(status != 'ok' for status in skill_status.values()) or bool(warnings)

    result['meta'] = {
        'models': models,
        'detail': detail,
        'elapsed_ms': elapsed_ms,
        'degraded': degraded,
        'request_id': _make_request_id(),
        'batch_id': batch_id,
        'batch_size': batch_size,
        'skill_order': [skill.skill_id for skill in requested_skills],
        'skill_status': skill_status,
        'skill_durations_ms': skill_durations_ms,
    }
    if warnings:
        result['meta']['warnings'] = warnings
        result['meta']['reason'] = '; '.join(warnings)

    result['snapshot'] = {
        'image': f"{PUBLIC_PREFIX}/{upload.path.name}",
        'thumbnail': f"{PUBLIC_PREFIX}/{upload.thumbnail_path.name}",
        'saved_at': saved_at,
    }

    await persist_analysis_result(result)
    return result


def _make_request_id() -> str:
    return _now_iso(basic=True) + secrets.token_hex(4)


def _make_batch_id() -> str:
    return _now_iso(basic=True).replace('req_', 'bat_', 1) + secrets.token_hex(4)


def _now_iso(*, basic: bool = False) -> str:
    from datetime import datetime, timezone

    now = datetime.now(timezone.utc)
    if basic:
        return now.strftime('req_%Y%m%d_%H%M%S_')
    return now.isoformat()
