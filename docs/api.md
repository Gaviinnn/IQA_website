# API reference

[Back to the project](../README.md)

Default base URL: `http://127.0.0.1:8000`. FastAPI provides the generated schema at [`/openapi.json`](http://127.0.0.1:8000/openapi.json) and interactive documentation at [`/docs`](http://127.0.0.1:8000/docs). Examples below use placeholder IDs; substitute values returned by your own run.

## Endpoints

| Method | Path | Purpose |
| --- | --- | --- |
| GET | `/` | Application name and version |
| GET | `/health` | Backend, MANIQA, and provider readiness |
| GET | `/skills` | UI-visible analysis skills |
| GET | `/logs/latest` | Recent log entries; optional `limit` |
| POST | `/upload` | Upload images |
| POST | `/analyze` | Analyze uploaded image IDs |
| GET | `/history` | Search and paginate batches |
| GET | `/history/{batch_id}` | Full batch details |
| DELETE | `/history` | Clear history and associated uploaded files |
| DELETE | `/delete` | Delete a batch using a JSON `batch_id` |
| GET | `/providers/presets` | Provider configuration presets |
| GET | `/providers/profiles` | Saved profiles and active profile ID |
| POST | `/providers/profiles` | Create or update a profile |
| POST | `/providers/profiles/activate` | Activate a profile |
| DELETE | `/providers/profiles/{profile_id}` | Delete a profile |
| GET | `/providers/active` | Active profile |
| POST | `/providers/test` | Test profile connectivity |
| POST | `/filtering/batches/{batch_id}/plan` | Generate a selection plan |
| POST | `/filtering/batches/{batch_id}/run` | Execute structured rules |
| POST | `/filtering/batches/{batch_id}/chat` | Answer or execute a conversational turn |
| POST | `/filtering/batches/{batch_id}/export` | Download retained images as ZIP |

Image and thumbnail paths returned by the API are served under `/uploads/`.

## Upload and analyze

`POST /upload` accepts multipart form data with one or more `files` fields. JPEG, PNG, and WebP are supported.

```bash
curl -X POST http://127.0.0.1:8000/upload -F "files=@sample.jpg"
```

The response contains an `uploads` array with `upload_id`, filename, MIME type, size, dimensions, thumbnail URL, and timestamp.

Pass the returned IDs to `POST /analyze`:

```json
{
  "upload_ids": ["ul_example"],
  "skills": ["quality", "diagnostics"],
  "detail": "low"
}
```

Either `upload_id` or `upload_ids` is required. IDs are deduplicated. `detail` accepts `low`, `high`, or `auto`.

Omitting `skills` requests `quality`, `diagnostics`, `quality_fusion`, and `semantic`, with internal dependencies added automatically. Optional `provider_profile_id` selects a saved profile. Optional `model` and `prompt` are used by applicable model-backed skills; they do not replace MANIQA or necessarily affect every provider call.

The response is `{"results": [...]}`. Each result can contain:

| Field | Meaning |
| --- | --- |
| `quality` | Local MANIQA score, label, and explanation |
| `diagnostics` | Quality categories and low-level measurements |
| `quality_evidence` | Technical factor scores and summary |
| `quality_judge` | Model rubric scores and confidence |
| `quality_fusion` | Component scores, weights, and final score |
| `content` / `semantic` | Caption, objects, scene, and semantic attributes |
| `meta` | Batch ID, request ID, model names, skill status, timings, and warnings |
| `snapshot` | Working-image and thumbnail URLs, plus save time |

Unrequested or failed components can be `null`. A successful HTTP response may contain partial or degraded analysis; inspect `meta.degraded`, `meta.skill_status`, and `meta.warnings`.

## History

`GET /history` accepts `cursor`, `limit` (1–50, default 20), `order` (`asc` or `desc`), and optional search text `q`. It returns `history` and `next_cursor`. Items represent batches.

`GET /history/{batch_id}` returns `{"batch": ...}`.

To delete one batch, send `{"batch_id": "bat_example"}` in the JSON body of `DELETE /delete`. `DELETE /history` clears all history; use these only when deletion is intended.

## Providers

Create a profile through the UI or `POST /providers/profiles`. Required fields are `name`, `provider_id`, and `model`; provider-specific fields include `base_url`, `api_key`, `api_version`, `organization`, and `region`. Supply `profile_id` to update an existing profile.

Use `{"profile_id": "prf_example"}` for activation and connectivity tests. Profile responses mask secrets; the local database still stores credentials. See [data handling](setup.md#local-data-and-privacy).

## Filtering

Use a `batch_id` from analysis metadata or history.

### Plan

`POST /filtering/batches/{batch_id}/plan` accepts `query`, optional `messages`, `model`, and `provider_profile_id`. It produces a plan without executing the selection.

### Run

`POST /filtering/batches/{batch_id}/run` accepts `{"dsl": ...}`. The [rule example](filtering.md#structured-rule-example) documents the DSL object. This route evaluates the entire stored batch.

### Chat

```json
{
  "messages": [
    {"role": "user", "content": "Keep the two highest-quality images."}
  ],
  "active_upload_ids": ["ul_example_a", "ul_example_b"]
}
```

Send this to `POST /filtering/batches/{batch_id}/chat`. Optional `model` and `provider_profile_id` select the model configuration. The messages must include a nonempty user message.

The response includes `assistant_message`, `did_execute`, `turn`, and `result`. Explanatory replies have `result: null`; execution replies contain the keep/remove selection and summary. The current UI and prompts primarily target Chinese.

### Export

`POST /filtering/batches/{batch_id}/export` accepts:

```json
{"kept_upload_ids": ["ul_example_a"], "filename": "selected_images"}
```

It returns `application/zip`. The optional filename is a simple ZIP basename without an extension. Temporary archives are scheduled for deletion after the response.
