from __future__ import annotations

from typing import Any, Dict, List

from backend.models.doubao_api import (
    DoubaoError,
    call_structured_vision,
    call_with_timeout,
    parse_vision_response_text,
)
from backend.services.provider_profiles import (
    get_active_provider_profile,
    get_model_display_name,
    get_provider_profile,
)

from .skill_base import AnalysisSkill, SkillContext, SkillOutcome

ALLOWED_COMPLEXITY = {'low', 'medium', 'high'}
ALLOWED_CLUTTER = {'low', 'medium', 'high'}
ALLOWED_SCENES = {
    'indoor',
    'outdoor',
    'landscape',
    'portrait',
    'food',
    'document',
    'urban',
    'nature',
    'product',
    'other',
}


def _normalize_label(value: Any, *, allowed: set[str], fallback: str) -> str:
    if isinstance(value, str):
        normalized = value.strip().lower()
        if normalized in allowed:
            return normalized
    return fallback


def _sanitize_objects(value: Any) -> List[Dict[str, Any]]:
    objects: List[Dict[str, Any]] = []
    if not isinstance(value, list):
        return objects

    for item in value:
        if not isinstance(item, dict):
            continue
        label = item.get('label') or item.get('name') or item.get('category')
        score = item.get('score') if 'score' in item else item.get('confidence')
        if not isinstance(label, str) or not label.strip():
            continue
        try:
            numeric_score = float(score)
        except Exception:
            numeric_score = 0.0
        if numeric_score > 1.0 and numeric_score <= 100.0:
            numeric_score = numeric_score / 100.0
        numeric_score = max(0.0, min(1.0, numeric_score))
        objects.append({'label': label.strip(), 'score': round(numeric_score, 3)})
    return objects


def _sanitize_tags(value: Any) -> List[str]:
    if not isinstance(value, list):
        return []
    tags: List[str] = []
    seen: set[str] = set()
    for item in value:
        if not isinstance(item, str):
            continue
        tag = item.strip()
        if not tag or tag in seen:
            continue
        seen.add(tag)
        tags.append(tag)
    return tags


def _build_semantic_prompt(custom_prompt: str | None) -> str:
    base_prompt = (
        '请分析这张图片，并且只输出 JSON。'
        '返回字段必须包含 '
        '{"caption": string, "objects": [{"label": string, "score": number}], '
        '"scene": string, "object_count": number, "complexity": string, '
        '"scene_clutter": string, "semantic_tags": [string]}。'
        '要求：caption 使用中文；objects 最多 8 个；'
        'scene 只能是 indoor/outdoor/landscape/portrait/food/document/urban/nature/product/other 之一；'
        'complexity 只能是 low/medium/high；'
        'scene_clutter 只能是 low/medium/high；'
        'object_count 给出估计值；不要输出 Markdown，不要输出任何额外解释。'
    )
    if not custom_prompt:
        return base_prompt
    return f'{base_prompt}\n补充要求：{custom_prompt.strip()}'


def _build_caption_prompt(custom_prompt: str | None) -> str:
    base_prompt = (
        '请只返回 JSON：'
        '{"caption": string, "objects": [{"label": string, "score": number}]}。'
        'caption 使用中文，objects 最多 8 个，不要输出额外说明。'
    )
    if not custom_prompt:
        return base_prompt
    return f'{base_prompt}\n补充要求：{custom_prompt.strip()}'


def _combine_text(caption: str | None, objects: List[Dict[str, Any]]) -> str:
    labels = ' '.join(item.get('label', '') for item in objects)
    return f'{caption or ""} {labels}'.strip().lower()


def _infer_scene(caption: str | None, objects: List[Dict[str, Any]]) -> str:
    text = _combine_text(caption, objects)
    if any(token in text for token in ('document', 'paper', 'text', 'chart', 'table', 'report', 'documento', '文档', '图表')):
        return 'document'
    if any(token in text for token in ('portrait', 'face', 'person', 'selfie', '人物', '人像', '女孩', '男孩')):
        return 'portrait'
    if any(token in text for token in ('food', 'meal', 'dish', 'plate', '餐', '食物', '美食')):
        return 'food'
    if any(token in text for token in ('product', 'bottle', 'package', 'shoe', 'bag', '商品')):
        return 'product'
    if any(token in text for token in ('street', 'building', 'city', 'road', 'urban', '城市', '街道')):
        return 'urban'
    if any(token in text for token in ('mountain', 'forest', 'grass', 'lake', 'ocean', 'river', 'tree', 'sky', 'beach', '自然', '风景', '海边')):
        return 'landscape'
    if any(token in text for token in ('room', 'desk', 'kitchen', 'sofa', 'bed', 'office', '室内', '桌子')):
        return 'indoor'
    if any(token in text for token in ('outdoor', 'park', 'field', 'outdoors', '户外', '公园')):
        return 'outdoor'
    return 'other'


def _infer_complexity(caption: str | None, objects: List[Dict[str, Any]]) -> str:
    object_count = len(objects)
    caption_length = len((caption or '').strip())
    if object_count >= 6 or caption_length >= 40:
        return 'high'
    if object_count <= 2 and caption_length <= 16:
        return 'low'
    return 'medium'


def _infer_scene_clutter(objects: List[Dict[str, Any]]) -> str:
    object_count = len(objects)
    if object_count >= 6:
        return 'high'
    if object_count <= 2:
        return 'low'
    return 'medium'


def _build_semantic_payload(payload: Dict[str, Any], caption: str | None, objects: List[Dict[str, Any]]) -> Dict[str, Any]:
    object_count_raw = payload.get('object_count')
    try:
        object_count = max(0, int(object_count_raw))
    except Exception:
        object_count = len(objects)

    semantic_tags = _sanitize_tags(payload.get('semantic_tags') or payload.get('tags'))
    if not semantic_tags:
        semantic_tags = [item['label'] for item in objects[:5] if item.get('label')]

    return {
        'scene': _normalize_label(payload.get('scene'), allowed=ALLOWED_SCENES, fallback=_infer_scene(caption, objects)),
        'object_count': object_count,
        'complexity': _normalize_label(
            payload.get('complexity'),
            allowed=ALLOWED_COMPLEXITY,
            fallback=_infer_complexity(caption, objects),
        ),
        'scene_clutter': _normalize_label(
            payload.get('scene_clutter'),
            allowed=ALLOWED_CLUTTER,
            fallback=_infer_scene_clutter(objects),
        ),
        'semantic_tags': semantic_tags,
    }


class SemanticAnalysisSkill(AnalysisSkill):
    skill_id = 'semantic'
    aliases = ('semantic_analysis', 'semantic_analysis_skill', 'caption', 'scene')
    description = 'Generate caption, object list, scene classification, and semantic complexity.'

    async def run(self, context: SkillContext) -> SkillOutcome:
        base64_image = await context.read_base64()
        structured_prompt = _build_semantic_prompt(context.runtime.prompt)
        warnings: list[str] = []
        profile = await (
            get_provider_profile(context.runtime.provider_profile_id)
            if context.runtime.provider_profile_id
            else get_active_provider_profile()
        )
        selected_model = get_model_display_name(profile) if profile else (context.runtime.model or 'No active provider')

        try:
            response = await call_structured_vision(
                base64_image=base64_image,
                prompt=structured_prompt,
                detail=context.runtime.detail,
                model=context.runtime.model,
                profile_id=context.runtime.provider_profile_id,
            )
            payload = response.payload
            caption = payload.get('caption')
            caption = caption.strip() if isinstance(caption, str) and caption.strip() else None
            objects = _sanitize_objects(payload.get('objects'))
            semantic = _build_semantic_payload(payload, caption, objects)
        except DoubaoError as exc:
            raw_fallback = parse_vision_response_text(exc.raw_text) if getattr(exc, 'raw_text', None) else None
            if raw_fallback and (raw_fallback.caption or raw_fallback.objects):
                caption = raw_fallback.caption.strip() if isinstance(raw_fallback.caption, str) and raw_fallback.caption.strip() else None
                objects = _sanitize_objects(raw_fallback.objects)
                semantic = _build_semantic_payload({}, caption, objects)
                warnings.append(f'结构化语义输出解析失败，已基于首个响应降级补全: {exc}')
            else:
                fallback = await call_with_timeout(
                    base64_image=base64_image,
                    detail=context.runtime.detail,
                    prompt=_build_caption_prompt(context.runtime.prompt),
                    model=context.runtime.model,
                    profile_id=context.runtime.provider_profile_id,
                )
                caption = fallback.caption.strip() if isinstance(fallback.caption, str) and fallback.caption.strip() else None
                objects = _sanitize_objects(fallback.objects)
                semantic = _build_semantic_payload({}, caption, objects)
                warnings.append(f'结构化语义输出解析失败，已回退为启发式补全: {exc}')

        return SkillOutcome(
            skill_id=self.skill_id,
            data={
                'content': {
                    'caption': caption,
                    'objects': objects,
                },
                'semantic': semantic,
            },
            models={
                'content': selected_model,
                'semantic': selected_model,
            },
            warnings=warnings,
        )
