# Development and checks

[Back to the project](../README.md)

## Filtering regression tests

Run from the repository root:

```bash
python -m unittest discover -s backend/tests -v
```

The existing suite uses Python's standard-library unittest runner and stubs provider/tool calls. It verifies selection normalization, top-item selection, and content matching without loading MANIQA or calling an API.

## Frontend build

```bash
cd frontend
npm ci
npm run build
```

Build output goes to `frontend/dist/` and is ignored by Git.

## Optional workflow benchmark

[scripts/benchmark_workflow.py](../scripts/benchmark_workflow.py) exercises upload, analysis, history, and optionally filtering plus ZIP export against a running backend.

**Prerequisites:** backend dependencies, local MANIQA weights, provider configuration for model-backed skills, and the original local benchmark images. The script does not download or synthesize the missing source corpus.

The current dataset definitions expect these files in `Test_Image/`:

```text
操场.jpg
空中花园.jpg
操场_unified.jpg
空中花园_unified.jpg
操场_degraded.jpg
空中花园_degraded.jpg
```

These private test images are excluded from the repository. The optional [compress_image.py](../compress_image.py) utility can produce resized and degraded copies from local images; its added noise is random. The benchmark copies the named source files into batches of 1, 3, 10, and 20, with repeated inputs in larger batches.

Once prerequisites are present:

```bash
python scripts/benchmark_workflow.py prepare
python scripts/benchmark_workflow.py run --datasets set_1 set_3
python scripts/benchmark_workflow.py run --datasets set_1 set_3 --run-filter
```

Useful options include `--base-url`, `--repeats`, `--skills`, `--timeout`, `--provider-profile-id`, and `--filter-query`. `--clear-history-first` deletes existing history before a run.

Results are written to `output/benchmark_runs/<timestamp>/`, including summary JSON/CSV, endpoint responses, and exports when applicable. Outputs are ignored by Git.

A passing logic test or frontend build does not verify model accuracy or end-to-end inference. Record the checkpoint, provider/model, dependency versions, device, and image set when reporting benchmark results.
