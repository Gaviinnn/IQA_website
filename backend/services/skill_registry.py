from __future__ import annotations

from typing import Iterable, List

from .skill_base import AnalysisSkill
from .skill_diagnostics import QualityDiagnosticsSkill
from .skill_quality_evidence import QualityEvidenceSkill
from .skill_quality_fusion import QualityFusionSkill
from .skill_quality_judge import QualityJudgeSkill
from .skill_quality import QualityAssessmentSkill
from .skill_semantic import SemanticAnalysisSkill

DEFAULT_SKILL_ORDER = ('quality', 'diagnostics', 'quality_fusion', 'semantic')

_SKILLS: list[AnalysisSkill] = [
    QualityAssessmentSkill(),
    QualityDiagnosticsSkill(),
    QualityEvidenceSkill(),
    QualityJudgeSkill(),
    QualityFusionSkill(),
    SemanticAnalysisSkill(),
]

_REGISTRY: dict[str, AnalysisSkill] = {}
for skill in _SKILLS:
    names = (skill.skill_id, *skill.aliases)
    for name in names:
        _REGISTRY[name] = skill


def resolve_skills(requested: Iterable[str] | None) -> List[AnalysisSkill]:
    names = list(requested or DEFAULT_SKILL_ORDER)
    resolved_ids: list[str] = []
    seen: set[str] = set()
    order_map = {skill_id: index for index, skill_id in enumerate(DEFAULT_SKILL_ORDER)}

    def visit(raw_name: str) -> None:
        name = (raw_name or '').strip().lower()
        if not name:
            return
        skill = _REGISTRY.get(name)
        if skill is None:
            raise ValueError(f'Unsupported skill: {raw_name}')
        if skill.skill_id in seen:
            return
        for dependency in skill.dependencies:
            visit(dependency)
        seen.add(skill.skill_id)
        resolved_ids.append(skill.skill_id)

    for raw_name in names:
        visit(raw_name)

    if not resolved_ids:
        return resolve_skills(DEFAULT_SKILL_ORDER)
    resolved = [_REGISTRY[skill_id] for skill_id in resolved_ids]
    return sorted(
        resolved,
        key=lambda item: (order_map.get(item.skill_id, len(order_map)), resolved_ids.index(item.skill_id)),
    )


def list_registered_skills() -> list[dict[str, str]]:
    return [
        {'id': skill.skill_id, 'description': skill.description}
        for skill in _SKILLS
        if skill.expose_in_ui
    ]
