from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict, Iterable, List


SUPPORTED_FIELDS = {
    'quality_fusion.final_score',
    'quality_judge.sharpness_score',
    'quality_judge.noise_score',
    'quality_judge.exposure_score',
    'quality_judge.contrast_score',
    'quality_judge.compression_score',
    'quality_judge.overall_quality_score',
    'semantic.scene',
    'semantic.complexity',
    'semantic.scene_clutter',
    'semantic.object_count',
    'semantic.semantic_tags',
    'content.caption',
    'content.objects',
    'content.search_text',
    'filename',
}

SUPPORTED_OPERATORS = {'>=', '<=', '>', '<', '==', '!=', 'contains', 'in'}
OPERATOR_ALIASES = {
    'eq': '==',
    'equals': '==',
    '=': '==',
    'ne': '!=',
    'neq': '!=',
    'not_equals': '!=',
    'gte': '>=',
    'lte': '<=',
    'gt': '>',
    'lt': '<',
}


@dataclass(slots=True)
class RuleEvaluation:
    rule: Dict[str, Any]
    matched: bool
    actual_value: Any


def _get_field_value(payload: Dict[str, Any], field: str) -> Any:
    if field == 'content.objects':
        objects = ((payload.get('content') or {}).get('objects') or [])
        labels = []
        for item in objects:
            if isinstance(item, dict):
                label = item.get('label') or item.get('name')
            else:
                label = item
            if label:
                labels.append(str(label))
        return labels

    if field == 'content.search_text':
        content = payload.get('content') or {}
        semantic = payload.get('semantic') or {}
        values: List[str] = [
            str(payload.get('filename') or ''),
            str(content.get('caption') or ''),
            str(semantic.get('scene') or ''),
            str(semantic.get('complexity') or ''),
        ]
        tags = semantic.get('semantic_tags') or []
        if isinstance(tags, list):
            values.extend(str(tag) for tag in tags if tag)
        objects = _get_field_value(payload, 'content.objects')
        if isinstance(objects, list):
            values.extend(objects)
        return ' '.join(value for value in values if value).strip()

    current: Any = payload
    for part in field.split('.'):
        if not isinstance(current, dict):
            return None
        current = current.get(part)
    return current


def _to_float(value: Any) -> float | None:
    try:
        return float(value)
    except Exception:
        return None


def _as_list(value: Any) -> List[Any]:
    if value is None:
        return []
    if isinstance(value, list):
        return value
    if isinstance(value, tuple) or isinstance(value, set):
        return list(value)
    return [value]


def _contains_value(actual: Any, expected: Any) -> bool:
    expected_items = [str(item).lower() for item in _as_list(expected) if str(item).strip()]
    if not expected_items:
        return False

    if isinstance(actual, str):
        haystack = actual.lower()
        return any(item in haystack for item in expected_items)

    if isinstance(actual, Iterable):
        actual_items = [str(item).lower() for item in actual if str(item).strip()]
        return any(
            expected_item in actual_item or actual_item in expected_item
            for expected_item in expected_items
            for actual_item in actual_items
        )

    return any(item in str(actual).lower() for item in expected_items)


def _normalize_dsl(dsl: Dict[str, Any]) -> Dict[str, Any]:
    mode = str(dsl.get('mode') or 'keep_matching').strip().lower()
    if mode not in {'keep_matching', 'remove_matching'}:
        mode = 'keep_matching'

    logic = str(dsl.get('logic') or 'and').strip().lower()
    if logic not in {'and', 'or'}:
        logic = 'and'

    rules = []
    for rule in dsl.get('rules') or []:
        if not isinstance(rule, dict):
            continue
        field = str(rule.get('field') or '').strip()
        op = OPERATOR_ALIASES.get(str(rule.get('op') or '').strip().lower(), str(rule.get('op') or '').strip())
        if field not in SUPPORTED_FIELDS or op not in SUPPORTED_OPERATORS:
            continue
        rules.append(
            {
                'field': field,
                'op': op,
                'value': rule.get('value'),
            }
        )

    sort = dsl.get('sort') if isinstance(dsl.get('sort'), dict) else None
    normalized_sort = None
    if sort:
        field = str(sort.get('field') or '').strip()
        direction = str(sort.get('direction') or 'desc').strip().lower()
        if field in SUPPORTED_FIELDS:
            normalized_sort = {
                'field': field,
                'direction': 'asc' if direction == 'asc' else 'desc',
            }

    limit = dsl.get('limit')
    if not isinstance(limit, int) or limit <= 0:
        limit = None

    return {
        'mode': mode,
        'logic': logic,
        'rules': rules,
        'sort': normalized_sort,
        'limit': limit,
    }


def _evaluate_rule(item: Dict[str, Any], rule: Dict[str, Any]) -> RuleEvaluation:
    field = rule['field']
    op = rule['op']
    expected = rule.get('value')
    actual = _get_field_value(item, field)
    matched = False

    if op in {'>=', '<=', '>', '<'}:
        left = _to_float(actual)
        right = _to_float(expected)
        if left is not None and right is not None:
            if op == '>=':
                matched = left >= right
            elif op == '<=':
                matched = left <= right
            elif op == '>':
                matched = left > right
            else:
                matched = left < right
    elif op == '==':
        matched = actual == expected
    elif op == '!=':
        matched = actual != expected
    elif op == 'contains':
        matched = _contains_value(actual, expected)
    elif op == 'in':
        expected_values = expected if isinstance(expected, list) else [expected]
        if isinstance(actual, Iterable) and not isinstance(actual, str):
            matched = any(_contains_value(expected_values, item) for item in actual)
        else:
            matched = actual in expected_values

    return RuleEvaluation(rule=rule, matched=matched, actual_value=actual)


def _item_passes(evaluations: List[RuleEvaluation], logic: str) -> bool:
    if not evaluations:
        return True
    matches = [evaluation.matched for evaluation in evaluations]
    return all(matches) if logic == 'and' else any(matches)


def _sort_items(items: List[Dict[str, Any]], sort: Dict[str, Any] | None) -> List[Dict[str, Any]]:
    if not sort:
        return items
    field = sort['field']
    reverse = sort.get('direction') != 'asc'
    return sorted(items, key=lambda item: (_get_field_value(item, field) is None, _get_field_value(item, field)), reverse=reverse)


def _format_actual_value(value: Any) -> str:
    if isinstance(value, list):
        compact = [str(item) for item in value if item is not None]
        return '、'.join(compact[:5]) if compact else '--'
    if value is None or value == '':
        return '--'
    return str(value)


def _rule_to_reason(rule: Dict[str, Any], actual_value: Any) -> str:
    field_labels = {
        'quality_fusion.final_score': '综合质量分',
        'quality_judge.sharpness_score': '清晰度评分',
        'quality_judge.noise_score': '噪声评分',
        'quality_judge.exposure_score': '曝光评分',
        'quality_judge.contrast_score': '对比度评分',
        'quality_judge.compression_score': '压缩影响评分',
        'quality_judge.overall_quality_score': 'LLM 总评',
        'semantic.scene': '场景',
        'semantic.complexity': '复杂度',
        'semantic.scene_clutter': '杂乱度',
        'semantic.object_count': '目标数',
        'semantic.semantic_tags': '语义标签',
        'content.caption': '描述',
        'content.objects': '识别对象',
        'content.search_text': '图像内容',
        'filename': '文件名',
    }
    return f"{field_labels.get(rule['field'], rule['field'])} {rule['op']} {rule.get('value')}（实际值：{_format_actual_value(actual_value)}）"


def _decision_basis(entry: Dict[str, Any], normalized: Dict[str, Any]) -> List[str]:
    if entry['matched_rules']:
        return [f"命中 {reason}" for reason in entry['matched_rules'][:3]]
    if entry['unmet_rules']:
        return [f"未满足 {reason}" for reason in entry['unmet_rules'][:3]]
    sort = normalized.get('sort')
    if sort:
        return [f"按 {sort['field']} {sort['direction']} 排序后保留"]
    return ['未设置细分规则，默认纳入当前结果']


def execute_filter_dsl(batch_items: List[Dict[str, Any]], dsl: Dict[str, Any]) -> Dict[str, Any]:
    normalized = _normalize_dsl(dsl)
    evaluated: List[Dict[str, Any]] = []
    for item in batch_items:
        evaluations = [_evaluate_rule(item, rule) for rule in normalized['rules']]
        passes = _item_passes(evaluations, normalized['logic'])
        keep = passes if normalized['mode'] == 'keep_matching' else not passes
        matched_reasons = [_rule_to_reason(e.rule, e.actual_value) for e in evaluations if e.matched]
        unmet_reasons = [_rule_to_reason(e.rule, e.actual_value) for e in evaluations if not e.matched]
        evaluated.append(
            {
                'result': item,
                'keep': keep,
                'matched_rules': matched_reasons,
                'unmet_rules': unmet_reasons,
                'reason': ('；'.join(matched_reasons[:3]) if keep and matched_reasons else '符合筛选条件') if keep else ('；'.join(unmet_reasons[:3]) or '未命中筛选条件'),
            }
        )

    kept = [entry for entry in evaluated if entry['keep']]
    removed = [entry for entry in evaluated if not entry['keep']]

    if normalized['sort']:
        kept = _sort_items(kept, {'field': f"result.{normalized['sort']['field']}", 'direction': normalized['sort']['direction']})
        removed = _sort_items(removed, {'field': f"result.{normalized['sort']['field']}", 'direction': normalized['sort']['direction']})

    limit = normalized.get('limit')
    if limit:
        overflow = kept[limit:]
        kept = kept[:limit]
        for entry in overflow:
            entry['keep'] = False
            entry['reason'] = '超过保留数量上限'
            entry['unmet_rules'] = ['超过保留数量上限']
        removed = overflow + removed

    def _format(entries: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        return [
            {
                'upload_id': entry['result'].get('upload_id'),
                'filename': entry['result'].get('filename'),
                'score': ((entry['result'].get('quality_fusion') or {}).get('final_score')
                          or (entry['result'].get('quality') or {}).get('score')),
                'thumbnail': ((entry['result'].get('snapshot') or {}).get('thumbnail')),
                'image': ((entry['result'].get('snapshot') or {}).get('image')),
                'reason': entry['reason'],
                'matched_rules': entry['matched_rules'],
                'unmet_rules': entry['unmet_rules'],
                'decision_basis': _decision_basis(entry, normalized),
                'result': entry['result'],
            }
            for entry in entries
        ]

    return {
        'dsl': normalized,
        'summary': {
            'total': len(batch_items),
            'kept': len(kept),
            'removed': len(removed),
        },
        'kept': _format(kept),
        'removed': _format(removed),
    }
