from __future__ import annotations

from typing import Any, Dict

from backend.models.doubao_api import DoubaoError, call_structured_vision
from backend.services.provider_profiles import (
    get_active_provider_profile,
    get_model_display_name,
    get_provider_profile,
)

from .skill_base import AnalysisSkill, SkillContext, SkillOutcome
from .skill_quality_helpers import clamp_score, score_to_level


def _build_quality_judge_prompt(evidence: Dict[str, Any]) -> str:
    factor_scores = evidence.get('factor_scores') or {}
    return (
        '你是一名严格的图像质量评审员。请结合原图和给定证据，只输出 JSON。\n'
        '请从以下维度分别给出 0-100 分：sharpness_score, noise_score, exposure_score, contrast_score, compression_score, overall_quality_score。\n'
        '同时返回 confidence(0-100), level(string), evidence_alignment(string), reason(string), key_issues([string])。\n'
        '要求：\n'
        '1. 只评估图像质量，不评价图像内容的美学或语义价值。\n'
        '2. reason 使用中文且不超过两句。\n'
        '3. level 只能是 优秀/良好/一般/较差。\n'
        '4. evidence_alignment 只能是 aligned/slightly_divergent/divergent。\n'
        '5. key_issues 最多 4 个短语。\n'
        f"已知证据：MANIQA={evidence.get('base_maniqa_score')}, "
        f"technical_score={evidence.get('technical_score')}, "
        f"blur={factor_scores.get('blur')}, noise={factor_scores.get('noise')}, "
        f"exposure={factor_scores.get('exposure')}, contrast={factor_scores.get('contrast')}, "
        f"compression={factor_scores.get('compression')}。"
    )


def _normalize_alignment(value: Any) -> str:
    if isinstance(value, str):
        normalized = value.strip().lower()
        if normalized in {'aligned', 'slightly_divergent', 'divergent'}:
            return normalized
    return 'aligned'


def _sanitize_issue_list(value: Any) -> list[str]:
    if not isinstance(value, list):
        return []
    issues: list[str] = []
    for item in value:
        if not isinstance(item, str):
            continue
        text = item.strip()
        if not text or text in issues:
            continue
        issues.append(text)
    return issues[:4]


class QualityJudgeSkill(AnalysisSkill):
    skill_id = 'quality_judge'
    aliases = ('quality_judge_skill', 'judge')
    description = 'Use an LLM rubric to judge image quality factors and overall quality.'
    dependencies = ('quality_evidence',)
    expose_in_ui = False

    async def run(self, context: SkillContext) -> SkillOutcome:
        evidence = await context.get_shared('quality_evidence', {}) or {}
        base64_image = await context.read_base64()
        prompt = _build_quality_judge_prompt(evidence)
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
                prompt=prompt,
                detail=context.runtime.detail,
                model=context.runtime.model,
                profile_id=context.runtime.provider_profile_id,
            )
            payload = response.payload
        except DoubaoError as exc:
            warnings.append(f'LLM 质量评审失败: {exc}')
            payload = {}

        judge = {
            'sharpness_score': clamp_score(payload.get('sharpness_score'), default=evidence.get('factor_scores', {}).get('blur', 0.0)),
            'noise_score': clamp_score(payload.get('noise_score'), default=evidence.get('factor_scores', {}).get('noise', 0.0)),
            'exposure_score': clamp_score(payload.get('exposure_score'), default=evidence.get('factor_scores', {}).get('exposure', 0.0)),
            'contrast_score': clamp_score(payload.get('contrast_score'), default=evidence.get('factor_scores', {}).get('contrast', 0.0)),
            'compression_score': clamp_score(payload.get('compression_score'), default=evidence.get('factor_scores', {}).get('compression', 0.0)),
            'overall_quality_score': clamp_score(payload.get('overall_quality_score'), default=evidence.get('technical_score', 0.0)),
            'confidence': clamp_score(payload.get('confidence'), default=72.0),
            'level': payload.get('level') if payload.get('level') in {'优秀', '良好', '一般', '较差'} else score_to_level(clamp_score(payload.get('overall_quality_score'), default=evidence.get('technical_score', 0.0))),
            'evidence_alignment': _normalize_alignment(payload.get('evidence_alignment')),
            'reason': payload.get('reason') if isinstance(payload.get('reason'), str) and payload.get('reason').strip() else 'LLM 已结合图像与证据完成质量审阅。',
            'key_issues': _sanitize_issue_list(payload.get('key_issues')),
        }

        return SkillOutcome(
            skill_id=self.skill_id,
            data={'quality_judge': judge},
            models={'quality_judge': selected_model},
            warnings=warnings,
        )
