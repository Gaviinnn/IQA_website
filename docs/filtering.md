# Conversational filtering

[Back to the project](../README.md)

## User workflow

1. Upload a batch in the filtering workspace, or open a saved batch.
2. Ask an explanatory question about the images.
3. Request a selection, such as keeping the two highest-scoring images.
4. Continue refining the retained set, or reset to the full batch.
5. Inspect per-image reasons and export the retained files.

The UI and prompt logic currently target Chinese. An example request is `只保留质量最高的2张图片` (“Keep only the two highest-quality images”).

## Conversation and execution

[filtering_agent.py](../backend/services/filtering_agent.py) can answer a question, inspect images or quality metrics, and produce a structured selection plan. The chat route executes that plan only when the turn indicates an action. Explanatory replies return `did_execute: false` and do not produce a new selection.

The frontend sends `active_upload_ids` to scope subsequent chat turns to the retained set. A nonempty scope is used to narrow the input; an empty list is interpreted as the full batch by the backend.

The local [rule executor](../backend/services/filtering_executor.py) evaluates the plan against stored results. The model interprets the request; explicit rules, sorting, and limits determine the selection.

## Structured rule example

This example keeps up to two images with a fused quality score of at least 60:

```json
{
  "mode": "keep_matching",
  "logic": "and",
  "rules": [
    {"field": "quality_fusion.final_score", "op": ">=", "value": 60}
  ],
  "sort": {"field": "quality_fusion.final_score", "direction": "desc"},
  "limit": 2
}
```

The executor supports `keep_matching` and `remove_matching`, `and` and `or`, numeric comparisons, equality, `contains`, and `in`. Supported fields include fused and judge scores, semantic attributes, captions, object labels, combined content-search text, and filenames.

Unsupported rules are dropped during normalization. Inspect the normalized rules and resulting selection when integrating a custom client; do not assume unsupported conditions fail closed.

## Inspection and output

Implemented inspection tools can list batch items, inspect one or several images with a multimodal model, and recompute blur, noise, or exposure metrics. Tool traces make extra inspection visible in the response.

Results contain `kept`, `removed`, and a count summary, with per-image evaluation information. “Removed” refers to exclusion from the selection, not deletion from disk. ZIP export prefers the saved original file and falls back to the working image if the original is absent.

See [filtering endpoints](api.md#filtering) for the separate plan, run, chat, and export interfaces.
