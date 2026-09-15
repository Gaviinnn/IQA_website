# AI Image Analysis Platform - API Contract (v2.1)

## Overview

This version adds a provider configuration center. The system now supports:

- skill-based image analysis
- configurable cloud LLM providers
- persistent provider profiles
- frontend provider management

Implemented endpoints:

| Endpoint | Method | Description |
| --- | --- | --- |
| `/upload` | `POST` | Upload one or more images and generate metadata + thumbnail |
| `/analyze` | `POST` | Run one or more registered skills for one or more uploads |
| `/skills` | `GET` | Return the currently registered skills |
| `/providers/presets` | `GET` | Return built-in cloud vendor presets |
| `/providers/profiles` | `GET` | Return saved provider profiles |
| `/providers/profiles` | `POST` | Create or update a provider profile |
| `/providers/profiles/activate` | `POST` | Activate a provider profile |
| `/providers/profiles/{profile_id}` | `DELETE` | Delete a provider profile |
| `/providers/active` | `GET` | Return the current active provider profile |
| `/providers/test` | `POST` | Test a provider profile connection |
| `/history` | `GET` | Read paginated history records |
| `/history` | `DELETE` | Clear all history records and uploaded files |
| `/delete` | `DELETE` | Delete a single history record |
| `/health` | `GET` | Service health status |
| `/logs/latest` | `GET` | Read latest backend logs |

## Analyze API

`POST /analyze`

Request:

```json
{
  "upload_ids": ["ul_20260312_123000_abcd1234"],
  "skills": ["quality", "diagnostics", "semantic"],
  "detail": "low",
  "provider_profile_id": "prf_1234abcd5678ef90",
  "model": "qwen-vl-max",
  "prompt": "如果是图表，请重点给出场景类型与复杂度。"
}
```

Rules:

- `upload_id` and `upload_ids` are both supported
- `skills` is optional; default order is `quality -> diagnostics -> semantic`
- `provider_profile_id` is optional; if omitted, backend uses the active provider profile
- `model` is optional; if present, it overrides the active profile's saved model for that request only

Response shape:

```json
{
  "results": [
    {
      "upload_id": "ul_20260312_123000_abcd1234",
      "filename": "chart.png",
      "quality": {
        "score": 61.3,
        "level": "良好",
        "explanation": "文字边缘较清晰，但高亮区域压缩了部分层次。"
      },
      "diagnostics": {
        "blur": "low",
        "noise": "medium",
        "exposure": "overexposed",
        "contrast": "high",
        "compression_artifacts": "low",
        "summary": "主要质量问题：曝光过强，对比度偏高，噪声中。",
        "metrics": {
          "blur_score": 0.0447,
          "brightness_mean": 0.7712,
          "contrast_std": 0.3151,
          "noise_score": 0.0182,
          "compression_score": 0.0
        }
      },
      "content": {
        "caption": "一张包含四个热力图的学术图表截图。",
        "objects": [
          {"label": "heatmap", "score": 0.95},
          {"label": "chart", "score": 0.92}
        ]
      },
      "semantic": {
        "scene": "document",
        "object_count": 2,
        "complexity": "medium",
        "scene_clutter": "low",
        "semantic_tags": ["heatmap", "chart"]
      },
      "meta": {
        "models": {
          "quality": "MANIQA v1.2",
          "diagnostics": "Heuristic Diagnostic Analyzer v1",
          "content": "Alibaba Qwen / qwen-vl-max",
          "semantic": "Alibaba Qwen / qwen-vl-max"
        },
        "detail": "low",
        "elapsed_ms": 1420,
        "degraded": false,
        "request_id": "req_20260312_123004_18dcfe92",
        "skill_order": ["quality", "diagnostics", "semantic"],
        "skill_status": {
          "quality": "ok",
          "diagnostics": "ok",
          "semantic": "ok"
        }
      },
      "snapshot": {
        "image": "/uploads/ul_20260312_123000_abcd1234.png",
        "thumbnail": "/uploads/ul_20260312_123000_abcd1234_thumb.jpg",
        "saved_at": "2026-03-12T04:30:04+00:00"
      }
    }
  ]
}
```

## Provider preset API

`GET /providers/presets`

Response:

```json
{
  "presets": [
    {
      "id": "openai",
      "label": "OpenAI",
      "protocol": "openai_compatible",
      "default_base_url": "https://api.openai.com/v1",
      "default_model": "gpt-4.1-mini",
      "docs_url": "https://platform.openai.com/docs/api-reference",
      "supports_multimodal": true
    },
    {
      "id": "anthropic",
      "label": "Anthropic Claude",
      "protocol": "anthropic_native",
      "default_base_url": "https://api.anthropic.com/v1",
      "default_model": "claude-sonnet-4-5",
      "docs_url": "https://docs.anthropic.com/en/api/messages",
      "supports_multimodal": true,
      "requires_api_version": true
    }
  ]
}
```

Current built-in presets include:

- OpenAI
- Azure OpenAI
- Anthropic Claude
- Google Gemini
- Alibaba Qwen
- Volcengine Ark / Doubao
- DeepSeek
- OpenRouter
- xAI Grok
- Zhipu GLM
- Baidu Qianfan
- Tencent Hunyuan
- Moonshot Kimi
- MiniMax

## Provider profile API

`POST /providers/profiles`

```json
{
  "name": "Lab Qwen",
  "provider_id": "qwen",
  "base_url": "https://dashscope.aliyuncs.com/compatible-mode/v1",
  "model": "qwen-vl-max",
  "api_key": "sk-***",
  "api_version": "",
  "organization": "",
  "region": "cn-beijing",
  "is_active": true
}
```

Response:

```json
{
  "profile": {
    "profile_id": "prf_a1b2c3d4e5f67890",
    "name": "Lab Qwen",
    "provider_id": "qwen",
    "protocol": "openai_compatible",
    "base_url": "https://dashscope.aliyuncs.com/compatible-mode/v1",
    "model": "qwen-vl-max",
    "api_key_masked": "sk-1***9abc",
    "api_version": null,
    "organization": null,
    "region": "cn-beijing",
    "is_active": true,
    "created_at": "2026-03-12T04:20:00+00:00",
    "updated_at": "2026-03-12T04:20:00+00:00"
  }
}
```

`POST /providers/profiles/activate`

```json
{"profile_id": "prf_a1b2c3d4e5f67890"}
```

`POST /providers/test`

```json
{"profile_id": "prf_a1b2c3d4e5f67890"}
```

Response:

```json
{
  "ok": true,
  "detail": "Alibaba Qwen / qwen-vl-max | pong"
}
```

## Runtime notes

- The semantic skill and MANIQA explanation both use the active provider profile unless a per-request `provider_profile_id` override is supplied.
- If no provider profile is configured, semantic analysis will fail and MANIQA explanation will fall back to a local placeholder sentence.
- Existing environment variables can still bootstrap the first provider profile automatically. Current code supports bootstrap from `DOUBAO_*` or `OPENAI_*`.
