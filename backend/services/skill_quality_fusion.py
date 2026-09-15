from __future__ import annotations

from .skill_base import AnalysisSkill, SkillContext, SkillOutcome
from .skill_quality_helpers import (
    FUSION_WEIGHTS,
    clamp_score,
    score_to_level,
    summarize_quality_adjustments,
)


def _confidence_from_alignment(alignment: str, confidence: float) -> str:
    if alignment == 'divergent' or confidence < 55:
        return 'low'
    if alignment == 'slightly_divergent' or confidence < 75:
        return 'medium'
    return 'high'


class QualityFusionSkill(AnalysisSkill):
    skill_id = 'quality_fusion'
    aliases = ('quality_fusion_skill', 'fusion')
    description = 'Fuse MANIQA, technical evidence, and LLM judging into a final quality score.'
    dependencies = ('quality', 'diagnostics', 'quality_evidence', 'quality_judge')

    async def run(self, context: SkillContext) -> SkillOutcome:
        quality = await context.get_shared('quality', {}) or {}
        diagnostics = await context.get_shared('diagnostics', {}) or {}
        evidence = await context.get_shared('quality_evidence', {}) or {}
        judge = await context.get_shared('quality_judge', {}) or {}

        maniqa_score = clamp_score(quality.get('score'), default=0.0)
        technical_score = clamp_score(evidence.get('technical_score'), default=maniqa_score)
        judge_score = clamp_score(judge.get('overall_quality_score'), default=technical_score)

        final_score = round(
            maniqa_score * FUSION_WEIGHTS['maniqa']
            + technical_score * FUSION_WEIGHTS['technical']
            + judge_score * FUSION_WEIGHTS['judge'],
            2,
        )
        level = score_to_level(final_score)
        alignment = judge.get('evidence_alignment', 'aligned')
        llm_confidence = clamp_score(judge.get('confidence'), default=72.0)

        fusion = {
            'base_score': maniqa_score,
            'technical_score': technical_score,
            'judge_score': judge_score,
            'final_score': final_score,
            'level': level,
            'confidence': _confidence_from_alignment(alignment, llm_confidence),
            'weights': FUSION_WEIGHTS,
            'judge_alignment': alignment,
            'judge_confidence': llm_confidence,
            'factor_scores': evidence.get('factor_scores') or {},
            'adjustments': summarize_quality_adjustments(
                maniqa_score=maniqa_score,
                technical_factors=evidence.get('factor_scores') or {},
                judge_overall=judge_score,
            ),
            'reason': judge.get('reason') or f'融合 MANIQA、技术证据与 LLM 质量审阅后，图像质量等级为 {level}。',
            'key_issues': judge.get('key_issues') or [],
            'diagnostics_summary': diagnostics.get('summary'),
        }

        return SkillOutcome(
            skill_id=self.skill_id,
            data={'quality_fusion': fusion},
            models={'quality_fusion': 'Quality Fusion Engine v1'},
        )
