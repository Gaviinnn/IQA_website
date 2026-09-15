- # 图像质量评估与内容识别网站（线下版/MVP）

  ## 一、模型与调用

  - **IQA（NR-IQA）**：MANIQA（使用公开训练好的权重）。
  - **内容识别**：**Doubao-Seed-1.6 Vision**（火山方舟/火山引擎 Doubao 系列，多模态视觉理解），可保留 **Qwen-VL-Max** 作为备选。

  ------

  ## 二、实现路径（落地版）

  ### 1）前端（React）

  - 上传组件：`multipart/form-data`；选择文件后**立即本地校验**（扩展名与大小）。
  - 反馈：进度条（Progress）、骨架屏（Skeleton），结果卡片化展示。
  - 失败态：类型/大小不符、网络超时、API 错误的**可读提示**。

  ### 2）后端（FastAPI）

  - 两个接口：
    - `POST /upload`：接收文件，做**扩展名 + MIME 双白名单**校验、像素与大小限制；
    - `POST /analyze`：转调 **Doubao-Seed-1.6 Vision**，接入 MANIQA 分数；统一结构化输出 JSON。
  - 文件上传的正确写法与示例：**FastAPI 文件上传（UploadFile）文档**、**UploadFile 参考**、（补充中文教程）。 [FastAPI+2fastapi.org.cn](https://fastapi.tiangolo.com/zh/tutorial/request-files/?utm)

  ### 3）统一返回 JSON（Response Contract）

  ```json
  {
    "quality": {
      "score": 65.2,
      "level": "中等",
      "explanation": "图像存在轻微模糊和压缩痕迹，整体质量一般"
    },
    "content": {
      "caption": "一只狗在海滩上奔跑，背景有遮阳伞。",
      "objects": [
        {"label": "dog", "score": 0.97},
        {"label": "beach", "score": 0.88},
        {"label": "umbrella", "score": 0.62}
      ]
    },
    "meta": {
      "model": "doubao-seed-1.6-vision",
      "inference_ms": 520,
      "request_id": "req_20250924xxx"
    }
  }
  
  ```
  
  > 约定：`objects[].score ∈ [0,1]`；`quality.score ∈ [0,100]`；空结果用空数组/`null`，不可省略字段。
  
  ### 4）本地存储与日志
  
  - 不长期保存用户图片；仅存**临时文件**（自动清理），日志记录：文件名（随机化）、MIME、像素、大小、耗时、错误堆栈、模型版本。
  
  ### 5）安全与上传基线（必须）
  
  - **扩展名白名单**：`.jpg .jpeg .png .webp`。
  - **MIME 白名单**：`image/jpeg image/png image/webp`。
  - **像素上限**：`≤ 4096 × 4096`；**文件上限**：`≤ 5 MB`（先按 MVP 定）。
- **隔离目录**：上传目录与静态目录物理/逻辑隔离；随机文件名；绝不直链回显。
  - **超时/限流**：接口超时 15s；同 IP 并发 ≤ 5、速率 ≤ 10 req/min（本地实现可只先考虑接口超时）。
- **参考**：OWASP 文件上传/安全编码中文资料。 [owasp.org.cn](https://www.owasp.org.cn/OWASP-CHINA/owasp-project/download/OWASP_SCP_Quick_Reference_Guide-Chinese.pdf?utm)
  
------
  
## 三、内容规范
  
- **允许格式**：JPG/JPEG、PNG、WEBP。
  - **大小与分辨率**：`≤ 5 MB`；`≤ 4096×4096`（超过则前端压缩，后端二次兜底）。
  - **失败提示**：
    - 415（不支持类型）：提示“仅支持 jpg/png/webp”；
    - 413（实体过大）：提示“请上传 ≤5MB、≤4096×4096 的图片”；
    - 504/524（超时）：提示“模型响应超时，请重试”；
    - 500：提示“系统繁忙，请稍后再试”。
  - 403 ：提示“图片内容不符合规范，无法输出结果”。 
  - **依据**：FastAPI 上传规范 + OWASP 上传安全基线。 [FastAPI](https://fastapi.tiangolo.com/zh/tutorial/request-files/?utm)

  ------

  ## 四、性能目标（SLO）
  
  - **端到端延迟**（单张）：目标 ≤ 1–3 秒；95 线 ≤ 3 秒（含网络）。
  - **并发/吞吐**：线下并发 **5–20**；超出排队 + 友好提示。
  
  ------
  
  ## 五、错误与重试（Resilience）
  
- **指数退避**：初始 500ms、×2 退避，最多 **2–3 次**；限定**总时长 ≤ 6s**。
  - **可重试错误**：网络超时、5xx；**不可重试**：4xx（415/413/401）。
- **回退策略**：可返回**退化结果**（仅 caption 或仅对象标签），并标注 `meta.degraded=true`。
  
------
  
  ## 六、隐私与合规（PIPL）
  
- **存储策略（线下版）**：默认**不落盘**；若需调试缓存，**最长 24 小时**自动清理。
  - **告知与同意**：页面明确说明“仅用于模型分析，不做永久保存；含人像/敏感内容请勿上传”。
- **数据最小化/保存期限**：遵循 PIPL 第十九条“保存期限应为实现处理目的所必要的最短时间”等条款（**官方发布稿**可查）。必要时出具隐私政策文本。 [国家政府网](https://www.gov.cn/xinwen/2021-08/20/content_5632486.htm?utm_source=chatgpt.com)
  - （若面向繁体环境）参考：**国防部站点的繁体版法条**。 [中国国防部](https://www.mod.gov.cn/gfbw/fgwx/flfg/4892505.html?big=fan&utm_source=chatgpt.com)

  ------
  
  ## 七、UI/UX 细节

  - 选择文件即刻做**前端校验**（扩展名/大小/像素），不合规直接拦截。
- 上传过程显示**进度**与**骨架屏**；超时提供“一键重试”。
  - 结果**卡片化**：上方缩略图；中部标签与描述；右侧质量分/提示；底部**“复制 JSON”**按钮。
- 可选：历史面板（本地缓存）+ **cursor** 分页（将时间戳/自增 ID 作为游标）。
  
  ------
  
  ## 八、测试集与验收标准

  **自建小测集**（至少 70–120 张，可以从spaq数据库中选取，spaq适合这个使用场景）：

  - 清晰/模糊/低光/强压缩/含文字（OCR）/截图/复杂场景/非照片（插画）各 **10–20 张**。
- **通过率**：主目标对象识别 Top-1 ≥ 80%；
  - **质量感知**：对“强压缩/重模糊”样例 `quality.score` 明显低于清晰样例（平均差 ≥ 20 分）；
  - **性能**：平均延迟 ≤ 2s；95 线 ≤ 3s；失败率 ≤ 2%；
  - **鲁棒性**：对极端图片（超大/EXIF 畸形/MIME 伪造）能**正确拦截**或返回明确错误。
  
------
  
## 九、接口契约（示例）
  
### `POST /upload`
  
- **请求**：`multipart/form-data`，字段 `file`。
  - **校验**：扩展名 + MIME + 像素 + 大小。
  - **响应**：`{"upload_id":"ul_2025xxx","width":1234,"height":820,"mime":"image/jpeg"}`
  - **错误**：415/413/400/500（见上）。
  
  ### `POST /analyze`

  - **请求**：`{"upload_id":"ul_2025xxx"}`（或直传 base64）；
- **调用**：Doubao-Seed-1.6 Vision（OpenAI 兼容/HTTP），可对照 **Doubao 文档** 与 **Qwen API**。
  - **响应**：返回“统一 JSON”。
- **错误**：5xx 退避重试；4xx 直接提示。