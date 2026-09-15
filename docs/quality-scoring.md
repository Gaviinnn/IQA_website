# Quality scoring

[Back to the project](../README.md)

## Three complementary inputs

The application retains separate score components so users can inspect how the displayed result was formed.

1. **MANIQA:** a no-reference model prediction, clamped to 0–1 and displayed on a 0–100 scale.
2. **Technical evidence:** local measurements of blur, noise, exposure, contrast, and compression mapped to factor scores.
3. **Model judge:** an optional multimodal assessment using the working image and technical evidence.

The current fusion in [skill_quality_fusion.py](../backend/services/skill_quality_fusion.py) is:

```text
final score = 0.45 × MANIQA + 0.25 × technical score + 0.30 × judge score
```

### Technical factors

| Factor | Weight |
| --- | --- |
| Blur | 0.32 |
| Noise | 0.22 |
| Exposure | 0.19 |
| Contrast | 0.17 |
| Compression | 0.10 |

[skill_quality_helpers.py](../backend/services/skill_quality_helpers.py) contains the mappings, metric thresholds, penalties, and caps. The technical score is not simply the weighted average: detected defects and combinations such as blur plus noise add penalties or cap the result.

### Score bands

| Score | Meaning | Label returned by the application |
| --- | --- | --- |
| 80–100 | Excellent | `优秀` |
| 60–<80 | Good | `良好` |
| 40–<60 | Fair | `一般` |
| 0–<40 | Poor | `较差` |

## Interpreting results

- The weights, thresholds, and bands are project heuristics, not calibrated mean-opinion scores or a universal quality standard.
- Fusion evaluates technical quality. It does not establish artistic merit or whether an image is useful for a particular task.
- The working image may be resized during upload, and MANIQA receives a 224 × 224 input. The original file is retained for export.
- When a provider call fails, the judge may fall back to technical evidence. Read `meta.degraded`, `meta.warnings`, and the component scores before relying on the final score.
- The confidence field summarizes model confidence and agreement. It is not a statistically calibrated probability.

See [architecture](architecture.md#analysis-pipeline) for skill dependencies. The thesis screenshots demonstrate the UI and sample behavior; they do not establish accuracy or generalization.
