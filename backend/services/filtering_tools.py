from __future__ import annotations

import asyncio
import base64
from io import BytesIO
from typing import Any, Dict

import numpy as np
from PIL import Image

from backend.models.doubao_api import call_text_model
from backend.services.history_service import get_history_batch
from backend.services.skill_diagnostics import diagnose_rgb_array
from backend.services.uploads import load_metadata


def summarize_result_for_filtering(result: Dict[str, Any]) -> Dict[str, Any]:
    quality_fusion = result.get('quality_fusion') or {}
    quality_judge = result.get('quality_judge') or {}
    semantic = result.get('semantic') or {}
    content = result.get('content') or {}
    diagnostics = result.get('diagnostics') or {}
    snapshot = result.get('snapshot') or {}
    return {
        'upload_id': result.get('upload_id'),
        'filename': result.get('filename'),
        'quality_fusion': {
            'final_score': quality_fusion.get('final_score'),
            'level': quality_fusion.get('level'),
        },
        'quality_judge': {
            'sharpness_score': quality_judge.get('sharpness_score'),
            'noise_score': quality_judge.get('noise_score'),
            'exposure_score': quality_judge.get('exposure_score'),
            'contrast_score': quality_judge.get('contrast_score'),
            'compression_score': quality_judge.get('compression_score'),
            'overall_quality_score': quality_judge.get('overall_quality_score'),
            'confidence': quality_judge.get('confidence'),
            'reason': quality_judge.get('reason'),
            'key_issues': quality_judge.get('key_issues') or [],
        },
        'semantic': {
            'scene': semantic.get('scene'),
            'complexity': semantic.get('complexity'),
            'scene_clutter': semantic.get('scene_clutter'),
            'object_count': semantic.get('object_count'),
        },
        'content': {
            'caption': content.get('caption'),
        },
        'diagnostics': {
            'blur': diagnostics.get('blur'),
            'noise': diagnostics.get('noise'),
            'exposure': diagnostics.get('exposure'),
        },
        'snapshot': {
            'thumbnail': snapshot.get('thumbnail'),
            'image': snapshot.get('image'),
        },
    }


async def get_batch_result_items(batch_id: str) -> list[Dict[str, Any]]:
    batch = await get_history_batch(batch_id)
    if not batch:
        raise ValueError('历史批次不存在')
    items = []
    for item in batch.get('items') or []:
        result = item.get('result') or item
        if result:
            items.append(result)
    return items


async def list_batch_items(batch_id: str) -> Dict[str, Any]:
    items = await get_batch_result_items(batch_id)
    summaries = [summarize_result_for_filtering(item) for item in items]
    return {
        'batch_id': batch_id,
        'count': len(summaries),
        'items': summaries,
    }


async def get_item_quality_summary(upload_id: str, batch_id: str | None = None) -> Dict[str, Any]:
    if batch_id:
        items = await get_batch_result_items(batch_id)
        for item in items:
            if item.get('upload_id') == upload_id:
                return summarize_result_for_filtering(item)
    metadata = await load_metadata(upload_id)
    if metadata is None:
        raise ValueError('图片不存在')
    return {
        'upload_id': upload_id,
        'filename': metadata.filename,
        'snapshot': {
            'thumbnail': f'/uploads/{metadata.thumbnail_path.name}',
            'image': f'/uploads/{metadata.path.name}',
        },
    }


async def _load_rgb_array(upload_id: str) -> np.ndarray:
    metadata = await load_metadata(upload_id)
    if metadata is None:
        raise ValueError(f'图片不存在: {upload_id}')
    source_path = metadata.original_path if metadata.original_path and metadata.original_path.exists() else metadata.path
    raw = await asyncio.to_thread(source_path.read_bytes)

    def _load() -> np.ndarray:
        with Image.open(BytesIO(raw)) as image:
            return np.asarray(image.convert('RGB'))

    return await asyncio.to_thread(_load)


async def _read_image_base64(upload_id: str) -> str:
    metadata = await load_metadata(upload_id)
    if metadata is None:
        raise ValueError(f'图片不存在: {upload_id}')
    source_path = metadata.original_path if metadata.original_path and metadata.original_path.exists() else metadata.path
    raw = await asyncio.to_thread(source_path.read_bytes)
    return await asyncio.to_thread(lambda: base64.b64encode(raw).decode('ascii'))


async def _compute_diagnostics(upload_id: str) -> Dict[str, Any]:
    rgb = await _load_rgb_array(upload_id)
    return await asyncio.to_thread(diagnose_rgb_array, rgb)


async def compute_blur_metrics(upload_id: str) -> Dict[str, Any]:
    diagnostics = await _compute_diagnostics(upload_id)
    metrics = diagnostics.get('metrics') or {}
    return {
        'upload_id': upload_id,
        'blur': diagnostics.get('blur'),
        'blur_score': metrics.get('blur_score'),
        'median_gradient': metrics.get('median_gradient'),
        'low_gradient_percentile': metrics.get('low_gradient_percentile'),
        'edge_density': metrics.get('edge_density'),
        'informative_patch_ratio': metrics.get('informative_patch_ratio'),
    }


async def compute_noise_metrics(upload_id: str) -> Dict[str, Any]:
    diagnostics = await _compute_diagnostics(upload_id)
    metrics = diagnostics.get('metrics') or {}
    return {
        'upload_id': upload_id,
        'noise': diagnostics.get('noise'),
        'noise_score': metrics.get('noise_score'),
        'flat_patch_gradient_threshold': metrics.get('flat_patch_gradient_threshold'),
    }


async def compute_exposure_metrics(upload_id: str) -> Dict[str, Any]:
    diagnostics = await _compute_diagnostics(upload_id)
    metrics = diagnostics.get('metrics') or {}
    return {
        'upload_id': upload_id,
        'exposure': diagnostics.get('exposure'),
        'brightness_mean': metrics.get('brightness_mean'),
        'low_clip_ratio': metrics.get('low_clip_ratio'),
        'high_clip_ratio': metrics.get('high_clip_ratio'),
        'exposure_severity': metrics.get('exposure_severity'),
    }


async def inspect_image(
    upload_id: str,
    *,
    focus: str | None = None,
    model: str | None = None,
    provider_profile_id: str | None = None,
) -> Dict[str, Any]:
    metadata = await load_metadata(upload_id)
    if metadata is None:
        raise ValueError(f'图片不存在: {upload_id}')
    image_base64 = await _read_image_base64(upload_id)
    prompt = (
        '你是图片整理助手，正在直接查看一张图片。'
        '请用自然中文简洁描述这张图的场景、光线、清晰度以及是否适合被保留。'
        '如果给出了 focus，请优先围绕该问题回答。'
        '不要输出 JSON，不要复述字段名。'
        f'\nfocus: {focus or "整体观察"}'
    )
    observation = await call_text_model(
        prompt,
        model=model,
        timeout=30,
        image_base64=image_base64,
        profile_id=provider_profile_id,
    )
    return {
        'upload_id': upload_id,
        'filename': metadata.filename,
        'focus': focus,
        'observation': (observation or '').strip(),
    }


async def inspect_batch_images(
    batch_id: str,
    *,
    focus: str | None = None,
    upload_ids: list[str] | None = None,
    limit: int = 6,
    model: str | None = None,
    provider_profile_id: str | None = None,
) -> Dict[str, Any]:
    items = await get_batch_result_items(batch_id)
    if upload_ids:
        chosen = [item for item in items if item.get('upload_id') in set(upload_ids)]
    else:
        chosen = items[: max(1, min(limit, 6))]

    observations = []
    for item in chosen:
        upload_id = str(item.get('upload_id') or '').strip()
        if not upload_id:
            continue
        inspected = await inspect_image(
            upload_id,
            focus=focus,
            model=model,
            provider_profile_id=provider_profile_id,
        )
        observations.append(
            {
                'upload_id': inspected['upload_id'],
                'filename': inspected['filename'],
                'observation': inspected['observation'],
            }
        )

    return {
        'batch_id': batch_id,
        'focus': focus,
        'count': len(observations),
        'observations': observations,
    }


async def resolve_export_source(upload_id: str) -> Dict[str, Any]:
    metadata = await load_metadata(upload_id)
    if metadata is None:
        raise ValueError(f'图片不存在: {upload_id}')
    source_path = metadata.original_path if metadata.original_path and metadata.original_path.exists() else metadata.path
    return {
        'path': source_path,
        'filename': metadata.filename or source_path.name,
        'is_original': bool(metadata.original_path and metadata.original_path.exists()),
    }


TOOL_DEFINITIONS = {
    'list_batch_items': {
        'description': '列出 batch 内图片的筛选摘要，包含融合分、LLM 审阅分与语义信息。',
        'args': {'batch_id': 'string'},
    },
    'get_item_quality_summary': {
        'description': '获取单张图片的质量摘要。',
        'args': {'upload_id': 'string'},
    },
    'compute_blur_metrics': {
        'description': '重新计算单张图片的 blur 低层指标，用于精细清晰度判断。',
        'args': {'upload_id': 'string'},
    },
    'compute_noise_metrics': {
        'description': '重新计算单张图片的 noise 低层指标，用于精细噪声判断。',
        'args': {'upload_id': 'string'},
    },
    'compute_exposure_metrics': {
        'description': '重新计算单张图片的 exposure 低层指标，用于精细曝光判断。',
        'args': {'upload_id': 'string'},
    },
    'inspect_image': {
        'description': '直接让多模态模型重新查看单张图片，适合回答场景、内容、主观保留价值等问题。',
        'args': {'upload_id': 'string', 'focus': 'string'},
    },
    'inspect_batch_images': {
        'description': '直接让多模态模型重新查看一个 batch 里的若干图片，适合判断是否存在夜景、室内、展示图等高层问题。',
        'args': {'batch_id': 'string', 'focus': 'string', 'upload_ids': 'string[]', 'limit': 'number'},
    },
}
