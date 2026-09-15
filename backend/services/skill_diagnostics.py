from __future__ import annotations

import asyncio
from typing import Any

import numpy as np

from .skill_base import AnalysisSkill, SkillContext, SkillOutcome


def _round_metric(value: float) -> float:
    return round(float(value), 4)


def _iter_patch_starts(length: int, size: int, stride: int) -> list[int]:
    if length <= size:
        return [0]
    starts = list(range(0, length - size + 1, stride))
    last = length - size
    if starts[-1] != last:
        starts.append(last)
    return starts


def _convolve3(gray: np.ndarray, kernel: np.ndarray) -> np.ndarray:
    padded = np.pad(gray, ((1, 1), (1, 1)), mode='reflect')
    return (
        kernel[0, 0] * padded[:-2, :-2]
        + kernel[0, 1] * padded[:-2, 1:-1]
        + kernel[0, 2] * padded[:-2, 2:]
        + kernel[1, 0] * padded[1:-1, :-2]
        + kernel[1, 1] * padded[1:-1, 1:-1]
        + kernel[1, 2] * padded[1:-1, 2:]
        + kernel[2, 0] * padded[2:, :-2]
        + kernel[2, 1] * padded[2:, 1:-1]
        + kernel[2, 2] * padded[2:, 2:]
    )


def _mean_filter3(gray: np.ndarray) -> np.ndarray:
    kernel = np.full((3, 3), 1.0 / 9.0, dtype=np.float32)
    return _convolve3(gray, kernel)


def _sobel_gradients(gray: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    kernel_x = np.array(
        [[-1.0, 0.0, 1.0], [-2.0, 0.0, 2.0], [-1.0, 0.0, 1.0]],
        dtype=np.float32,
    )
    kernel_y = np.array(
        [[1.0, 2.0, 1.0], [0.0, 0.0, 0.0], [-1.0, -2.0, -1.0]],
        dtype=np.float32,
    )
    return _convolve3(gray, kernel_x), _convolve3(gray, kernel_y)


def _patch_means(feature: np.ndarray, patch_size: int = 16, stride: int = 8) -> np.ndarray:
    h, w = feature.shape
    rows = _iter_patch_starts(h, patch_size, stride)
    cols = _iter_patch_starts(w, patch_size, stride)
    values: list[float] = []
    for row in rows:
        for col in cols:
            patch = feature[row : row + patch_size, col : col + patch_size]
            values.append(float(np.mean(patch)))
    return np.asarray(values, dtype=np.float32)


def _patch_stds(feature: np.ndarray, patch_size: int = 32, stride: int = 16) -> np.ndarray:
    h, w = feature.shape
    rows = _iter_patch_starts(h, patch_size, stride)
    cols = _iter_patch_starts(w, patch_size, stride)
    values: list[float] = []
    for row in rows:
        for col in cols:
            patch = feature[row : row + patch_size, col : col + patch_size]
            values.append(float(np.std(patch)))
    return np.asarray(values, dtype=np.float32)


def _estimate_blur(gray: np.ndarray) -> tuple[str, dict[str, float]]:
    grad_x, grad_y = _sobel_gradients(gray)
    grad_mag = np.sqrt(grad_x * grad_x + grad_y * grad_y)

    patch_size = 24
    stride = 12
    rows = _iter_patch_starts(gray.shape[0], patch_size, stride)
    cols = _iter_patch_starts(gray.shape[1], patch_size, stride)
    patch_sharpness: list[float] = []
    patch_edge_density: list[float] = []
    edge_threshold = max(0.08, float(np.percentile(grad_mag, 72)))

    for row in rows:
        for col in cols:
            patch = grad_mag[row : row + patch_size, col : col + patch_size]
            patch_sharpness.append(float(np.mean(patch)))
            patch_edge_density.append(float(np.mean(patch >= edge_threshold)))

    sharpness_values = np.asarray(patch_sharpness, dtype=np.float32)
    edge_density_values = np.asarray(patch_edge_density, dtype=np.float32)

    informative_mask = edge_density_values >= max(0.06, float(np.percentile(edge_density_values, 58)))
    if np.count_nonzero(informative_mask) < max(6, int(0.1 * sharpness_values.size)):
        informative_mask = sharpness_values >= float(np.percentile(sharpness_values, 60))

    informative_sharpness = sharpness_values[informative_mask]
    if informative_sharpness.size == 0:
        informative_sharpness = sharpness_values

    median_sharpness = float(np.median(informative_sharpness))
    low_percentile = float(np.percentile(informative_sharpness, 25))
    edge_density = float(np.mean(edge_density_values[informative_mask])) if np.any(informative_mask) else float(np.mean(edge_density_values))
    sharpness_metric = 0.72 * median_sharpness + 0.28 * low_percentile

    if sharpness_metric < 0.075:
        level = 'high'
    elif sharpness_metric < 0.135:
        level = 'medium'
    else:
        level = 'low'

    return level, {
        'blur_score': _round_metric(sharpness_metric),
        'median_gradient': _round_metric(median_sharpness),
        'low_gradient_percentile': _round_metric(low_percentile),
        'edge_density': _round_metric(edge_density),
        'informative_patch_ratio': _round_metric(float(np.mean(informative_mask.astype(np.float32)))),
    }


def _estimate_noise(gray: np.ndarray) -> tuple[str, dict[str, float]]:
    grad_x, grad_y = _sobel_gradients(gray)
    grad_mag = np.sqrt(grad_x * grad_x + grad_y * grad_y)
    local_mean = _mean_filter3(gray)
    residual = gray - local_mean

    patch_gradients = _patch_means(grad_mag, patch_size=24, stride=12)
    flat_threshold = float(np.percentile(patch_gradients, 35))

    h, w = gray.shape
    rows = _iter_patch_starts(h, 24, 12)
    cols = _iter_patch_starts(w, 24, 12)
    selected: list[np.ndarray] = []
    index = 0
    for row in rows:
        for col in cols:
            if patch_gradients[index] <= flat_threshold:
                selected.append(residual[row : row + 24, col : col + 24].reshape(-1))
            index += 1

    if selected:
        residual_values = np.concatenate(selected)
    else:
        residual_values = residual.reshape(-1)
    median_abs_dev = float(np.median(np.abs(residual_values - np.median(residual_values))))
    noise_sigma = 1.4826 * median_abs_dev

    if noise_sigma >= 0.03:
        level = 'high'
    elif noise_sigma >= 0.016:
        level = 'medium'
    else:
        level = 'low'

    return level, {
        'noise_score': _round_metric(noise_sigma),
        'flat_patch_gradient_threshold': _round_metric(flat_threshold),
    }


def _estimate_exposure(gray: np.ndarray) -> tuple[str, dict[str, float]]:
    mean_brightness = float(np.mean(gray))
    low_clip_ratio = float(np.mean(gray <= 0.05))
    high_clip_ratio = float(np.mean(gray >= 0.95))
    under_severity = max(low_clip_ratio * 3.0, max(0.0, 0.34 - mean_brightness) * 2.4)
    over_severity = max(high_clip_ratio * 3.0, max(0.0, mean_brightness - 0.70) * 2.4)
    exposure_severity = max(under_severity, over_severity)

    if under_severity > max(0.18, over_severity):
        level = 'underexposed'
    elif over_severity > max(0.18, under_severity):
        level = 'overexposed'
    else:
        level = 'normal'

    return level, {
        'brightness_mean': _round_metric(mean_brightness),
        'low_clip_ratio': _round_metric(low_clip_ratio),
        'high_clip_ratio': _round_metric(high_clip_ratio),
        'exposure_severity': _round_metric(exposure_severity),
    }


def _estimate_contrast(gray: np.ndarray) -> tuple[str, dict[str, float]]:
    global_std = float(np.std(gray))
    local_stds = _patch_stds(gray, patch_size=32, stride=16)
    local_median = float(np.median(local_stds))
    contrast_metric = 0.55 * global_std + 0.45 * local_median

    if contrast_metric < 0.16:
        level = 'low'
    elif contrast_metric > 0.31:
        level = 'high'
    else:
        level = 'normal'

    return level, {
        'contrast_std': _round_metric(contrast_metric),
        'global_contrast_std': _round_metric(global_std),
        'local_contrast_median': _round_metric(local_median),
    }


def _estimate_compression(gray: np.ndarray) -> tuple[str, dict[str, float]]:
    diff_h = np.abs(np.diff(gray, axis=1))
    diff_v = np.abs(np.diff(gray, axis=0))

    boundary_cols = np.arange(7, diff_h.shape[1], 8)
    boundary_rows = np.arange(7, diff_v.shape[0], 8)

    boundary_h = float(np.mean(diff_h[:, boundary_cols])) if boundary_cols.size else 0.0
    boundary_v = float(np.mean(diff_v[boundary_rows, :])) if boundary_rows.size else 0.0

    interior_cols = np.setdiff1d(np.arange(diff_h.shape[1]), boundary_cols)
    interior_rows = np.setdiff1d(np.arange(diff_v.shape[0]), boundary_rows)
    interior_h = float(np.mean(diff_h[:, interior_cols])) if interior_cols.size else 0.0
    interior_v = float(np.mean(diff_v[interior_rows, :])) if interior_rows.size else 0.0

    boundary_strength = (boundary_h + boundary_v) / 2.0
    interior_strength = max(1e-6, (interior_h + interior_v) / 2.0)
    blockiness_ratio = max(0.0, (boundary_strength / interior_strength) - 1.0)
    blockiness_excess = max(0.0, boundary_strength - interior_strength)
    compression_score = blockiness_ratio + 8.0 * blockiness_excess

    if compression_score >= 0.24:
        level = 'high'
    elif compression_score >= 0.08:
        level = 'medium'
    else:
        level = 'low'

    return level, {
        'compression_score': _round_metric(compression_score),
        'blockiness_ratio': _round_metric(blockiness_ratio),
        'blockiness_excess': _round_metric(blockiness_excess),
    }


def _collect_issues(diagnostics: dict[str, Any]) -> list[str]:
    issues: list[str] = []
    if diagnostics['blur'] == 'high':
        issues.append('模糊严重')
    elif diagnostics['blur'] == 'medium':
        issues.append('模糊程度中')

    if diagnostics['noise'] == 'high':
        issues.append('噪声高')
    elif diagnostics['noise'] == 'medium':
        issues.append('噪声中')

    if diagnostics['exposure'] == 'underexposed':
        issues.append('欠曝')
    elif diagnostics['exposure'] == 'overexposed':
        issues.append('过曝')

    if diagnostics['contrast'] == 'low':
        issues.append('对比度低')
    elif diagnostics['contrast'] == 'high':
        issues.append('对比度偏强')

    if diagnostics['compression_artifacts'] == 'high':
        issues.append('压缩痕迹高')
    elif diagnostics['compression_artifacts'] == 'medium':
        issues.append('压缩痕迹中')
    return issues


def _build_summary(diagnostics: dict[str, Any]) -> str:
    issues = _collect_issues(diagnostics)
    if not issues:
        return '未发现明显的技术质量缺陷。'
    return f"主要质量问题：{'，'.join(issues)}。"


def _diagnose_image(rgb_array: np.ndarray) -> dict[str, Any]:
    arr = rgb_array.astype(np.float32) / 255.0
    gray = arr[..., 0] * 0.299 + arr[..., 1] * 0.587 + arr[..., 2] * 0.114

    blur_level, blur_metrics = _estimate_blur(gray)
    noise_level, noise_metrics = _estimate_noise(gray)
    exposure_level, exposure_metrics = _estimate_exposure(gray)
    contrast_level, contrast_metrics = _estimate_contrast(gray)
    compression_level, compression_metrics = _estimate_compression(gray)

    diagnostics = {
        'blur': blur_level,
        'noise': noise_level,
        'exposure': exposure_level,
        'contrast': contrast_level,
        'compression_artifacts': compression_level,
        'metrics': {
            **blur_metrics,
            **noise_metrics,
            **exposure_metrics,
            **contrast_metrics,
            **compression_metrics,
        },
    }
    diagnostics['issues'] = _collect_issues(diagnostics)
    diagnostics['summary'] = _build_summary(diagnostics)
    return diagnostics


def diagnose_rgb_array(rgb_array: np.ndarray) -> dict[str, Any]:
    return _diagnose_image(rgb_array)


class QualityDiagnosticsSkill(AnalysisSkill):
    skill_id = 'diagnostics'
    aliases = ('quality_diagnostics', 'diagnostic')
    description = 'Estimate blur, noise, exposure, contrast, and compression using low-level image features.'

    async def run(self, context: SkillContext) -> SkillOutcome:
        image = await context.load_rgb_image()
        diagnostics = await asyncio.to_thread(_diagnose_image, np.asarray(image))

        return SkillOutcome(
            skill_id=self.skill_id,
            data={'diagnostics': diagnostics},
            models={'diagnostics': 'Heuristic Diagnostic Analyzer v2'},
        )
