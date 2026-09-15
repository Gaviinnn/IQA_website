# 项目文件概览（IQA_website）

本文件梳理当前项目的主要目录与文件职责，便于快速理解与协作。

## 顶层（root）
- `.env`：后端/工具相关的环境变量（如 Doubao 的 API Key、URL、模型名）。注意：前端要使用的环境变量应放在 `frontend/.env` 且以 `VITE_` 前缀命名。
- `图像质量评估与内容识别网站（线下版MVP）.md`：项目说明/规划文档（若在终端显示乱码，建议统一为 UTF‑8 编码或重命名以避免 mojibake）。

## frontend（React + Vite 前端）
- `frontend/index.html`：前端 HTML 入口。包含 `div#root` 挂载点，加载 `/src/main.jsx`。
- `frontend/vite.config.js`：Vite 配置（启用 `@vitejs/plugin-react`，开发服务器端口/host/open/proxy 等）。
- `frontend/package.json`：前端脚本与依赖（`dev`/`build`/`preview`，依赖 `react`、`react-dom`、`axios`、`vite` 等）。
- `frontend/package-lock.json`：依赖锁定文件（自动生成）。

- `frontend/src/main.jsx`：应用入口。使用 `ReactDOM.createRoot` 将 `<App />` 挂载到 `#root`，并引入全局样式 `styles.css`。
- `frontend/src/App.jsx`：根组件，当前直接渲染页面组件 `<Home />`。
- `frontend/src/styles.css`：全局样式（布局、上传区、按钮、进度条、结果卡片、响应式等）。

- `frontend/src/utils/api.js`：前端 API 封装。
  - 基于 `axios` 创建实例（`baseURL` 取自 `VITE_API_BASE_URL`，超时、JSON 头等）。
  - `uploadImages(files, onUploadProgress)`：批量上传图片。
  - `analyzeImages(payload)`：请求技能化图像分析接口，支持 `skills` 字段。
  - `fetchSkills()`：读取后端已注册技能。
  - `fetchHistory()` / `deleteHistoryItem()` / `clearHistory()`：历史记录管理。
  - `healthCheck()`：健康检查。

- 页面与组件：
  - `frontend/src/pages/Home.jsx`：主页面。负责上传/分析流程状态、技能选择、历史记录、调用 API，并组合 UI 组件。
  - `frontend/src/components/UploadBox.jsx`：上传组件。支持拖拽/点击选择、类型与大小校验、预览、技能选择、提交/重置。
  - `frontend/src/components/ProgressBar.jsx`：进度条组件。根据 `progress` 与 `status` 展示状态与进度。
  - `frontend/src/components/ResultCard.jsx`：结果展示组件。显示质量评分、质量诊断、内容识别、语义增强、模型信息与告警。
  - `frontend/src/components/Sidebar.jsx`：历史记录侧边栏。

> 说明：`frontend/dist/`（构建产物）与 `frontend/node_modules/`（依赖）为自动生成目录，通常不纳入说明与版本管理重点。

## backend（后端服务）
- `backend/main.py`：后端应用入口。通常负责创建应用实例、注册路由、中间件（如 CORS）等。
- `backend/requirements.txt`：后端依赖列表，用于环境安装。
- `backend/logs/app.log`：后端运行日志文件。

- 路由（routes）：
  - `backend/routes/upload.py`：上传接口路由（与前端 `POST /upload` 对应）。
  - `backend/routes/analyze.py`：分析接口路由（与前端 `POST /analyze` 对应）。
  - `backend/routes/history.py`：历史记录分页与清空接口。
  - `backend/routes/delete.py`：删除单条历史记录接口。
  - `backend/routes/__init__.py`：路由包初始化。

- 服务/健康检查（services）：
  - `backend/services/health.py`：健康检查服务。
  - `backend/services/analyze_service.py`：技能执行主流程。
  - `backend/services/skill_registry.py`：技能注册表与别名解析。
  - `backend/services/skill_quality.py`：质量评分技能。
  - `backend/services/skill_diagnostics.py`：质量诊断技能。
  - `backend/services/skill_semantic.py`：语义增强技能。
  - `backend/services/history_service_sqlite.py`：SQLite 历史持久层。
  - `backend/services/uploads.py`：上传、缩略图、元数据与文件清理。

- 模型/外部服务（models）：
  - `backend/models/doubao_api.py`：Doubao 视觉/对话 API 客户端封装（读取 `.env` 中 Doubao 配置）。
  - `backend/iqa/models/maniqa_service.py`：MANIQA 图像质量评估服务封装。
  - `backend/models/__init__.py`：包初始化。

- `backend/**/__pycache__/...`：Python 编译缓存（自动生成）。

## 使用与配置建议
- 前端环境变量：若需在前端访问变量，放置于 `frontend/.env` 并使用 `VITE_` 前缀（如：`VITE_API_BASE_URL`、`VITE_USE_API_MOCK=true`）。Vite 仅会将 `VITE_` 开头的变量注入 `import.meta.env`。
- 启动与构建：
  - 前端开发：在 `frontend/` 目录执行 `npm run dev`。
  - 前端构建/预览：`npm run build` / `npm run preview`（默认预览在构建产物上运行）。
  - 后端启动：根据实际框架（如 FastAPI）可使用 `uvicorn backend.main:app --reload`（仅示例，视实现为准）。
- 跨域与地址：将前端 `VITE_API_BASE_URL` 配置为后端实际地址（如 `http://127.0.0.1:8000`），并在后端开启相应的 CORS 配置。
- 文件名编码：中文文件名建议统一 UTF‑8 并避免在不支持的控制台下显示乱码，必要时可重命名为英文或拼音。
