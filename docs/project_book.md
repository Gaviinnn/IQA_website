# 毕业设计选题与项目简介

## 一、选题名称
**智能图像质量感知与语义内容解析系统的设计与实现**

## 二、项目简介
本项目旨在构建一套融合图像视觉质量评估与语义理解能力的智能化分析系统，实现从图像输入到质量诊断与内容解析的全链路自动化处理。系统以先进的无参考图像质量评价模型 MANIQA 为核心，结合具备强大视觉语义推理能力的 Doubao Seed 1.6 Vision 模型，对图像质量、语义描述与关键对象的综合信息进行统一解析。前后端采用 React 与 FastAPI 构建，前端负责上传、历史与结果可视化，后端承载文件处理、模型调度、日志与监控，全部以 JSON 协议对外输出，适配本地高性能、低延迟的离线运行环境（参考 `docs/archetecture.md`、`docs/api_contract.md`）。

## 三、项目主要功能
1. **Skill 化智能分析模块**：后端通过 `backend/services/skill_registry.py` 与 `backend/services/analyze_service.py` 构建技能注册与执行流水线，将质量评分、质量诊断、语义增强解耦为独立 skill，支持按请求动态选择与扩展。
2. **智能图像质量感知模块**：`backend/iqa/models/maniqa_service.py` 封装 MANIQA 模型，给出 0~100 的质量分数与等级；`backend/services/skill_diagnostics.py` 进一步输出 blur、noise、exposure、contrast、compression artifacts 等质量诊断结果。
3. **视觉语义理解模块**：通过 `backend/models/doubao_api.py` 与 Doubao HTTP 接口交互，将 `upload_id[]` 与 prompt 传入 Doubao Seed 1.6 Vision，生成图像自然语言描述、主要语义对象、场景分类、目标数量与复杂度信息，实现语义内容的增强解析。
4. **统一呈现与交互界面**：React 前端中的 UploadBox、ResultCard、Sidebar、ProgressBar 等组件负责上传进度、技能选择、多个结果卡片、历史分页与结构化数据可视化展示，为用户提供清晰的交互流程（参照 `frontend/src` 目录结构）。
5. **安全校验与异常处理机制**：`backend/services/uploads.py` 联合 `MAX_UPLOAD_DIM`、MIME 限制、文件大小与像素校验，支持 1~N 张图片的批量上传；`MAX_CONCURRENCY` 控制分析并发，日志系统统一捕获异常并写入 `logs/app.log`。
6. **本地日志记录与隐私控制**：后台将操作日志、推理耗时等关键元信息写入 `logs/app.log`，原图保存在 `backend/uploads` 并通过 `/uploads` 静态服务访问，遵循最小化存储原则，同时提供 `/skills`、`/logs/latest`、`/health` 等接口以保障系统可观测性。

## 四、技术路线与实现思路
- **前后端分离**：React 负责用户交互与可视化展现，FastAPI 提供 `/upload`、`/skills`、`/analyze`、`/history`、`/delete`、`/health` 等 RESTful 接口，`upload_id` 作为贯穿全链路的 ID，协议详见 `docs/api_contract.md`。
- **Skill-based 调度**：上传文件后由 `analyze_service` 根据请求中的 `skills[]` 动态解析并执行技能链，形成统一结果对象，再写入历史服务（基于 SQLite 的 `history_service_sqlite.py` 支持分页、TTL、删除等操作）。
- **图像质量评估与诊断**：质量 skill 负责 MANIQA 分数与等级输出，诊断 skill 进一步生成模糊、噪声、曝光、对比度、压缩痕迹等解释性指标。
- **语义解析与多模态融合**：语义 skill 将图像以 base64 方式送入 Doubao Seed 1.6 Vision，从结构化 JSON 中抽取语言描述、对象列表、场景分类、目标数量与复杂度信息，并与质量结果合并后返回给前端。
- **文件与任务管理**：`uploads` 服务生成 `upload_id` 与缩略图、写入元数据，`history_service` 提供删除与列表功能，日志与异常统一落地，形成完整的任务生命周期。
- **统一 JSON 协议**：输出结果采用固定的 JSON schema（如 `quality.score`、`objects[].score`、`caption`），为前端组件、实验统计与可视化提供稳定接口。

## 五、预期成果
1. 构建一套可在本地稳定运行的智能图像分析系统（React + FastAPI + MANIQA + Doubao）。
2. 完善可量化且带解释的图像质量评分机制与文字说明。
3. 实现全面的图像语义解析能力（自然语言描述、主要对象识别与置信度）。
4. 输出统一的推理接口体系与可交互的前端界面（上传、结果卡片、历史、日志）。
5. 形成技术文档、实验报告、测试数据与演示视频，在毕业论文中完成模型工程化、系统设计与可视化呈现的章节。

> 参考文档：项目说明《图像质量评估与内容识别网站（线下版 MVP）》，`docs/archetecture.md` 的架构图与 `docs/api_contract.md` 的接口规范。
