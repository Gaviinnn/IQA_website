from __future__ import annotations

import zipfile
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List

from fastapi import APIRouter, BackgroundTasks, HTTPException
from fastapi.responses import FileResponse
from pydantic import BaseModel, Field

from backend.services.filtering_agent import build_filter_chat_turn, build_filter_plan
from backend.services.filtering_executor import execute_filter_dsl
from backend.services.filtering_tools import get_batch_result_items, resolve_export_source

router = APIRouter(prefix='/filtering', tags=['filtering'])

EXPORT_DIR = Path(__file__).resolve().parent.parent / 'uploads' / 'exports'
EXPORT_DIR.mkdir(parents=True, exist_ok=True)


class FilterPlanRequest(BaseModel):
    query: str = Field(..., min_length=1)
    messages: List[Dict[str, str]] = Field(default_factory=list)
    model: str | None = None
    provider_profile_id: str | None = None


class FilterRunRequest(BaseModel):
    dsl: Dict[str, Any] = Field(default_factory=dict)


class FilterExportRequest(BaseModel):
    kept_upload_ids: List[str] = Field(default_factory=list)
    filename: str | None = None


class FilterChatRequest(BaseModel):
    messages: List[Dict[str, str]] = Field(default_factory=list)
    active_upload_ids: List[str] = Field(default_factory=list)
    model: str | None = None
    provider_profile_id: str | None = None


@router.post('/batches/{batch_id}/plan')
async def plan_filter_route(batch_id: str, payload: FilterPlanRequest) -> dict[str, Any]:
    try:
        plan = await build_filter_plan(
            batch_id=batch_id.strip(),
            query=payload.query.strip(),
            conversation=payload.messages,
            model=payload.model,
            provider_profile_id=payload.provider_profile_id,
        )
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except Exception as exc:  # pragma: no cover
        raise HTTPException(status_code=500, detail='生成筛选方案失败') from exc
    return plan


def _build_chat_reply(plan: Dict[str, Any], run_result: Dict[str, Any]) -> str:
    summary = run_result.get('summary') or {}
    kept = summary.get('kept', 0)
    removed = summary.get('removed', 0)
    total = summary.get('total', 0)
    explanation = str(plan.get('assistant_message') or plan.get('explanation') or '已根据你的描述生成筛选规则。').strip()
    if not explanation.endswith(('。', '！', '？')):
        explanation = f'{explanation}。'
    return f'{explanation} 本轮共检查 {total} 张图片，保留 {kept} 张，移除 {removed} 张。'


@router.post('/batches/{batch_id}/chat')
async def chat_filter_route(batch_id: str, payload: FilterChatRequest) -> dict[str, Any]:
    batch_id = batch_id.strip()
    messages = payload.messages or []
    user_messages = [
        str(item.get('content') or '').strip()
        for item in messages
        if isinstance(item, dict) and str(item.get('role') or '').strip().lower() == 'user'
    ]
    query = user_messages[-1] if user_messages else ''
    if not query:
        raise HTTPException(status_code=400, detail='至少需要一条用户消息')

    try:
        turn = await build_filter_chat_turn(
            batch_id=batch_id,
            query=query,
            conversation=messages,
            active_upload_ids=payload.active_upload_ids,
            model=payload.model,
            provider_profile_id=payload.provider_profile_id,
        )
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except Exception as exc:  # pragma: no cover
        raise HTTPException(status_code=500, detail='执行对话筛选失败') from exc

    if not turn.get('should_execute'):
        return {
            'batch_id': batch_id,
            'query': query,
            'assistant_message': turn.get('assistant_message') or '已读取当前批次。',
            'did_execute': False,
            'turn': turn,
            'result': None,
        }

    try:
        items = await get_batch_result_items(batch_id)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc

    active_upload_ids = {item.strip() for item in payload.active_upload_ids if item and item.strip()}
    if active_upload_ids:
        items = [item for item in items if str(item.get('upload_id') or '').strip() in active_upload_ids]

    run_result = execute_filter_dsl(items, turn.get('dsl') or {})
    run_result['batch_id'] = batch_id
    return {
        'batch_id': batch_id,
        'query': query,
        'assistant_message': _build_chat_reply(turn, run_result),
        'did_execute': True,
        'turn': turn,
        'result': run_result,
    }


@router.post('/batches/{batch_id}/run')
async def run_filter_route(batch_id: str, payload: FilterRunRequest) -> dict[str, Any]:
    try:
        items = await get_batch_result_items(batch_id.strip())
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc

    result = execute_filter_dsl(items, payload.dsl or {})
    result['batch_id'] = batch_id.strip()
    return result


async def _delete_file_later(path: Path) -> None:
    try:
        path.unlink(missing_ok=True)
    except OSError:
        return


@router.post('/batches/{batch_id}/export')
async def export_filter_route(
    batch_id: str,
    payload: FilterExportRequest,
    background_tasks: BackgroundTasks,
) -> FileResponse:
    batch_id = batch_id.strip()
    upload_ids = [item.strip() for item in payload.kept_upload_ids if item and item.strip()]
    if not upload_ids:
        raise HTTPException(status_code=400, detail='kept_upload_ids 不能为空')

    timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
    safe_name = (payload.filename or f'filtered_{batch_id}_{timestamp}').strip().replace(' ', '_')
    zip_path = EXPORT_DIR / f'{safe_name}.zip'

    try:
        source_paths = []
        for upload_id in upload_ids:
            source_paths.append((upload_id, await resolve_export_source(upload_id)))
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc

    with zipfile.ZipFile(zip_path, 'w', compression=zipfile.ZIP_DEFLATED) as archive:
        for upload_id, source in source_paths:
            archive.write(source['path'], arcname=source['filename'])

    background_tasks.add_task(_delete_file_later, zip_path)
    return FileResponse(
        path=zip_path,
        filename=zip_path.name,
        media_type='application/zip',
    )
