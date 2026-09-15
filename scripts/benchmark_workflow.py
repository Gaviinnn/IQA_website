from __future__ import annotations

import argparse
import csv
import json
import mimetypes
import shutil
import statistics
import sys
import time
from datetime import datetime
from pathlib import Path
from typing import Any

try:
    import requests
except ImportError as exc:  # pragma: no cover - dependency hint
    raise SystemExit(
        "缺少 requests 依赖。请先执行: python -m pip install requests"
    ) from exc


ROOT_DIR = Path(__file__).resolve().parent.parent
TEST_IMAGE_DIR = ROOT_DIR / "Test_Image"
BENCHMARK_SET_DIR = TEST_IMAGE_DIR / "benchmark_sets"
OUTPUT_DIR = ROOT_DIR / "output" / "benchmark_runs"

DEFAULT_SKILLS = ["quality_fusion", "semantic"]
DEFAULT_FILTER_QUERY = "只保留质量最高的2张图片"
DEFAULT_TIMEOUT = 180

DATASET_DEFINITIONS: dict[str, list[str]] = {
    "set_1": [
        "操场_unified.jpg",
    ],
    "set_3": [
        "操场_unified.jpg",
        "空中花园_unified.jpg",
        "操场_degraded.jpg",
    ],
    "set_10": [
        "操场_unified.jpg",
        "空中花园_unified.jpg",
        "操场_degraded.jpg",
        "空中花园_degraded.jpg",
        "操场.jpg",
        "空中花园.jpg",
        "操场_unified.jpg",
        "空中花园_unified.jpg",
        "操场_degraded.jpg",
        "空中花园_degraded.jpg",
    ],
    "set_20": [
        "操场_unified.jpg",
        "空中花园_unified.jpg",
        "操场_degraded.jpg",
        "空中花园_degraded.jpg",
        "操场.jpg",
        "空中花园.jpg",
        "操场_unified.jpg",
        "空中花园_unified.jpg",
        "操场_degraded.jpg",
        "空中花园_degraded.jpg",
        "操场.jpg",
        "空中花园.jpg",
        "操场_unified.jpg",
        "空中花园_unified.jpg",
        "操场_degraded.jpg",
        "空中花园_degraded.jpg",
        "操场.jpg",
        "空中花园.jpg",
        "操场_unified.jpg",
        "空中花园_unified.jpg",
    ],
}


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="准备固定图片测试集，并执行本地 API 基准测试。"
    )
    subparsers = parser.add_subparsers(dest="command", required=True)

    prepare_parser = subparsers.add_parser("prepare", help="生成 1/3/10/20 张图片测试集")
    prepare_parser.add_argument(
        "--force",
        action="store_true",
        help="已存在时覆盖 benchmark_sets 目录内容",
    )

    run_parser = subparsers.add_parser("run", help="执行上传/分析/历史/筛选测试")
    run_parser.add_argument(
        "--base-url",
        default="http://127.0.0.1:8000",
        help="后端 API 地址，默认 http://127.0.0.1:8000",
    )
    run_parser.add_argument(
        "--datasets",
        nargs="+",
        default=list(DATASET_DEFINITIONS.keys()),
        choices=list(DATASET_DEFINITIONS.keys()),
        help="要执行的测试集，默认全部",
    )
    run_parser.add_argument(
        "--detail",
        default="low",
        choices=["low", "high", "auto"],
        help="分析 detail 参数",
    )
    run_parser.add_argument(
        "--skills",
        nargs="+",
        default=DEFAULT_SKILLS,
        help="分析 skills 列表，默认 quality_fusion semantic",
    )
    run_parser.add_argument(
        "--provider-profile-id",
        default=None,
        help="可选，指定 Provider Profile",
    )
    run_parser.add_argument(
        "--model",
        default=None,
        help="可选，覆盖本次分析使用的模型名",
    )
    run_parser.add_argument(
        "--prompt",
        default=None,
        help="可选，自定义分析提示词",
    )
    run_parser.add_argument(
        "--repeats",
        type=int,
        default=1,
        help="每个测试集重复执行次数，默认 1",
    )
    run_parser.add_argument(
        "--timeout",
        type=int,
        default=DEFAULT_TIMEOUT,
        help=f"接口超时时间（秒），默认 {DEFAULT_TIMEOUT}",
    )
    run_parser.add_argument(
        "--clear-history-first",
        action="store_true",
        help="开始前先清空一次历史记录",
    )
    run_parser.add_argument(
        "--run-filter",
        action="store_true",
        help="附带执行筛选工作台对话测试和导出",
    )
    run_parser.add_argument(
        "--filter-query",
        default=DEFAULT_FILTER_QUERY,
        help=f"筛选测试语句，默认：{DEFAULT_FILTER_QUERY}",
    )
    run_parser.add_argument(
        "--prepare-if-missing",
        action="store_true",
        help="如果 benchmark_sets 缺失，则自动先生成",
    )

    return parser.parse_args()


def prepare_benchmark_sets(*, force: bool = False) -> dict[str, Any]:
    if BENCHMARK_SET_DIR.exists() and force:
        shutil.rmtree(BENCHMARK_SET_DIR)
    BENCHMARK_SET_DIR.mkdir(parents=True, exist_ok=True)

    manifest: dict[str, Any] = {"generated_at": now_iso(), "datasets": {}}

    for dataset_name, source_names in DATASET_DEFINITIONS.items():
        target_dir = BENCHMARK_SET_DIR / dataset_name
        target_dir.mkdir(parents=True, exist_ok=True)

        for old_file in target_dir.iterdir():
            if old_file.is_file():
                old_file.unlink()

        copied_files: list[str] = []
        for index, source_name in enumerate(source_names, start=1):
            source_path = TEST_IMAGE_DIR / source_name
            if not source_path.exists():
                raise FileNotFoundError(f"缺少源图片: {source_path}")

            suffix = source_path.suffix
            stem = source_path.stem
            target_name = f"{index:02d}_{stem}{suffix}"
            target_path = target_dir / target_name
            shutil.copy2(source_path, target_path)
            copied_files.append(target_name)

        manifest["datasets"][dataset_name] = {
            "count": len(copied_files),
            "source_images": source_names,
            "files": copied_files,
            "directory": str(target_dir.relative_to(ROOT_DIR)),
        }

    manifest_path = BENCHMARK_SET_DIR / "manifest.json"
    manifest_path.write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    return manifest


def ensure_datasets_exist(*, prepare_if_missing: bool) -> None:
    missing = [name for name in DATASET_DEFINITIONS if not (BENCHMARK_SET_DIR / name).exists()]
    if not missing:
        return
    if not prepare_if_missing:
        raise FileNotFoundError(
            f"缺少测试集目录: {', '.join(missing)}。请先执行 `python scripts/benchmark_workflow.py prepare`。"
        )
    prepare_benchmark_sets(force=False)


def now_iso() -> str:
    return datetime.now().isoformat(timespec="seconds")


def run_timed(func, *args, **kwargs) -> tuple[Any, float]:
    started = time.perf_counter()
    result = func(*args, **kwargs)
    elapsed_ms = (time.perf_counter() - started) * 1000
    return result, round(elapsed_ms, 2)


def request_json(
    session: requests.Session,
    method: str,
    url: str,
    *,
    timeout: int,
    **kwargs,
) -> Any:
    response = session.request(method=method, url=url, timeout=timeout, **kwargs)
    response.raise_for_status()
    return response.json()


def guess_mime(path: Path) -> str:
    mime, _ = mimetypes.guess_type(str(path))
    return mime or "application/octet-stream"


def write_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def copy_export_if_available(response: requests.Response, target: Path) -> None:
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_bytes(response.content)


def summarize_numeric(values: list[float]) -> dict[str, float | None]:
    if not values:
        return {"avg_ms": None, "min_ms": None, "max_ms": None}
    return {
        "avg_ms": round(statistics.mean(values), 2),
        "min_ms": round(min(values), 2),
        "max_ms": round(max(values), 2),
    }


def dataset_files(dataset_name: str) -> list[Path]:
    target_dir = BENCHMARK_SET_DIR / dataset_name
    files = sorted(path for path in target_dir.iterdir() if path.is_file() and path.suffix.lower() in {".jpg", ".jpeg", ".png", ".webp"})
    if not files:
        raise FileNotFoundError(f"测试集为空: {target_dir}")
    return files


def run_benchmark(args: argparse.Namespace) -> Path:
    ensure_datasets_exist(prepare_if_missing=args.prepare_if_missing)

    session = requests.Session()
    base_url = args.base_url.rstrip("/")
    run_id = datetime.now().strftime("%Y%m%d_%H%M%S")
    run_dir = OUTPUT_DIR / run_id
    run_dir.mkdir(parents=True, exist_ok=True)

    summary: dict[str, Any] = {
        "run_id": run_id,
        "started_at": now_iso(),
        "base_url": base_url,
        "detail": args.detail,
        "skills": args.skills,
        "provider_profile_id": args.provider_profile_id,
        "model": args.model,
        "prompt": args.prompt,
        "repeats": args.repeats,
        "run_filter": args.run_filter,
        "filter_query": args.filter_query if args.run_filter else None,
        "datasets": {},
    }

    if args.clear_history_first:
        _, clear_history_ms = run_timed(
            request_json,
            session,
            "DELETE",
            f"{base_url}/history",
            timeout=args.timeout,
        )
        summary["clear_history_ms"] = clear_history_ms

    csv_rows: list[dict[str, Any]] = []

    for dataset_name in args.datasets:
        files = dataset_files(dataset_name)
        dataset_dir = run_dir / dataset_name
        dataset_dir.mkdir(parents=True, exist_ok=True)

        iteration_results: list[dict[str, Any]] = []
        upload_times: list[float] = []
        analyze_times: list[float] = []
        history_list_times: list[float] = []
        history_batch_times: list[float] = []
        filter_times: list[float] = []
        export_times: list[float] = []

        for repeat_index in range(1, args.repeats + 1):
            repeat_dir = dataset_dir / f"run_{repeat_index:02d}"
            repeat_dir.mkdir(parents=True, exist_ok=True)

            upload_payload = []
            file_handles = []
            try:
                for file_path in files:
                    handle = file_path.open("rb")
                    file_handles.append(handle)
                    upload_payload.append(
                        ("files", (file_path.name, handle, guess_mime(file_path)))
                    )

                upload_response, upload_ms = run_timed(
                    request_json,
                    session,
                    "POST",
                    f"{base_url}/upload",
                    timeout=args.timeout,
                    files=upload_payload,
                )
            finally:
                for handle in file_handles:
                    handle.close()

            write_json(repeat_dir / "01_upload.json", upload_response)
            upload_times.append(upload_ms)

            upload_ids = [item["upload_id"] for item in upload_response.get("uploads", [])]
            analyze_payload: dict[str, Any] = {
                "upload_ids": upload_ids,
                "detail": args.detail,
                "skills": args.skills,
            }
            if args.provider_profile_id:
                analyze_payload["provider_profile_id"] = args.provider_profile_id
            if args.model:
                analyze_payload["model"] = args.model
            if args.prompt:
                analyze_payload["prompt"] = args.prompt

            analyze_response, analyze_ms = run_timed(
                request_json,
                session,
                "POST",
                f"{base_url}/analyze",
                timeout=args.timeout,
                json=analyze_payload,
            )
            write_json(repeat_dir / "02_analyze.json", analyze_response)
            analyze_times.append(analyze_ms)

            results = analyze_response.get("results", [])
            batch_id = None
            if results:
                batch_id = ((results[0].get("meta") or {}).get("batch_id"))

            history_list_response, history_list_ms = run_timed(
                request_json,
                session,
                "GET",
                f"{base_url}/history",
                timeout=args.timeout,
                params={"limit": 20},
            )
            write_json(repeat_dir / "03_history_list.json", history_list_response)
            history_list_times.append(history_list_ms)

            history_batch_response = None
            history_batch_ms = None
            if batch_id:
                history_batch_response, history_batch_ms = run_timed(
                    request_json,
                    session,
                    "GET",
                    f"{base_url}/history/{batch_id}",
                    timeout=args.timeout,
                )
                write_json(repeat_dir / "04_history_batch.json", history_batch_response)
                history_batch_times.append(history_batch_ms)

            filter_response = None
            filter_ms = None
            export_ms = None
            export_file = None
            if args.run_filter and batch_id:
                filter_payload = {
                    "messages": [{"role": "user", "content": args.filter_query}],
                    "active_upload_ids": [],
                }
                if args.provider_profile_id:
                    filter_payload["provider_profile_id"] = args.provider_profile_id
                if args.model:
                    filter_payload["model"] = args.model

                filter_response, filter_ms = run_timed(
                    request_json,
                    session,
                    "POST",
                    f"{base_url}/filtering/batches/{batch_id}/chat",
                    timeout=args.timeout,
                    json=filter_payload,
                )
                write_json(repeat_dir / "05_filter_chat.json", filter_response)
                filter_times.append(filter_ms)

                kept_upload_ids = [
                    item["upload_id"]
                    for item in ((filter_response.get("result") or {}).get("kept") or [])
                    if item.get("upload_id")
                ]
                if kept_upload_ids:
                    export_started = time.perf_counter()
                    export_response = session.post(
                        f"{base_url}/filtering/batches/{batch_id}/export",
                        timeout=args.timeout,
                        json={
                            "kept_upload_ids": kept_upload_ids,
                            "filename": f"{dataset_name}_run_{repeat_index:02d}",
                        },
                    )
                    export_response.raise_for_status()
                    export_ms = round((time.perf_counter() - export_started) * 1000, 2)
                    export_file = repeat_dir / "06_filter_export.zip"
                    copy_export_if_available(export_response, export_file)
                    export_times.append(export_ms)

            iteration = {
                "dataset": dataset_name,
                "repeat": repeat_index,
                "item_count": len(files),
                "upload_ms": upload_ms,
                "analyze_ms": analyze_ms,
                "history_list_ms": history_list_ms,
                "history_batch_ms": history_batch_ms,
                "filter_chat_ms": filter_ms,
                "export_ms": export_ms,
                "batch_id": batch_id,
                "upload_ids": upload_ids,
                "did_execute_filter": bool(filter_response and filter_response.get("did_execute")),
                "export_file": str(export_file.relative_to(ROOT_DIR)) if export_file else None,
            }
            iteration_results.append(iteration)
            csv_rows.append(iteration)

        dataset_summary = {
            "item_count": len(files),
            "files": [str(path.relative_to(ROOT_DIR)) for path in files],
            "iterations": iteration_results,
            "metrics": {
                "upload": summarize_numeric(upload_times),
                "analyze": summarize_numeric(analyze_times),
                "history_list": summarize_numeric(history_list_times),
                "history_batch": summarize_numeric(history_batch_times),
                "filter_chat": summarize_numeric(filter_times),
                "filter_export": summarize_numeric(export_times),
            },
        }
        summary["datasets"][dataset_name] = dataset_summary

    summary["finished_at"] = now_iso()
    write_json(run_dir / "summary.json", summary)
    write_csv(run_dir / "summary.csv", csv_rows)
    return run_dir


def write_csv(path: Path, rows: list[dict[str, Any]]) -> None:
    if not rows:
        return
    fieldnames = list(rows[0].keys())
    with path.open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)


def main() -> int:
    args = parse_args()
    if args.command == "prepare":
        manifest = prepare_benchmark_sets(force=args.force)
        print("测试集已生成：", BENCHMARK_SET_DIR)
        print(json.dumps(manifest, ensure_ascii=False, indent=2))
        return 0

    if args.command == "run":
        run_dir = run_benchmark(args)
        print(f"测试完成，结果保存在: {run_dir}")
        print(f"汇总 JSON: {run_dir / 'summary.json'}")
        print(f"汇总 CSV:  {run_dir / 'summary.csv'}")
        return 0

    print("未知命令", file=sys.stderr)
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
