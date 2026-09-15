from __future__ import annotations

import json
import re
from typing import Any, Dict, List

from backend.models.doubao_api import DoubaoError, call_text_model

from .filtering_tools import (
    TOOL_DEFINITIONS,
    compute_blur_metrics,
    compute_exposure_metrics,
    compute_noise_metrics,
    inspect_batch_images,
    inspect_image,
    list_batch_items,
)

MAX_AGENT_STEPS = 4

SCENE_LABELS = {
    'indoor': '室内',
    'outdoor': '室外',
    'landscape': '风景',
    'portrait': '人像',
    'food': '食物',
    'document': '文档',
    'urban': '城市',
    'nature': '自然',
    'product': '物品',
    'other': '其他',
}

COMPLEXITY_LABELS = {
    'low': '低',
    'medium': '中',
    'high': '高',
}


def _extract_json(text: str) -> Dict[str, Any] | None:
    raw = (text or '').strip()
    if not raw:
        return None
    match = re.search(r'\{.*\}', raw, flags=re.S)
    if not match:
        return None
    try:
        return json.loads(match.group(0))
    except Exception:
        return None


def _tool_specs_text() -> str:
    lines = []
    for name, spec in TOOL_DEFINITIONS.items():
        lines.append(f"- {name}: {spec['description']} | args={json.dumps(spec['args'], ensure_ascii=False)}")
    return '\n'.join(lines)


def _compact_conversation(messages: List[Dict[str, str]] | None) -> str:
    history = []
    for item in messages or []:
        if not isinstance(item, dict):
            continue
        role = str(item.get('role') or '').strip().lower()
        content = str(item.get('content') or '').strip()
        if role not in {'user', 'assistant'} or not content:
            continue
        history.append({'role': role, 'content': content})
    if not history:
        return '[]'
    return json.dumps(history[-8:], ensure_ascii=False, indent=2)


def _looks_like_filter_request(query: str) -> bool:
    text = (query or '').strip().lower()
    filter_keywords = (
        '筛选', '保留', '去掉', '删除', '过滤', '只留', '留下', '移除', '剔除',
        '只要', '只保留', '帮我选', '导出', '下载结果',
    )
    return any(keyword in text for keyword in filter_keywords)


def _looks_like_visual_question(query: str) -> bool:
    text = (query or '').strip().lower()
    keywords = (
        '夜晚', '夜景', '白天', '黄昏', '傍晚', '场景', '室内', '室外',
        '夕阳', '晚霞', '建筑', '人物', '主体', '风格', '氛围', '构图',
        '有没有', '是否有', '哪些图', '哪几张', '适合展示', '适合做封面',
        '适合保留', '最好看', '像不像', '主要是什么', '看起来', '内容', '图里', '这批图',
    )
    return any(keyword in text for keyword in keywords)


def _extract_limit(query: str) -> int | None:
    text = (query or '').strip()
    match = re.search(r'(\d+)\s*张', text)
    if match:
        value = int(match.group(1))
        return value if value > 0 else None

    chinese_match = re.search(r'([零一二两三四五六七八九十百]+)\s*张', text)
    if chinese_match:
        value = _parse_chinese_count(chinese_match.group(1))
        return value if value and value > 0 else None

    leading_match = re.search(r'前\s*(\d+)', text)
    if leading_match:
        value = int(leading_match.group(1))
        return value if value > 0 else None

    leading_chinese_match = re.search(r'前\s*([零一二两三四五六七八九十百]+)', text)
    if leading_chinese_match:
        value = _parse_chinese_count(leading_chinese_match.group(1))
        return value if value and value > 0 else None

    return None


def _parse_chinese_count(token: str) -> int | None:
    text = (token or '').strip()
    if not text:
        return None

    direct_map = {
        '零': 0,
        '一': 1,
        '二': 2,
        '两': 2,
        '三': 3,
        '四': 4,
        '五': 5,
        '六': 6,
        '七': 7,
        '八': 8,
        '九': 9,
        '十': 10,
    }
    if text in direct_map:
        return direct_map[text]

    if text == '百':
        return 100

    if '百' in text:
        hundreds_part, _, remainder = text.partition('百')
        hundreds = direct_map.get(hundreds_part or '一')
        if hundreds is None:
            return None
        tail = _parse_chinese_count(remainder) or 0
        return hundreds * 100 + tail

    if '十' in text:
        tens_part, _, ones_part = text.partition('十')
        tens = 1 if tens_part == '' else direct_map.get(tens_part)
        ones = 0 if ones_part == '' else direct_map.get(ones_part)
        if tens is None or ones is None:
            return None
        return tens * 10 + ones

    value = 0
    for char in text:
        digit = direct_map.get(char)
        if digit is None:
            return None
        value = value * 10 + digit
    return value


def _infer_single_item_limit(text: str, *, highest_intent: bool) -> int | None:
    if not highest_intent:
        return None

    singular_markers = (
        '那张',
        '这一张',
        '这一張',
        '这张',
        '一张',
        '1张',
        '单张',
        '唯一一张',
    )
    return 1 if any(marker in text for marker in singular_markers) else None


def _explicit_sort_intent(query: str) -> tuple[str | None, str]:
    text = (query or '').strip().lower()

    if any(keyword in text for keyword in ('综合质量分最高', '综合质量最高', '综合分最高', '融合质量分最高', '最终质量分最高')):
        return 'quality_fusion.final_score', 'desc'
    if any(keyword in text for keyword in ('质量最高', '评分最高', '最高分', '质量最好', '分数最高')):
        return 'quality_fusion.final_score', 'desc'
    if any(keyword in text for keyword in ('最清晰', '清晰度最高', '锐度最高', '最锐利')):
        return 'quality_judge.sharpness_score', 'desc'
    if any(keyword in text for keyword in ('曝光最好', '曝光最正常')):
        return 'quality_judge.exposure_score', 'desc'
    if any(keyword in text for keyword in ('对比度最好', '层次最好')):
        return 'quality_judge.contrast_score', 'desc'
    if any(keyword in text for keyword in ('噪声最少', '噪点最少', '最干净')):
        return 'quality_judge.noise_score', 'desc'
    return None, 'desc'


def _normalize_filter_dsl(query: str, dsl: Dict[str, Any] | None, *, domain_count: int | None = None) -> Dict[str, Any]:
    normalized = dict(dsl or {})
    text = (query or '').strip().lower()
    explicit_field, direction = _explicit_sort_intent(query)
    highest_intent = any(keyword in text for keyword in ('最高', '最好', 'top', '前'))
    limit = _extract_limit(query) or _infer_single_item_limit(text, highest_intent=highest_intent)
    remove_worst_intent = (
        any(keyword in text for keyword in ('去掉', '移除', '删除', '剔除'))
        and any(keyword in text for keyword in ('最差', '最低', '最不好', '最低分'))
    )

    mode = str(normalized.get('mode') or 'keep_matching').strip().lower()
    if mode not in {'keep_matching', 'remove_matching'}:
        mode = 'keep_matching'
    if '保留' in text or '只留' in text or '留下' in text:
        mode = 'keep_matching'
    normalized['mode'] = mode

    logic = str(normalized.get('logic') or 'and').strip().lower()
    normalized['logic'] = logic if logic in {'and', 'or'} else 'and'

    rules = normalized.get('rules')
    if not isinstance(rules, list):
        rules = []

    if explicit_field:
        rules = [
            rule
            for rule in rules
            if not isinstance(rule, dict)
            or not str(rule.get('field') or '').startswith('quality_')
            or str(rule.get('field') or '').strip() == explicit_field
        ]
        if highest_intent:
            rules = [
                rule
                for rule in rules
                if not isinstance(rule, dict) or str(rule.get('field') or '').strip() != explicit_field
            ]
        normalized['sort'] = {'field': explicit_field, 'direction': direction}
    elif not isinstance(normalized.get('sort'), dict):
        normalized['sort'] = {'field': 'quality_fusion.final_score', 'direction': 'desc'}

    if remove_worst_intent and limit is not None and domain_count and domain_count > limit:
        normalized['mode'] = 'keep_matching'
        normalized['rules'] = []
        normalized['sort'] = {'field': explicit_field or 'quality_fusion.final_score', 'direction': 'desc'}
        normalized['limit'] = domain_count - limit
        return normalized

    if limit is not None:
        normalized['limit'] = limit

    normalized['rules'] = rules
    return normalized


def _label_scene(value: Any) -> str | None:
    if not isinstance(value, str):
        return None
    key = value.strip().lower()
    return SCENE_LABELS.get(key, value.strip())


def _label_complexity(value: Any) -> str | None:
    if not isinstance(value, str):
        return None
    key = value.strip().lower()
    return COMPLEXITY_LABELS.get(key, value.strip())


def _compact_batch_summary(batch_payload: Dict[str, Any]) -> str:
    rows = []
    for item in batch_payload.get('items') or []:
        qf = item.get('quality_fusion') or {}
        judge = item.get('quality_judge') or {}
        semantic = item.get('semantic') or {}
        content = item.get('content') or {}
        rows.append(
            {
                '图片': item.get('filename') or item.get('upload_id'),
                '综合质量分': qf.get('final_score'),
                '清晰度评分': judge.get('sharpness_score'),
                '噪声控制评分': judge.get('noise_score'),
                '曝光评分': judge.get('exposure_score'),
                '场景': _label_scene(semantic.get('scene')),
                '复杂度': _label_complexity(semantic.get('complexity')),
                '简述': content.get('caption'),
                '对象': content.get('objects') or [],
                '标签': semantic.get('semantic_tags') or [],
                '关键问题': judge.get('key_issues') or [],
            }
        )
    return json.dumps(rows, ensure_ascii=False, indent=2)


def _polish_assistant_message(text: str) -> str:
    message = (text or '').strip()
    if not message:
        return '我已经读取当前批次。你可以继续问我批次内容，或者直接说保留/去掉什么类型的图片。'
    message = re.sub(r'\s+', ' ', message).strip()
    if not message.endswith(('。', '！', '？')):
        message = f'{message}。'
    return message


async def _answer_with_visual_review(
    *,
    batch_id: str,
    query: str,
    active_upload_ids: List[str] | None = None,
    model: str | None = None,
    provider_profile_id: str | None = None,
) -> Dict[str, Any] | None:
    observations = await inspect_batch_images(
        batch_id,
        focus=query,
        upload_ids=active_upload_ids,
        limit=6,
        model=model,
        provider_profile_id=provider_profile_id,
    )
    if not observations.get('observations'):
        return None

    prompt = (
        '你是图片整理助手。下面是你重新直接查看一组图片后得到的观察记录。'
        '请只根据这些观察，用自然中文回答用户问题。'
        '回答要直接、简洁、像产品里的助手回复，不要提工具、字段、JSON、batch 摘要。'
        '如果无法确认，就明确说“目前看不出”或“这批图片里没有明显的……”。'
        f'\n用户问题：{query}'
        f'\n观察记录：{json.dumps(observations, ensure_ascii=False)}'
    )
    try:
        reply = await call_text_model(
            prompt,
            model=model,
            timeout=30,
            profile_id=provider_profile_id,
        )
    except DoubaoError:
        return None

    return {
        'assistant_message': _polish_assistant_message(reply),
        'tool_trace': [
            {
                'tool_name': 'inspect_batch_images',
                'tool_args': {'batch_id': batch_id, 'focus': query, 'limit': 6},
                'reason': '用户在问场景/内容类问题，直接看图更可靠。',
                'tool_result': observations,
            }
        ],
        'mode': 'visual_fallback_reply',
    }


async def _seed_visual_trace(
    *,
    batch_id: str,
    query: str,
    active_upload_ids: List[str] | None = None,
    model: str | None = None,
    provider_profile_id: str | None = None,
) -> List[Dict[str, Any]]:
    observations = await inspect_batch_images(
        batch_id,
        focus=query,
        upload_ids=active_upload_ids,
        limit=6,
        model=model,
        provider_profile_id=provider_profile_id,
    )
    if not observations.get('observations'):
        return []
    return [
        {
            'tool_name': 'inspect_batch_images',
            'tool_args': {'batch_id': batch_id, 'focus': query, 'limit': 6},
            'reason': '该问题涉及场景、内容或主观展示价值，先直接看图再回答更可靠。',
            'tool_result': observations,
        }
    ]


def _fallback_plan(query: str, *, domain_count: int | None = None) -> Dict[str, Any]:
    text = (query or '').strip().lower()
    rules: List[Dict[str, Any]] = []
    explanation_parts: List[str] = []
    mode = 'keep_matching'

    remove_intent = any(keyword in text for keyword in ('去掉', '删除', '过滤', '移除', '剔除', '不要'))

    if any(keyword in text for keyword in ('模糊', '清晰', '失焦')):
        if remove_intent:
            rules.append({'field': 'quality_judge.sharpness_score', 'op': '>=', 'value': 60})
            explanation_parts.append('保留清晰度评分不低于 60 的图片')
        else:
            rules.append({'field': 'quality_judge.sharpness_score', 'op': '>=', 'value': 60})
            explanation_parts.append('优先保留清晰图片')

    if '噪声' in text:
        rules.append({'field': 'quality_judge.noise_score', 'op': '>=', 'value': 60})
        explanation_parts.append('去除噪声评分过低的图片')

    if '曝光' in text:
        rules.append({'field': 'quality_judge.exposure_score', 'op': '>=', 'value': 65})
        explanation_parts.append('保留曝光正常的图片')

    if '质量' in text or '高质量' in text:
        rules.append({'field': 'quality_fusion.final_score', 'op': '>=', 'value': 65})
        explanation_parts.append('保留综合质量分较高的图片')

    content_keywords = [
        (('人物', '人像', '人脸', '有人'), '人物'),
        (('建筑', '楼', '城市', '街景'), '建筑'),
        (('夜景', '夜晚', '晚上', '夜间'), '夜'),
        (('风景', '自然', '草地', '天空'), '风景'),
        (('室内',), '室内'),
        (('室外', '户外'), '室外'),
        (('文档', '文字', '截图'), '文档'),
        (('食物', '餐饮'), '食物'),
    ]
    content_rules = []
    for markers, expected in content_keywords:
        if any(marker in text for marker in markers):
            content_rules.append({'field': 'content.search_text', 'op': 'contains', 'value': expected})
            explanation_parts.append(f"匹配包含“{expected}”相关内容的图片")

    if content_rules:
        if remove_intent and not any(keyword in text for keyword in ('模糊', '噪声', '曝光', '质量', '高质量')):
            mode = 'remove_matching'
        rules.extend(content_rules)

    limit = _extract_limit(query)
    if not rules:
        rules.append({'field': 'quality_fusion.final_score', 'op': '>=', 'value': 60})
        explanation_parts.append('默认保留综合质量分不低于 60 的图片')

    return {
        'dsl': _normalize_filter_dsl(
            query,
            {
            'mode': mode,
            'logic': 'and',
            'rules': rules,
            'sort': {'field': 'quality_fusion.final_score', 'direction': 'desc'},
            'limit': limit,
            },
            domain_count=domain_count,
        ),
        'explanation': '；'.join(explanation_parts) + '。',
    }


def _build_agent_prompt(
    *,
    query: str,
    batch_summary: str,
    trace: List[Dict[str, Any]],
    conversation: List[Dict[str, str]] | None = None,
) -> str:
    return (
        '你是图像筛选 Agent。你的任务是把用户的自然语言筛图需求转成可执行 DSL。'
        '你可以在必要时调用工具，但只有在已有 batch 摘要不足以做出稳定决策时才调用。'
        '输出必须是 JSON。\n'
        '允许的动作只有两种：\n'
        '1. {"action":"use_tool","tool_name":"...","tool_args":{...},"reason":"..."}\n'
        '2. {"action":"final","dsl":{...},"explanation":"..."}\n'
        'DSL 结构：{"mode":"keep_matching|remove_matching","logic":"and|or","rules":[{"field":"...","op":"...","value":...}],"sort":{"field":"...","direction":"asc|desc"},"limit":number|null}\n'
        '可用字段：quality_fusion.final_score, quality_judge.sharpness_score, quality_judge.noise_score, quality_judge.exposure_score, quality_judge.contrast_score, quality_judge.compression_score, quality_judge.overall_quality_score, semantic.scene, semantic.complexity, semantic.scene_clutter, semantic.object_count, semantic.semantic_tags, content.caption, content.objects, content.search_text, filename\n'
        f'可用工具：\n{_tool_specs_text()}\n'
        f'对话历史：\n{_compact_conversation(conversation)}\n'
        f'用户请求：{query}\n'
        f'Batch 摘要：\n{batch_summary}\n'
        f'当前工具调用轨迹：\n{json.dumps(trace, ensure_ascii=False, indent=2)}\n'
        '要求：如果用户要求涉及模糊、噪声、曝光的细粒度技术判断，而 batch 摘要信息不足以稳定决策，可以选择 use_tool。'
        '如果信息已经足够，请直接返回 final。不要输出额外解释文字。'
    )


def _build_chat_prompt(
    *,
    query: str,
    batch_summary: str,
    trace: List[Dict[str, Any]],
    conversation: List[Dict[str, str]] | None = None,
) -> str:
    return (
        '你是“图片整理助手”。你要结合当前批次图片摘要、必要时的直接看图结果，以及对话上下文，判断用户这句话是在：'
        '1. 咨询/确认信息；'
        '2. 明确要求执行筛选。'
        '输出必须是 JSON。\n'
        '允许的动作只有三种：\n'
        '1. {"action":"use_tool","tool_name":"...","tool_args":{...},"reason":"..."}\n'
        '2. {"action":"reply","message":"..."}\n'
        '3. {"action":"filter","dsl":{...},"message":"..."}\n'
        '如果用户只是在问问题、确认场景、询问某类图片是否存在、或者还没明确要求执行筛选，返回 reply。'
        '只有在用户明确表示要保留/去掉/筛选/过滤某类图片时，才返回 filter。'
        'reply 的 message 应该自然、简洁、面向用户，可以自由组织措辞。'
        '不要直接复述内部字段名、工具名或 JSON 结构。'
        'filter 的 message 也要自然，说明你将按什么条件筛选。'
        'DSL 结构：{"mode":"keep_matching|remove_matching","logic":"and|or","rules":[{"field":"...","op":"...","value":...}],"sort":{"field":"...","direction":"asc|desc"},"limit":number|null}\n'
        '可用字段：quality_fusion.final_score, quality_judge.sharpness_score, quality_judge.noise_score, quality_judge.exposure_score, quality_judge.contrast_score, quality_judge.compression_score, quality_judge.overall_quality_score, semantic.scene, semantic.complexity, semantic.scene_clutter, semantic.object_count, semantic.semantic_tags, content.caption, content.objects, content.search_text, filename\n'
        f'可用工具：\n{_tool_specs_text()}\n'
        f'对话历史：\n{_compact_conversation(conversation)}\n'
        f'用户最新消息：{query}\n'
        f'Batch 摘要：\n{batch_summary}\n'
        f'当前工具调用轨迹：\n{json.dumps(trace, ensure_ascii=False, indent=2)}\n'
        '如果用户的问题涉及场景、内容、主观保留价值、夜景/黄昏/室内外判断，或者你觉得仅靠字段不够可靠，应优先调用 inspect_image 或 inspect_batch_images 直接看图后再回答。'
        '对于“有没有夜景”“这批图像主要是什么场景”“哪几张更适合展示”这类问题，不要只根据摘要臆测。'
        '如果问题涉及模糊、噪声、曝光等细粒度技术判断，且 batch 摘要不足以支持回答或稳定筛选，可以调用对应 low-level 工具。'
        '不要输出额外解释文字。'
    )


async def _execute_tool(
    tool_name: str,
    tool_args: Dict[str, Any],
    batch_id: str,
    *,
    model: str | None = None,
    provider_profile_id: str | None = None,
) -> Dict[str, Any]:
    if tool_name == 'list_batch_items':
        return await list_batch_items(tool_args.get('batch_id') or batch_id)
    if tool_name == 'inspect_batch_images':
        upload_ids = tool_args.get('upload_ids')
        normalized_upload_ids = upload_ids if isinstance(upload_ids, list) else None
        limit = tool_args.get('limit')
        normalized_limit = int(limit) if isinstance(limit, int) and limit > 0 else 6
        return await inspect_batch_images(
            tool_args.get('batch_id') or batch_id,
            focus=tool_args.get('focus'),
            upload_ids=normalized_upload_ids,
            limit=normalized_limit,
            model=model,
            provider_profile_id=provider_profile_id,
        )
    upload_id = str(tool_args.get('upload_id') or '').strip()
    if not upload_id:
        raise ValueError('tool_args.upload_id is required')
    if tool_name == 'inspect_image':
        return await inspect_image(
            upload_id,
            focus=tool_args.get('focus'),
            model=model,
            provider_profile_id=provider_profile_id,
        )
    if tool_name == 'compute_blur_metrics':
        return await compute_blur_metrics(upload_id)
    if tool_name == 'compute_noise_metrics':
        return await compute_noise_metrics(upload_id)
    if tool_name == 'compute_exposure_metrics':
        return await compute_exposure_metrics(upload_id)
    raise ValueError(f'Unsupported tool: {tool_name}')


async def build_filter_plan(
    *,
    batch_id: str,
    query: str,
    conversation: List[Dict[str, str]] | None = None,
    model: str | None = None,
    provider_profile_id: str | None = None,
) -> Dict[str, Any]:
    batch_payload = await list_batch_items(batch_id)
    batch_summary = _compact_batch_summary(batch_payload)
    trace: List[Dict[str, Any]] = []

    for _ in range(MAX_AGENT_STEPS):
        prompt = _build_agent_prompt(
            query=query,
            batch_summary=batch_summary,
            trace=trace,
            conversation=conversation,
        )
        try:
            raw_text = await call_text_model(
                prompt,
                model=model,
                timeout=30,
                profile_id=provider_profile_id,
            )
        except DoubaoError:
            fallback = _fallback_plan(query, domain_count=batch_payload.get('count'))
            return {
                'batch_id': batch_id,
                'query': query,
                'dsl': fallback['dsl'],
                'explanation': fallback['explanation'],
                'tool_trace': trace,
                'mode': 'fallback',
            }

        payload = _extract_json(raw_text)
        if not isinstance(payload, dict):
            break

        action = str(payload.get('action') or '').strip().lower()
        if action == 'use_tool':
            tool_name = str(payload.get('tool_name') or '').strip()
            tool_args = payload.get('tool_args') if isinstance(payload.get('tool_args'), dict) else {}
            tool_result = await _execute_tool(
                tool_name,
                tool_args,
                batch_id,
                model=model,
                provider_profile_id=provider_profile_id,
            )
            trace.append(
                {
                    'tool_name': tool_name,
                    'tool_args': tool_args,
                    'reason': payload.get('reason'),
                    'tool_result': tool_result,
                }
            )
            continue

        if action == 'final' and isinstance(payload.get('dsl'), dict):
            return {
                'batch_id': batch_id,
                'query': query,
                'dsl': _normalize_filter_dsl(query, payload['dsl'], domain_count=batch_payload.get('count')),
                'explanation': payload.get('explanation') or '已生成筛选规则。',
                'tool_trace': trace,
                'mode': 'agent',
            }

        break

    fallback = _fallback_plan(query, domain_count=batch_payload.get('count'))
    return {
        'batch_id': batch_id,
        'query': query,
        'dsl': fallback['dsl'],
        'explanation': fallback['explanation'],
        'tool_trace': trace,
        'mode': 'fallback',
    }


async def build_filter_chat_turn(
    *,
    batch_id: str,
    query: str,
    conversation: List[Dict[str, str]] | None = None,
    active_upload_ids: List[str] | None = None,
    model: str | None = None,
    provider_profile_id: str | None = None,
) -> Dict[str, Any]:
    batch_payload = await list_batch_items(batch_id)
    if active_upload_ids:
        active_set = {str(upload_id).strip() for upload_id in active_upload_ids if str(upload_id).strip()}
        if active_set:
            batch_payload = {
                **batch_payload,
                'items': [item for item in (batch_payload.get('items') or []) if str(item.get('upload_id') or '').strip() in active_set],
                'count': len([item for item in (batch_payload.get('items') or []) if str(item.get('upload_id') or '').strip() in active_set]),
            }
    batch_summary = _compact_batch_summary(batch_payload)
    trace: List[Dict[str, Any]] = []
    visual_question = _looks_like_visual_question(query)

    if visual_question:
        try:
            trace.extend(
                await _seed_visual_trace(
                    batch_id=batch_id,
                    query=query,
                    active_upload_ids=active_upload_ids,
                    model=model,
                    provider_profile_id=provider_profile_id,
                )
            )
        except Exception:
            trace = []

    for _ in range(MAX_AGENT_STEPS):
        prompt = _build_chat_prompt(
            query=query,
            batch_summary=batch_summary,
            trace=trace,
            conversation=conversation,
        )
        try:
            raw_text = await call_text_model(
                prompt,
                model=model,
                timeout=30,
                profile_id=provider_profile_id,
            )
        except DoubaoError:
            break

        payload = _extract_json(raw_text)
        if not isinstance(payload, dict):
            break

        action = str(payload.get('action') or '').strip().lower()
        if action == 'use_tool':
            tool_name = str(payload.get('tool_name') or '').strip()
            tool_args = payload.get('tool_args') if isinstance(payload.get('tool_args'), dict) else {}
            tool_result = await _execute_tool(
                tool_name,
                tool_args,
                batch_id,
                model=model,
                provider_profile_id=provider_profile_id,
            )
            trace.append(
                {
                    'tool_name': tool_name,
                    'tool_args': tool_args,
                    'reason': payload.get('reason'),
                    'tool_result': tool_result,
                }
            )
            continue

        if action == 'reply':
            message = _polish_assistant_message(str(payload.get('message') or '').strip())
            if message:
                return {
                    'batch_id': batch_id,
                    'query': query,
                    'should_execute': False,
                    'assistant_message': message,
                    'tool_trace': trace,
                    'mode': 'agent_reply',
                }

        if action == 'filter' and isinstance(payload.get('dsl'), dict):
            message = _polish_assistant_message(str(payload.get('message') or '').strip() or '已根据你的要求执行筛选。')
            return {
                'batch_id': batch_id,
                'query': query,
                'should_execute': True,
                'assistant_message': message,
                'dsl': _normalize_filter_dsl(query, payload.get('dsl') or {}, domain_count=batch_payload.get('count')),
                'tool_trace': trace,
                'mode': 'agent_filter',
            }
        break

    if _looks_like_filter_request(query):
        fallback = _fallback_plan(query, domain_count=batch_payload.get('count'))
        return {
            'batch_id': batch_id,
            'query': query,
            'should_execute': True,
            'assistant_message': fallback['explanation'],
            'dsl': fallback['dsl'],
            'tool_trace': trace,
            'mode': 'fallback_filter',
        }

    if visual_question:
        visual_reply = await _answer_with_visual_review(
            batch_id=batch_id,
            query=query,
            active_upload_ids=active_upload_ids,
            model=model,
            provider_profile_id=provider_profile_id,
        )
        if visual_reply:
            return {
                'batch_id': batch_id,
                'query': query,
                'should_execute': False,
                'assistant_message': visual_reply['assistant_message'],
                'tool_trace': visual_reply['tool_trace'],
                'mode': visual_reply['mode'],
            }

    count = batch_payload.get('count') or len(batch_payload.get('items') or [])
    return {
        'batch_id': batch_id,
        'query': query,
        'should_execute': False,
        'assistant_message': f'我已经读取当前批次，共 {count} 张图片。你可以继续问我场景、质量特征，或者明确说“保留/去掉/筛选”某类图片，我再执行筛选。',
        'tool_trace': trace,
        'mode': 'fallback_reply',
    }
