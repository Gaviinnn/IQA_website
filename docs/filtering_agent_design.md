# 自然语言图像筛选 Agent 模块设计

## 1. 目标

当前系统已经具备以下能力：

1. 批量上传与分析图像
2. 输出融合质量分、LLM 质量审阅、语义结果
3. 对结果做建议式筛选（低质量、模糊、高噪声、曝光异常）

但当前筛选仍然停留在“给建议”的层面，尚不能完成真正的批量整理闭环。新的目标是：

> 用户上传一批图片后，用自然语言描述希望保留或去掉的图片类型，系统自动完成筛选、展示保留/移除结果，并支持下载保留图片。

典型输入：

- 去掉模糊的图片
- 只保留清晰、曝光正常、适合展示的图片
- 去掉高噪声和压缩明显的图片
- 只保留质量分高于 70 且主体清晰的图片

典型输出：

- 总数 `20`
- 保留 `12`
- 移除 `8`
- 每张图片的保留/移除原因
- 下载保留结果 ZIP

---

## 2. 为什么要做成独立模块

该功能与当前“分析工作台”不是同一个用户目标。

当前页面的核心目标是：

- 分析单张或一批图片的质量与内容
- 查看结果、解释与历史

新的筛选页面的核心目标是：

- 基于自然语言批量筛图
- 输出保留/移除决策
- 导出结果

因此建议将系统拆成两个页面：

1. `分析工作台`
   - 保留现有页面
   - 继续承担上传、分析、查看详情、历史管理

2. `筛选工作台`
   - 新增独立页面
   - 面向“自然语言筛图”和“结果导出”

这样做的好处：

1. 不会污染当前分析页的交互复杂度
2. 新模块可以独立迭代，不影响现有主链路
3. 页面定位更清晰，论文中也更容易描述为独立能力模块

建议页面路由：

- `/` 或 `/analysis`：现有分析页
- `/filter`：新的筛选页

---

## 3. Agent 里的 `skill` 到底是什么意思

这里需要先把概念说清楚。

### 3.1 Skill 不是 Tool

在 agent 体系里，`skill` 和 `tool` 不是同一个东西。

根据 Anthropic 关于 Skills 的官方说明，`skill` 是一组被打包的指令和工作流知识，用来教模型如何处理特定任务；它是“knowledge layer / workflow layer”，不是直接执行动作的 API 本身。Anthropic 还明确指出，针对 MCP/工具系统，skills 的作用是把“原始工具访问”转换成“可靠、优化的工作流”。  
来源：
- Anthropic Skills Guide: https://resources.anthropic.com/hubfs/The-Complete-Guide-to-Building-Skill-for-Claude.pdf

根据 OpenAI Agents SDK 官方文档，agentic application 的核心能力是：模型可以使用 tools、调用 specialized agents、并保留 trace。这里的 tool 是可执行能力，不是工作流知识。  
来源：
- OpenAI Agents SDK: https://developers.openai.com/api/docs/guides/agents-sdk

根据 Anthropic 的 tool use 文档与 advanced tool use 文章，tool use 指的是模型在对话中主动请求某个工具，由宿主代码执行，再把结果返回给模型继续推理。  
来源：
- Anthropic Tool Use: https://platform.claude.com/docs/en/agents-and-tools/tool-use/implement-tool-use
- Anthropic Advanced Tool Use: https://www.anthropic.com/engineering/advanced-tool-use

### 3.2 本系统中的正确映射

因此，在本项目里应该这样定义：

1. `Skill`
   - 是一套给筛选 Agent 的工作流指令
   - 例如：
     - 如何理解用户的筛图意图
     - 什么情况下需要调用额外 low-level 计算
     - 如何把自然语言转成结构化筛选 DSL
     - 如何给出保留/移除理由

2. `Tool`
   - 是 agent 可以实际调用的确定性能力
   - 例如：
     - 计算 blur 指标
     - 计算 noise 指标
     - 计算 exposure 指标
     - 直接查看单张图片
     - 直接查看一组候选图片
     - 获取 batch 内图片结果
     - 打包导出 ZIP

### 3.3 对本项目的设计结论

因此，low-level 计算部分不应该被描述为“skill 本身”，而应该是：

> 由筛选 Agent 所掌握的一套可调用 tools；  
> 而指导它何时调用、如何解读结果、如何执行筛选的那一层，才是 skill。

这才符合 agent 技术里的概念边界。

---

## 4. 模块定位

建议新增一个完全独立的模块：

`Natural Language Image Filtering Agent`

它的职责不是重新做图像分析，而是：

1. 读取已有分析结果
2. 理解用户的自然语言筛选目标
3. 必要时主动调用 low-level tools 获取补充证据
4. 生成结构化筛选规则
5. 执行筛选
6. 输出保留/移除结果
7. 打包并导出保留图片

因此，该模块本质上是：

> “基于现有分析结果的自然语言筛选与导出模块”

而不是“另一个质量分析页面”。

---

## 5. 模块边界

### 5.1 保持现有分析页不变

现有分析页继续负责：

1. 上传图片
2. 调用分析 pipeline
3. 查看质量与语义结果
4. 历史记录管理

### 5.2 新增筛选页

新的筛选页只负责：

1. 选择一个已分析 batch
2. 输入自然语言筛选要求
3. 运行筛选 Agent
4. 查看保留/移除结果
5. 下载保留图片

推荐页面流：

1. 进入 `筛选工作台`
2. 选择一个历史 batch，或在该页直接上传并分析
3. 输入自然语言筛选条件
4. 点击“开始筛选”
5. 查看：
   - 全部
   - 保留
   - 移除
6. 点击“下载保留结果”

---

### 5.3 当前实现工作流

当前系统已经落地为一条独立的对话式筛选工作流：

1. 在 `筛选工作台` 上传一批图片
2. 页面自动执行上传与分析，不再要求用户手动点击“上传并分析”
3. 分析完成后，当前批次自动进入对话上下文
4. 用户以聊天消息形式描述筛选目标
5. 后端 `chat` 接口先判断这轮消息是在咨询信息，还是明确要求执行筛选
6. 如果只是咨询，页面只返回“图片整理助手”的自然语言回复，不执行筛选
7. 如果用户明确提出保留 / 去掉 / 筛选要求，Agent 再生成 DSL，并在必要时调用 low-level tools
8. 规则执行器产出保留 / 移除结果，页面展示本轮回复、筛选结果与可下载的保留图片 ZIP

因此，当前筛选页的用户体验目标不是“填写一个表单”，而是：

> 上传一个批次，然后与“图片整理助手”连续对话，先理解批次内容，再在需要时执行筛选。

---

### 5.4 当前聊天窗口的实际执行流程

当前筛选页中的聊天窗口，不是一个单纯的前端输入框，而是一条完整的 agent 工作流。其执行流程如下：

1. 用户在 `筛选工作台` 选择一批图片
2. 页面自动调用上传接口 `/upload`
3. 上传完成后，页面自动调用分析接口 `/analyze`
4. 系统固定执行：
   - `quality_fusion`
   - `semantic`
5. 后端为本批图片生成新的 `batch_id`
6. 前端将该 `batch_id` 设为当前筛选上下文
7. 聊天窗口进入“当前 batch 已就绪”的状态

此时，用户发送的每一条消息，都会连同历史消息一起提交到：

- `POST /filtering/batches/{batch_id}/chat`

后端收到消息后，会先判断该轮消息属于哪一类：

1. **咨询类消息**
   - 例如：
     - `这批图里有夜景吗`
     - `这批图主要是什么场景`
     - `哪几张更适合展示`

2. **筛选执行类消息**
   - 例如：
     - `去掉模糊的`
     - `只保留夜景`
     - `删除高噪声图片`
     - `只保留质量最高的 6 张`

#### 5.4.1 咨询类消息的处理流程

如果后端判断当前消息属于咨询类：

1. Agent 优先尝试基于当前上下文生成自然语言回复
2. 如果仅靠已有结构化结果不足以稳定回答，则可主动调用视觉 tools：
   - `inspect_image`
   - `inspect_batch_images`
3. 这些 tools 会把图片重新作为视觉输入送给多模态模型，而不是只读已有字段
4. Agent 基于看图结果生成自然语言回复
5. 本轮不执行筛选，不生成保留/移除结果

因此，咨询类消息的返回结果应满足：

- `did_execute = false`
- `result = null`

前端行为是：

1. 在聊天区追加一条“图片整理助手”的回复
2. 不刷新下方筛选结果区

#### 5.4.2 筛选执行类消息的处理流程

如果后端判断当前消息属于筛选执行类：

1. Agent 读取当前 batch 的结构化分析结果
2. 在必要时主动调用 tools
3. 将自然语言目标转换成 DSL
4. 把 DSL 提交给规则执行器
5. 得到：
   - `kept`
   - `removed`
   - `matched_rules`
   - `unmet_rules`
6. 返回本轮自然语言回复和筛选结果

此时返回结果满足：

- `did_execute = true`
- `result` 中包含完整筛选输出

前端行为是：

1. 在聊天区追加一条“图片整理助手”的回复
2. 更新下方“筛选结果”面板
3. 用户可以继续在同一上下文中发送下一轮消息

#### 5.4.3 Agent 当前可使用的两类 tools

当前聊天 Agent 使用两类工具：

1. **Low-level quality tools**
   - `compute_blur_metrics`
   - `compute_noise_metrics`
   - `compute_exposure_metrics`

这类工具用于：

- 细化模糊判断
- 细化噪声判断
- 细化曝光判断

2. **Vision inspection tools**
   - `inspect_image`
   - `inspect_batch_images`

这类工具用于：

- 重新直接看图
- 判断夜景 / 黄昏 / 室内外 / 展示价值等高层问题
- 避免仅凭结构化字段做不可靠推断

#### 5.4.4 导出流程

当某一轮消息真正执行了筛选后，前端可以调用：

- `POST /filtering/batches/{batch_id}/export`

后端会把保留图片打包为 ZIP。

对于新上传的数据，导出优先使用原图；
对于旧数据，如果系统历史上未保存原图，则回退到分析图。

#### 5.4.5 当前聊天窗口的设计结论

因此，当前聊天窗口的本质不是：

> “输入一句 prompt，然后立刻得到固定结果”

而是：

> “以一个 batch 为上下文，与图片整理助手持续对话；  
> 对于咨询类问题，优先回答；  
> 对于明确筛选类问题，再执行筛选与导出。”

这一定义对于论文中的系统描述也更准确，因为它强调的是：

1. `batch-aware context`
2. `agent-driven decision`
3. `tool-augmented conversation`
4. `filter execution only when needed`

---

## 6. 筛选 Agent 的核心职责

筛选 Agent 不应该直接“凭感觉挑图”，而应该承担以下明确职责：

1. 读取 batch 内已有分析结果
2. 解析用户自然语言需求
3. 判断是否需要额外 low-level 证据
4. 必要时调用工具
5. 生成结构化 DSL
6. 将 DSL 交给规则执行器
7. 给出可解释的保留/移除原因

换句话说，Agent 的作用是：

> 负责理解、决策与组织；
> 真正的计算和执行由 tools / rule engine 完成。

---

## 7. Agent 什么时候调用 low-level tools

这里不应该写死成“只有低置信度时才调用”，因为这会把 agent 退化成固定 if-else。

更合理的设计是：

> Agent 可以在自己认为有必要时调用 low-level tools；
> 系统只提供边界与预算，不替 agent 预先限定唯一触发条件。

### 7.1 正确的调用原则

应当让 Agent 在以下情况下自主决定是否调用工具：

1. 用户请求本身涉及细粒度技术质量判断  
例如：
- 去掉轻微模糊的
- 保留最清晰的
- 去掉高噪声但允许轻微曝光问题

2. 现有高层结果存在歧义  
例如：
- `MANIQA`、`LLM Judge`、`technical` 之间差异较大
- 同一图片接近筛选边界

3. 需要更可解释的保留/移除理由  
例如用户问：
- 为什么这张被去掉？
- 这两张谁更清晰？

4. 用户请求包含排序或“最优保留”意图  
例如：
- 只保留最适合展示的前 5 张
- 从 20 张里选最清晰的 8 张

### 7.2 系统该提供什么，而不是替它决定什么

系统应该提供：

1. 可调用的工具列表
2. 每个工具的描述
3. 输入输出 schema
4. 调用预算
5. 结果缓存

而不应该写成：

- 只在低置信度调用
- 只允许某一个固定条件触发

这种硬编码不符合 agent 化设计。

### 7.3 推荐的控制方式

可采用以下约束，而不是固定触发规则：

1. 每个筛选任务最多调用 `N` 次 low-level tools  
例如 `N = 15`

2. 每张图片最多调用 `M` 次深查工具  
例如 `M = 3`

3. 优先使用已有分析结果  
如果已有结果足够支撑决策，agent 应避免不必要的工具调用

4. 工具结果进入 trace，供后续解释与调试

---

## 8. 新模块的总体架构

建议新增如下后端结构：

### 8.1 Agent 层

`backend/filtering/filter_agent.py`

职责：

1. 接收自然语言筛选请求
2. 读取 batch 结果摘要
3. 决定是否需要调用 tools
4. 生成 DSL
5. 输出筛选计划与解释

### 8.2 Tool 层

`backend/filtering/filter_tools.py`

提供以下可调用工具：

1. `list_batch_items(batch_id)`
   - 返回 batch 内图片基本信息与已有分析结果

2. `get_item_quality_summary(upload_id)`
   - 返回该图片的融合分、LLM 审阅、语义与摘要

3. `compute_blur_metrics(upload_id)`
   - 返回更细粒度的 blur 指标与 patch 统计

4. `compute_noise_metrics(upload_id)`
   - 返回平坦区域噪声估计、噪声等级与相关统计

5. `compute_exposure_metrics(upload_id)`
   - 返回亮度均值、裁剪比例、曝光严重度

6. `preview_filter_rules(batch_id, dsl)`
   - 预览 DSL 命中结果，不真正导出

7. `export_kept_images(batch_id, kept_upload_ids)`
   - 打包保留图片并生成下载文件

### 8.3 规则执行层

`backend/filtering/filter_executor.py`

职责：

1. 接收 DSL
2. 在 batch 结果上执行规则
3. 返回：
   - kept
   - removed
   - matched rules
   - explanation

### 8.4 导出层

`backend/filtering/filter_export.py`

职责：

1. 根据筛选结果生成 ZIP
2. 输出下载地址或流式下载响应

---

## 9. 自然语言筛选 DSL

Agent 最终不应直接返回“删第 3 张、第 7 张”，而应返回可执行 DSL。

建议 DSL：

```json
{
  "mode": "keep_matching",
  "rules": [
    {
      "field": "quality_judge.sharpness_score",
      "op": ">=",
      "value": 60
    },
    {
      "field": "quality_judge.noise_score",
      "op": ">=",
      "value": 55
    },
    {
      "field": "quality_fusion.final_score",
      "op": ">=",
      "value": 65
    }
  ],
  "sort": {
    "field": "quality_fusion.final_score",
    "direction": "desc"
  },
  "limit": null
}
```

支持的字段建议包含：

1. `quality_fusion.final_score`
2. `quality_judge.sharpness_score`
3. `quality_judge.noise_score`
4. `quality_judge.exposure_score`
5. `quality_judge.contrast_score`
6. `quality_judge.compression_score`
7. `semantic.scene`
8. `semantic.complexity`
9. `meta.elapsed_ms`

支持的操作符建议：

- `>=`
- `<=`
- `>`
- `<`
- `==`
- `!=`
- `in`
- `contains`

这样 DSL 才能支持：

- 阈值筛选
- 标签筛选
- 排序
- Top-K 保留

---

## 10. 筛选 Agent 的运行流程

建议采用两阶段执行：

### 阶段 A：Plan

输入：

- `batch_id`
- `query`

Agent 行为：

1. 读取 batch 摘要
2. 理解用户自然语言需求
3. 自主决定是否调用 low-level tools
4. 生成 DSL
5. 返回自然语言解释

输出：

```json
{
  "dsl": { "...": "..." },
  "explanation": "将移除清晰度不足、噪声偏高且综合质量偏低的图片。",
  "tool_trace": [
    "list_batch_items",
    "compute_blur_metrics: ul_xxx",
    "compute_noise_metrics: ul_yyy"
  ]
}
```

### 阶段 B：Run

输入：

- `batch_id`
- `dsl`

执行器行为：

1. 规则求值
2. 生成保留/移除列表
3. 汇总统计

输出：

```json
{
  "summary": {
    "total": 20,
    "kept": 12,
    "removed": 8
  },
  "kept": [...],
  "removed": [...]
}
```

### 阶段 C：Export

输入：

- `batch_id`
- `kept_upload_ids`

输出：

- ZIP 下载文件

---

## 11. 前端页面设计

建议新增页面：

`frontend/src/pages/FilterStudio.jsx`

### 11.1 页面结构

1. 顶部导航
   - `分析工作台`
   - `筛选工作台`

2. 左侧：批次选择区
   - 历史 batch 列表
   - 选择一个批次进入筛图

3. 中间：筛选控制区
   - 自然语言输入框
   - “生成筛选方案”
   - “执行筛选”
   - “下载保留结果”

4. 右侧或下方：结果展示区
   - 全部
   - 保留
   - 移除

### 11.2 页面交互

推荐流程：

1. 选择一个 batch
2. 输入自然语言
3. 点击“生成筛选方案”
4. 查看 Agent 解析出来的筛选解释
5. 点击“执行筛选”
6. 查看保留/移除图片
7. 下载保留图片

### 11.3 页面状态

需要明确区分：

1. `分析中`
2. `筛选规划中`
3. `Agent 思考中`
4. `执行筛选中`
5. `导出中`

---

## 12. 推荐 API 设计

建议新增路由前缀：

`/filtering`

### 12.1 生成筛选计划

`POST /filtering/batches/{batch_id}/plan`

请求：

```json
{
  "query": "去掉模糊和高噪声的，只保留质量高的图片"
}
```

响应：

```json
{
  "dsl": { "...": "..." },
  "explanation": "将移除清晰度低于 60、噪声评分低于 55，以及综合质量低于 65 的图片。",
  "tool_trace": [
    "list_batch_items",
    "compute_blur_metrics: ul_1"
  ]
}
```

### 12.2 执行筛选

`POST /filtering/batches/{batch_id}/run`

请求：

```json
{
  "dsl": { "...": "..." }
}
```

响应：

```json
{
  "summary": {
    "total": 20,
    "kept": 12,
    "removed": 8
  },
  "kept": [...],
  "removed": [...]
}
```

### 12.3 导出结果

`POST /filtering/batches/{batch_id}/export`

请求：

```json
{
  "kept_upload_ids": ["ul_1", "ul_2", "ul_7"]
}
```

响应：

- ZIP 文件流，或下载链接

---

## 13. 为什么这比“让大模型直接挑图”更合理

不建议让大模型直接返回：

- 保留第 1、5、8 张
- 删除第 2、3、4 张

原因：

1. 不可解释
2. 不稳定
3. 难以复现
4. 不利于调试和论文描述

更合理的方案是：

1. Agent 负责理解自然语言与组织决策
2. Tools 提供确定性证据
3. DSL 承担可执行规则表达
4. Executor 负责真正筛选

这个结构的优点是：

1. 可解释
2. 可复现
3. 易调试
4. 易扩展
5. 更符合真实 agent 架构

---

## 14. 与当前系统的关系

这个新模块应当复用当前已有结果，而不是重复计算。

可直接复用：

1. `history batch`
2. `quality_fusion`
3. `quality_judge`
4. `semantic`
5. `uploads` 文件与缩略图

需要新增的部分主要是：

1. 筛选 Agent
2. 筛选 DSL
3. 执行器
4. 导出 ZIP
5. 新页面

因此这是一个：

> 基于现有分析系统向上加建的独立筛选模块

不是推倒重来。

---

## 15. 第一阶段可实现范围（推荐 MVP）

建议先做最稳的一版：

### 第一阶段必须完成

1. 新页面 `FilterStudio`
2. 选择历史 batch
3. 自然语言输入
4. Agent 生成 DSL
5. 规则执行
6. 保留/移除结果展示
7. 下载保留图片 ZIP

### 第一阶段 low-level tools

先开放三个：

1. `compute_blur_metrics`
2. `compute_noise_metrics`
3. `compute_exposure_metrics`

这三项最适合自然语言筛选场景，也与你当前系统最相关。

### 第一阶段不必做

1. 多轮对话式筛选
2. Agent 自动改写 prompt
3. 复杂语义排序
4. 多 batch 联合筛选

---

## 16. 第二阶段扩展方向

在第一阶段稳定后，可以继续扩展：

1. `Top-K` 最优筛选
   - 只保留最清晰的前 5 张

2. 语义条件筛选
   - 只保留室外、人物少、适合展示的图片

3. patch 级复查工具
   - 让 Agent 对边界图进行局部细查

4. 批量理由生成
   - 每张图输出更细粒度移除原因

5. 人机协同筛选
   - 用户手工调整保留/移除结果后再导出

---

## 17. 论文中的表述方式

这一模块可以写成：

> 本文在基础图像分析工作台之外，进一步设计了一个自然语言图像筛选模块。该模块采用 Agent 架构，将工作流知识封装为筛选 skill，将 low-level 质量计算与批次结果读取封装为可调用 tools。筛选 Agent 首先理解用户的自然语言筛选需求，并在必要时自主调用 blur、noise 与 exposure 等底层分析工具，以生成结构化筛选规则。随后由确定性规则执行器完成批量筛选，并输出可解释的保留/移除结果与下载包。该设计兼顾了自然语言交互能力、可解释性与工程可控性。

如果需要英文描述，可写为：

> We further design a natural-language image filtering module as an independent component on top of the existing analysis platform. In this module, workflow knowledge is encapsulated as an agent skill, while low-level quality computations and batch result retrieval are exposed as callable tools. The filtering agent interprets user queries, autonomously invokes blur/noise/exposure tools when additional evidence is needed, produces a structured filtering DSL, and then hands the execution to a deterministic rule engine. This design improves usability while preserving interpretability and execution reliability.

---

## 18. 参考资料

1. OpenAI Agents SDK  
   https://developers.openai.com/api/docs/guides/agents-sdk

2. Anthropic Tool Use  
   https://platform.claude.com/docs/en/agents-and-tools/tool-use/implement-tool-use

3. Anthropic Advanced Tool Use  
   https://www.anthropic.com/engineering/advanced-tool-use

4. Anthropic Skills Guide  
   https://resources.anthropic.com/hubfs/The-Complete-Guide-to-Building-Skill-for-Claude.pdf

---

## 19. 当前设计结论

本项目后续应采用以下原则：

1. 筛图模块独立于现有分析页
2. 页面拆分为 `分析工作台` 和 `筛选工作台`
3. `skill` 负责工作流知识
4. `tool` 负责确定性执行能力
5. low-level blur/noise/exposure 计算应作为 Agent 可调用 tools
6. 是否调用这些 tools 由 Agent 自主决定，系统只提供预算与边界
7. 筛选结果必须通过 DSL + 规则执行器落地
8. 最终输出应支持保留/移除展示与 ZIP 导出
