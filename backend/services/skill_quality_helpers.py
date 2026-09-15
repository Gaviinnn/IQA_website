from __future__ import annotations

from typing import Any, Dict, List


TECHNICAL_WEIGHTS = {
    'blur': 0.32,
    'noise': 0.22,
    'exposure': 0.19,
    'contrast': 0.17,
    'compression': 0.10,
}

FUSION_WEIGHTS = {
    'maniqa': 0.45,
    'technical': 0.25,
    'judge': 0.30,
}

LEVEL_SCORE_MAP = {
    'blur': {'low': 88.0, 'medium': 48.0, 'high': 18.0},
    'noise': {'low': 84.0, 'medium': 54.0, 'high': 16.0},
    'compression_artifacts': {'low': 86.0, 'medium': 52.0, 'high': 20.0},
}

EXPOSURE_SCORE_MAP = {
    'normal': 82.0,
    'underexposed': 48.0,
    'overexposed': 48.0,
}

CONTRAST_SCORE_MAP = {
    'normal': 80.0,
    'low': 50.0,
    'high': 66.0,
}

LEVEL_TEXT_MAP = {
    'low': '低',
    'medium': '中',
    'high': '高',
    'normal': '正常',
    'underexposed': '欠曝',
    'overexposed': '过曝',
}


def clamp_score(value: Any, *, default: float = 0.0) -> float:
    try:
        numeric = float(value)
    except Exception:
        numeric = default
    return round(max(0.0, min(100.0, numeric)), 2)


def score_to_level(score: float) -> str:
    if score >= 80:
        return '优秀'
    if score >= 60:
        return '良好'
    if score >= 40:
        return '一般'
    return '较差'


def _linear_score_lower_better(
    value: Any,
    *,
    good: float,
    bad: float,
    floor: float = 15.0,
    ceiling: float = 90.0,
    default: float,
) -> float:
    try:
        numeric = float(value)
    except Exception:
        return default
    if numeric <= good:
        return ceiling
    if numeric >= bad:
        return floor
    ratio = (numeric - good) / max(1e-6, bad - good)
    return round(ceiling - ratio * (ceiling - floor), 2)


def _linear_score_higher_better(
    value: Any,
    *,
    bad: float,
    good: float,
    floor: float = 15.0,
    ceiling: float = 90.0,
    default: float,
) -> float:
    try:
        numeric = float(value)
    except Exception:
        return default
    if numeric >= good:
        return ceiling
    if numeric <= bad:
        return floor
    ratio = (numeric - bad) / max(1e-6, good - bad)
    return round(floor + ratio * (ceiling - floor), 2)


def _contrast_score_from_metric(metric: Any, default: float) -> float:
    try:
        numeric = float(metric)
    except Exception:
        return default
    if 0.17 <= numeric <= 0.27:
        return 84.0
    if numeric < 0.11:
        return 20.0
    if numeric < 0.17:
        return round(20.0 + (numeric - 0.11) / 0.06 * 50.0, 2)
    if numeric <= 0.36:
        return round(84.0 - (numeric - 0.27) / 0.09 * 18.0, 2)
    return 48.0


def _level_text(value: Any) -> str:
    if isinstance(value, str):
        return LEVEL_TEXT_MAP.get(value, value)
    return str(value)


def compute_technical_factors(diagnostics: Dict[str, Any] | None) -> Dict[str, float]:
    diagnostics = diagnostics or {}
    metrics = diagnostics.get('metrics') or {}

    blur_default = LEVEL_SCORE_MAP['blur'].get(diagnostics.get('blur'), 48.0)
    noise_default = LEVEL_SCORE_MAP['noise'].get(diagnostics.get('noise'), 54.0)
    exposure_default = EXPOSURE_SCORE_MAP.get(diagnostics.get('exposure'), 60.0)
    contrast_default = CONTRAST_SCORE_MAP.get(diagnostics.get('contrast'), 58.0)
    compression_default = LEVEL_SCORE_MAP['compression_artifacts'].get(
        diagnostics.get('compression_artifacts'),
        52.0,
    )

    blur = min(
        blur_default,
        _linear_score_higher_better(
            metrics.get('blur_score'),
            bad=0.06,
            good=0.14,
            floor=12.0,
            ceiling=88.0,
            default=blur_default,
        ),
    )
    noise = min(
        noise_default,
        _linear_score_lower_better(
            metrics.get('noise_score'),
            good=0.009,
            bad=0.032,
            floor=12.0,
            ceiling=86.0,
            default=noise_default,
        ),
    )
    exposure = min(
        exposure_default,
        _linear_score_lower_better(
            metrics.get('exposure_severity'),
            good=0.05,
            bad=0.30,
            floor=18.0,
            ceiling=84.0,
            default=exposure_default,
        ),
    )
    contrast = min(
        contrast_default,
        _contrast_score_from_metric(metrics.get('contrast_std'), contrast_default),
    )
    compression = min(
        compression_default,
        _linear_score_lower_better(
            metrics.get('compression_score'),
            good=0.03,
            bad=0.24,
            floor=10.0,
            ceiling=84.0,
            default=compression_default,
        ),
    )
    return {
        'blur': round(blur, 2),
        'noise': round(noise, 2),
        'exposure': round(exposure, 2),
        'contrast': round(contrast, 2),
        'compression': round(compression, 2),
    }


def compute_technical_score(diagnostics: Dict[str, Any] | None) -> tuple[float, Dict[str, float]]:
    factor_scores = compute_technical_factors(diagnostics)
    diagnostics = diagnostics or {}
    technical_score = sum(
        factor_scores[key] * TECHNICAL_WEIGHTS[key]
        for key in TECHNICAL_WEIGHTS
    )
    penalties = 0.0
    caps: list[float] = []

    blur_level = diagnostics.get('blur')
    noise_level = diagnostics.get('noise')
    exposure_level = diagnostics.get('exposure')
    compression_level = diagnostics.get('compression_artifacts')

    if blur_level == 'medium':
        penalties += 8.0
        caps.append(60.0)
    elif blur_level == 'high':
        penalties += 18.0
        caps.append(42.0)

    if noise_level == 'medium':
        penalties += 6.0
    elif noise_level == 'high':
        penalties += 15.0
        caps.append(46.0)

    if compression_level == 'medium':
        penalties += 5.0
    elif compression_level == 'high':
        penalties += 12.0
        caps.append(52.0)

    if exposure_level in {'underexposed', 'overexposed'}:
        penalties += 7.0

    if blur_level in {'medium', 'high'} and noise_level in {'medium', 'high'}:
        penalties += 7.0
        caps.append(50.0)

    if blur_level in {'medium', 'high'} and compression_level == 'high':
        penalties += 6.0
        caps.append(48.0 if blur_level == 'high' else 55.0)

    technical_score = max(0.0, technical_score - penalties)
    if caps:
        technical_score = min(technical_score, min(caps))
    return round(technical_score, 2), factor_scores


def summarize_quality_adjustments(
    *,
    maniqa_score: float | None,
    technical_factors: Dict[str, float],
    judge_overall: float | None = None,
) -> List[Dict[str, Any]]:
    adjustments: List[Dict[str, Any]] = []
    for factor_key, factor_score in technical_factors.items():
        delta = round(factor_score - 100.0, 2)
        if delta >= -6:
            continue
        adjustments.append(
            {
                'factor': factor_key,
                'score': factor_score,
                'delta_from_perfect': delta,
            }
        )

    if maniqa_score is not None and judge_overall is not None:
        adjustments.append(
            {
                'factor': 'judge_alignment',
                'score': round(judge_overall, 2),
                'delta_from_maniqa': round(judge_overall - maniqa_score, 2),
            }
        )
    return adjustments


def build_evidence_summary(
    *,
    maniqa_score: float | None,
    technical_score: float,
    diagnostics: Dict[str, Any] | None,
) -> str:
    diagnostics = diagnostics or {}
    issues: List[str] = []
    if diagnostics.get('blur') in {'medium', 'high'}:
        issues.append(f"模糊{_level_text(diagnostics.get('blur'))}")
    if diagnostics.get('noise') in {'medium', 'high'}:
        issues.append(f"噪声{_level_text(diagnostics.get('noise'))}")
    if diagnostics.get('exposure') in {'underexposed', 'overexposed'}:
        issues.append(_level_text(diagnostics.get('exposure')))
    if diagnostics.get('contrast') in {'low', 'high'}:
        issues.append(f"对比度{_level_text(diagnostics.get('contrast'))}")
    if diagnostics.get('compression_artifacts') in {'medium', 'high'}:
        issues.append(f"压缩痕迹{_level_text(diagnostics.get('compression_artifacts'))}")

    if not issues:
        issue_text = '未发现明显技术质量缺陷'
    else:
        issue_text = '，'.join(issues)

    if maniqa_score is None:
        return f'技术质量子分为 {technical_score:.2f}，{issue_text}。'
    return f'MANIQA 基础分 {maniqa_score:.2f}，技术质量子分 {technical_score:.2f}，主要关注：{issue_text}。'
