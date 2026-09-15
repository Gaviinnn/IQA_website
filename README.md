# 智能图像质量感知与语义内容解析系统

基于 React/Vite 与 FastAPI 的本地图像分析应用。它提供图片上传、MANIQA 无参考质量评分、质量诊断、语义内容解析、结果筛选和本地历史记录功能。

## 项目结构

```text
backend/                 FastAPI 服务、图像质量模型与业务逻辑
frontend/                React + Vite 前端
scripts/                 基准测试脚本
docs/                    架构、接口与设计说明
```

运行产生的上传文件、SQLite 历史、日志、构建产物、模型权重、测试素材和个人答辩材料均保留在本地，且由 `.gitignore` 排除，避免泄露密钥或提交大文件。

## 环境要求

- Python 3.10+（建议使用与 PyTorch 2.5.1 兼容的版本）
- Node.js 18+
- 已准备的 MANIQA 权重文件：`backend/iqa/models/MANIQA_PIPAL-ae6d356b.pth`

> 权重文件不会随仓库提交；放入上述路径后，服务会以离线模式加载它。

## 本地启动

1. 在项目根目录创建后端配置：复制 `.env.example` 为 `.env`，按需填写模型服务密钥。没有配置外部模型时，质量评分仍可使用本地 MANIQA 权重；依赖外部模型的说明/语义功能会受限。
2. 安装后端依赖：

   ```bash
   python -m venv .venv
   .venv\\Scripts\\activate
   pip install -r backend/requirements.txt
   ```

3. 启动后端：

   ```bash
   uvicorn backend.main:app --reload
   ```

4. 在另一终端启动前端：

   ```bash
   cd frontend
   npm install
   npm run dev
   ```

默认访问地址为 `http://127.0.0.1:5173`，后端健康检查为 `http://127.0.0.1:8000/health`。

## 验证

```bash
python -m pytest backend/tests
cd frontend && npm run build
```

## 文档

- [启动说明](docs/launch.md)
- [接口契约](docs/api_contract.md)
- [架构说明](docs/archetecture.md)
- [筛选智能体设计](docs/filtering_agent_design.md)

## 安全说明

请勿提交 `.env`、provider profile 数据库或上传历史。若密钥曾以其他方式泄露，请在对应平台立即轮换。
