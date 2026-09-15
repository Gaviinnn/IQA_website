from __future__ import annotations

from .skill_base import AnalysisSkill, SkillContext, SkillOutcome
from .skill_quality_helpers import (
    TECHNICAL_WEIGHTS,
    build_evidence_summary,
    compute_technical_score,
)


class QualityEvidenceSkill(AnalysisSkill):
    skill_id = 'quality_evidence'
    aliases = ('quality_evidence_skill', 'evidence')
    description = 'Build structured technical evidence from MANIQA and diagnostics.'
    dependencies = ('quality', 'diagnostics')
    expose_in_ui = False

    async def run(self, context: SkillContext) -> SkillOutcome:
        quality = await context.get_shared('quality', {}) or {}
        diagnostics = await context.get_shared('diagnostics', {}) or {}
        maniqa_score = quality.get('score')
        technical_score, factor_scores = compute_technical_score(diagnostics)

        evidence = {
            'base_maniqa_score': maniqa_score,
            'technical_score': technical_score,
            'technical_weights': TECHNICAL_WEIGHTS,
            'factor_scores': factor_scores,
            'summary': build_evidence_summary(
                maniqa_score=maniqa_score,
                technical_score=technical_score,
                diagnostics=diagnostics,
            ),
        }
        return SkillOutcome(
            skill_id=self.skill_id,
            data={'quality_evidence': evidence},
            models={'quality_evidence': 'Quality Evidence Builder v1'},
        )
