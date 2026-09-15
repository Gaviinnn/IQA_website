from __future__ import annotations

from backend.iqa.models.maniqa_service import evaluate_image

from .skill_base import AnalysisSkill, SkillContext, SkillOutcome


class QualityAssessmentSkill(AnalysisSkill):
    skill_id = 'quality'
    aliases = ('quality_assessment', 'quality_assessment_skill')
    description = 'Run MANIQA-based no-reference image quality assessment.'

    async def run(self, context: SkillContext) -> SkillOutcome:
        quality = await evaluate_image(
            context.upload.path,
            provider_profile_id=context.runtime.provider_profile_id,
        )
        return SkillOutcome(
            skill_id=self.skill_id,
            data={
                'quality': {
                    'score': quality.score,
                    'level': quality.level,
                    'explanation': quality.explanation,
                }
            },
            models={'quality': 'MANIQA v1.2'},
        )
