# Setup and configuration

[Back to the project](../README.md)

## Environment

Use Python 3.10 or 3.11 with the versions recorded in [backend/requirements.txt](../backend/requirements.txt): PyTorch 2.5.1, torchvision 0.20.1, and torchaudio 2.5.1. Other Python dependencies are currently unpinned. The frontend uses React 18 and Vite 5, with an npm lockfile.

Follow the [quick start](../README.md#quick-start). For Windows PowerShell, the backend setup is:

```powershell
git clone https://github.com/Gaviinnn/IQA_website.git
Set-Location IQA_website
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -r backend/requirements.txt
Copy-Item .env.example .env
```

Run backend commands from the repository root. Use a PyTorch distribution compatible with your OS and device; the service selects CUDA when available and CPU otherwise. It does not currently select Apple's MPS backend.

## MANIQA checkpoint

The service expects exactly:

```text
backend/iqa/models/MANIQA_PIPAL-ae6d356b.pth
```

Obtain the PIPAL checkpoint from the [IQA-PyTorch model collection](https://huggingface.co/chaofengc/IQA-PyTorch-Weights/tree/main). The upstream [MANIQA implementation](https://github.com/chaofengc/IQA-PyTorch/blob/main/pyiqa/archs/maniqa_arch.py) identifies this filename for the PIPAL model. Copy the downloaded file to the path above; a checkpoint for another training dataset is not interchangeable.

The application constructs MANIQA locally, disables remote pretrained-backbone downloads, and loads this checkpoint. It does not fetch the missing weights automatically. The checkpoint is excluded from Git.

## Provider configuration

For the full workflow, open **Provider configuration center** (`模型配置中心`) in the application:

1. Choose a preset and a vision-capable model.
2. Enter the endpoint, model identifier, and API key; supply additional fields required by your provider.
3. Save the profile, test the connection, and activate it.

The gateway implements OpenAI-compatible requests, Azure OpenAI, and Anthropic Messages requests. Presets are configuration starting points: endpoint availability and image support depend on the actual provider and model. A successful text connectivity test alone does not establish that image requests work.

Alternatively, the first profile can be bootstrapped from the backend `.env` using `DOUBAO_API_KEY`, `DOUBAO_API_URL`, and `DOUBAO_MODEL`, or `OPENAI_API_KEY`, `OPENAI_BASE_URL`, and `OPENAI_MODEL`. Doubao takes precedence when both keys are present. Once profiles exist in SQLite, manage them in the configuration center; changing `.env` does not overwrite an existing profile.

### Operating without a provider

| Component | Behavior |
| --- | --- |
| MANIQA score | Runs locally when the checkpoint is available. |
| Quality explanation | Attempts a provider call, then uses a local fallback sentence on failure. |
| Diagnostics and technical evidence | Computed locally. |
| Model judge / fusion | May use fallback evidence and report warnings when the provider fails; inspect metadata before interpreting the score. |
| Semantic analysis / visual inspection | Requires a working provider for model-generated results. |
| Natural-language filtering | Requires a provider for the full conversational workflow; structured rule execution is local. |

Local scoring does not mean that an active provider is never contacted. For example, the quality skill also requests an image-based explanation.

## Runtime settings

Copy [.env.example](../.env.example) to `.env`. Leave optional storage overrides commented out to retain the defaults.

| Variable | Default | Meaning |
| --- | --- | --- |
| `HISTORY_TTL_HOURS` | `24` | Retention window for history rows. |
| `HISTORY_MAX_RECORDS` | `500` | Maximum history image records, not batches. |
| `UPLOAD_BATCH_CONCURRENCY` | `3` | Concurrent upload saves per request. |
| `ANALYZE_MAX_CONCURRENCY` | `3` | Concurrent image analysis pipelines. |
| `MAX_FILE_MB` | `20` | Maximum uploaded file size in MiB. |
| `MAX_PIXELS` | `10000` | Maximum input side length in pixels, not total pixel count. |
| `MAX_UPLOAD_DIM` | `1200` | Maximum side length of the working image. |
| `THUMB_MAX` | `320` | Thumbnail maximum side length. |
| `CORS_ALLOW_ORIGINS` | Local frontend origins in the example | Allowed browser origins. |

The frontend defaults to `http://127.0.0.1:8000`. To change it, copy [frontend/.env.example](../frontend/.env.example) to `frontend/.env` and set `VITE_API_BASE_URL`. Restart Vite after editing it. Never put provider secrets in `VITE_*` variables.

Keep the default upload location for this version: although services accept `UPLOAD_DIR`, the static-file mount and export directory in the application still use `backend/uploads`. An empty `UPLOAD_DIR` or `HISTORY_DB_FILE` is not treated as an omitted value.

## Local data and privacy

- `backend/uploads/` contains originals, working images, thumbnails, JSON metadata, and temporary exports.
- `backend/uploads/history.db` stores history and provider profiles, including credentials in plaintext. Masking in API responses does not encrypt the database.
- `backend/logs/` contains runtime logs. Browser local storage also retains frontend state.
- History TTL and record-limit pruning remove database rows; they are not a guarantee that every associated file is erased.
- External models receive image data and prompts for the features that use them. Use images appropriate for the selected provider.
- The app has no authentication, and uploads are served by the backend. The quick-start commands bind both development servers to the loopback address.

The repository ignores runtime data, database sidecar files, secret files, and personal thesis directories. Keep the full thesis and unreviewed screenshots outside the repository; selected documentation figures live in `docs/assets/`.

## Troubleshooting

| Symptom | Check |
| --- | --- |
| Backend cannot open SQLite | Ensure the optional storage variables are omitted or valid paths; do not set them to empty strings. |
| MANIQA is degraded | Check the checkpoint filename and location, installed dependencies, and backend logs. |
| Health endpoint returns `status: ok` but analysis is incomplete | Inspect `maniqa_server` and `doubao_api` too; HTTP success is not proof of model readiness. |
| Missing descriptions or semantic fields | Activate a provider, confirm its model supports images, and inspect analysis warnings. |
| Frontend cannot reach the API | Check `VITE_API_BASE_URL`, the backend port, and CORS origins. |
| CPU analysis is slow | Start with one image and reduce `ANALYZE_MAX_CONCURRENCY` if needed. MANIQA inference itself uses a lock. |
