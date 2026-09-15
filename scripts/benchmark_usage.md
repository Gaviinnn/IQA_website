# API 测试脚本说明

脚本文件：`scripts/benchmark_workflow.py`

## 1. 生成固定图片测试集

```powershell
python scripts/benchmark_workflow.py prepare
```

生成目录：

- `Test_Image/benchmark_sets/set_1`
- `Test_Image/benchmark_sets/set_3`
- `Test_Image/benchmark_sets/set_10`
- `Test_Image/benchmark_sets/set_20`

测试集清单保存到：

- `Test_Image/benchmark_sets/manifest.json`

## 2. 启动后端

示例：

```powershell
uvicorn backend.main:app --reload
```

默认脚本会请求：

- `http://127.0.0.1:8000`

## 3. 运行上传/分析/历史测试

```powershell
python scripts/benchmark_workflow.py run --prepare-if-missing
```

默认会跑：

- `set_1`
- `set_3`
- `set_10`
- `set_20`

默认分析技能：

- `quality_fusion`
- `semantic`

## 4. 带筛选工作台测试一起跑

```powershell
python scripts/benchmark_workflow.py run --prepare-if-missing --run-filter
```

默认筛选语句：

- `只保留质量最高的2张图片`

## 5. 常用参数

只跑 1 张和 3 张：

```powershell
python scripts/benchmark_workflow.py run --datasets set_1 set_3
```

每组重复 3 次：

```powershell
python scripts/benchmark_workflow.py run --repeats 3
```

指定 Provider：

```powershell
python scripts/benchmark_workflow.py run --run-filter --provider-profile-id prf_xxx
```

开始前先清空历史：

```powershell
python scripts/benchmark_workflow.py run --clear-history-first
```

## 6. 结果保存位置

每次运行都会生成一个时间戳目录：

- `output/benchmark_runs/YYYYMMDD_HHMMSS/`

其中包含：

- `summary.json`：完整汇总
- `summary.csv`：便于表格查看
- `set_1/run_01/01_upload.json`
- `set_1/run_01/02_analyze.json`
- `set_1/run_01/03_history_list.json`
- `set_1/run_01/04_history_batch.json`
- `set_1/run_01/05_filter_chat.json`（仅在 `--run-filter` 时）
- `set_1/run_01/06_filter_export.zip`（仅在筛选成功且有导出结果时）

## 7. 依赖

脚本依赖 `requests`：

```powershell
python -m pip install requests
```
