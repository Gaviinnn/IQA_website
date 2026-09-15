# 图像质量融合评分设计说明

## 1. 设计背景

当前系统使用 `MANIQA` 作为无参考图像质量评估（NR-IQA）的核心模型，能够输出单张图像的综合质量分数。然而，在真实应用场景中，单一 NR-IQA 模型的输出并不能完全等价于人类主观感知质量，原因主要有三点：

1. `MOS`（Mean Opinion Score）本质上来源于人类观察者对整体视觉质量的主观评分，而不是某个单一失真指标的直接映射。
2. 真实场景图像通常包含混合失真，例如模糊、噪声、曝光异常和压缩伪影同时出现，而不是单一可控失真。
3. 现有 NR-IQA 模型虽然对主观评分具有较强预测能力，但在跨内容、跨拍摄条件和跨失真类型时仍然存在稳定性问题。

因此，本系统将 `MANIQA` 视为“基础感知质量信号”，并进一步结合可解释的技术质量指标与大模型质量审阅结果，构建一个更符合主观评价逻辑的融合质量评分模块。

## 2. 主观质量评价（MOS）主要关注的内容

### 2.1 MOS 的基本含义

根据 `ITU-R BT.500-15`，主观图像质量评估的核心是让观察者对图像的整体视觉质量进行评分，常见形式包括等级评分、成对比较、双刺激比较等。该标准定义了评价流程和实验方法，但**并没有规定一个统一的“失真因素权重表”**。这意味着：

- `MOS` 是“整体感知质量”的结果；
- 各类质量因素的重要性通常需要结合具体图像类型、失真类型和应用目标来建模；
- 工程系统中的融合权重更适合采用“文献证据 + 数据校准”的方式设定，而不是声称存在唯一标准答案。

### 2.2 真实图像质量数据库揭示的主要失真因素

`LIVE In the Wild Image Quality Challenge Database` 强调，真实世界照片常包含多种混合失真，典型例子包括：

- 运动模糊或失焦模糊；
- 低照度噪声；
- 过曝或欠曝；
- 压缩误差。

这说明在真实图像质量判断中，人类主观评分并非只受某一个失真主导，而是受到多个技术质量因素共同影响。

`KonIQ-10k` 则进一步说明，面向真实场景图像的质量数据库需要同时保证内容多样性、失真真实性以及主观评分可靠性。该数据库的构建目标本身就说明：**真实图像质量预测必须考虑复杂、自然、混合型失真，而不能仅依赖理想化失真样本上的单一模型表现。**

### 2.3 图像感知质量研究中的关键属性

`Choi et al. (2008)` 从心理物理实验角度分析了影响感知图像质量的重要属性，结果表明：

- `contrast`、`naturalness`、`colorfulness` 是重要的感知属性；
- `sharpness` 与 `contrast` 存在较强相关性，不宜简单重复计入；
- 单一属性不足以完整解释图像质量，通常需要多个属性共同建模。

对本系统而言，这一结论的启发是：

1. 图像质量不应只由一个总分决定；
2. 清晰度（sharpness/blur）和对比度都重要，但存在耦合关系；
3. 融合模块应优先选择“与主观质量高度相关且当前系统可稳定计算”的指标。

## 3. 为什么本阶段融合只采用“质量相关因素”

本项目当前已经具备三类信息：

1. `MANIQA` 给出的整体感知质量分；
2. 基于 low-level feature 启发式图像诊断得到的技术质量指标：
   - blur
   - noise
   - exposure
   - contrast
   - compression artifacts
3. 基于多模态大模型的质量审阅结果，用于模拟类人工质量评审。

虽然系统也具备语义分析能力，但本阶段的质量融合模块**不引入语义因素**，理由如下：

1. 本阶段目标是提升“图像本身技术质量”的评价稳定性，而不是评价内容是否复杂、丰富或有意义。
2. 语义复杂度、场景类别等因素更适合作为后续“任务可用性”或“内容可读性”分析的辅助维度，而不是直接作为图像质量分数的主因。
3. 若在尚未建立充分实验依据时直接引入语义修正，容易导致“复杂场景天然低分”这类解释风险，不利于论文中的方法论严谨性。

因此，当前融合模块定位为：

> 以 `MANIQA` 为基础感知分，以基于 low-level features 的技术质量诊断项为显式证据，以多模态大模型质量审阅为类人工复核，形成可解释的综合质量评分。

## 4. 融合模块采用的质量维度

结合主观质量评测文献和当前系统的可实现性，第一阶段融合采用以下五个技术质量因素：

1. `Blur / Sharpness`
2. `Noise`
3. `Exposure`
4. `Contrast`
5. `Compression Artifacts`

选择理由如下：

- `Blur`：真实图像中最常见、最直接影响清晰度和可辨性的失真之一；
- `Noise`：在低照度、传感器增益较高或压缩退化时明显降低主观质量；
- `Exposure`：过曝和欠曝会直接破坏图像可视信息；
- `Contrast`：与视觉细节、层次和感知清晰度密切相关；
- `Compression Artifacts`：虽然通常不如模糊和曝光显著，但在低质量编码图像中会明显影响观感。

## 5. 当前技术质量子分的实现方式

### 5.1 low-level feature 诊断模块

当前系统中的 `technical` 并不是由大模型直接给出的主观分数，而是由启发式技术质量诊断模块生成。该模块直接从图像像素中提取 low-level perceptual features，并用阈值规则对质量因子进行分级判断。

可概括为：

- `blur`：采用局部梯度锐度估计。先计算 Sobel 梯度幅值，再按 patch 聚合局部 sharpness，以中位数与低分位数联合刻画整体清晰度与局部失焦程度；
- `noise`：采用平坦区域噪声估计。先在低纹理 patch 中提取高频残差，再使用 MAD（median absolute deviation）估计噪声强度，避免将纹理误识别为噪声；
- `exposure`：采用亮度均值与高光/阴影裁剪比例联合估计曝光状态，而不是仅使用全局平均亮度；
- `contrast`：采用全局标准差与局部对比度中位数联合估计对比度，降低单一统计量的偏差；
- `compression artifacts`：采用 8x8 block boundary 与非边界区域的梯度差异构造 blockiness 指标，近似估计 JPEG 类块状伪影。

因此，当前技术质量诊断模块本质上属于：

> low-level feature based heuristic diagnostic module

其优点是：

1. 计算代价低，适合在线系统；
2. 可解释性强，每个因子都有对应统计特征；
3. 不依赖额外训练数据，易于工程部署。

其局限是：

1. 对复杂真实混合失真不够鲁棒；
2. 阈值依赖较强；
3. 与主观视觉感受之间仍然存在偏差。

### 5.2 技术质量因子到分数的映射

当前系统不是简单把等级直接映射成固定分数，而是采用“两步评分”：

1. 先基于 low-level metrics 为每个因子生成一个保守的 `0-100` 子分；
2. 再结合等级规则对严重问题追加惩罚与上限约束。

其设计意图是避免“少数正常项抵消严重缺陷”，即：

- 当 `blur`、`noise`、`compression artifacts` 出现中高等级问题时，技术质量分会被明显压低；
- 当多个严重问题同时出现时，会触发额外 penalty；
- 当出现关键短板时，会对 `technical_score` 设置上限，使得总分不再是单纯的补偿型平均。

因此，当前 `technical_score` 更接近“短板约束下的技术质量健康度”，而不是普通加权平均值。

## 6. 权重设定原则

### 6.1 权重设定不是“标准答案”

如前所述，主观评价标准并未给出统一的失真权重。因此，本项目的权重设定遵循以下原则：

1. 优先考虑主观质量研究中反复出现的重要因素；
2. 优先考虑真实图像数据库中高频出现的失真类型；
3. 避免对高度相关的指标重复赋予过高权重；
4. 保持公式简单、可解释、便于后续实验校准。

### 6.2 技术质量子分权重

结合 `LIVE Challenge`、`KonIQ-10k` 以及 `Choi et al. (2008)` 的结论，第一阶段建议采用如下技术质量权重：

| 因子 | 权重 | 设计理由 |
|---|---:|---|
| Blur | 0.32 | 模糊对主观质量影响最直接，且在真实拍摄中极其常见 |
| Noise | 0.22 | 低照度噪声和高 ISO 噪声是自然图像中常见退化 |
| Exposure | 0.19 | 欠曝/过曝会显著损害有效视觉信息 |
| Contrast | 0.17 | 与感知清晰度和图像层次密切相关，但需避免与 blur 双重放大 |
| Compression | 0.10 | 重要但通常不应压过 blur、noise 和 exposure |

这些权重总和为 `1.00`，用于构造技术质量子分 `technical_score`。

## 7. 与 MANIQA 和 LLM Judge 的融合方式

### 7.1 设计思路

当前系统不再采用“仅由 MANIQA 与 technical 两路融合”的方案，而是采用三路融合：

- `MANIQA score`：整体感知质量基线；
- `technical score`：基于 low-level feature 诊断与规则映射得到的技术质量子分；
- `LLM judge score`：基于多模态大模型的结构化质量审阅得分。

这样设计的原因是：

1. 其输出是“主观质量预测”，不是绝对真值；
2. 纯规则的 technical score 虽然可解释，但对严重失真和整体视觉观感的刻画仍不充分；
3. 大模型质量审阅能够提供更接近人工主观判断的复核信号，但单独使用时稳定性仍不如规则证据；
4. 三路融合能同时兼顾稳定性、可解释性和主观感知一致性。

### 7.2 当前实现中的融合公式

当前系统实际使用如下公式：

```text
final_score
= 0.45 * maniqa_score
+ 0.25 * technical_score
+ 0.30 * llm_judge_score
```

其中：

```text
technical_base
= 0.32 * blur_score
+ 0.22 * noise_score
+ 0.19 * exposure_score
+ 0.17 * contrast_score
+ 0.10 * compression_score

technical_score
= min(technical_base - severe_penalties, shortboard_caps)
```

此处 `blur_score`、`noise_score`、`exposure_score`、`contrast_score`、`compression_score` 均映射到 `0-100` 区间，`severe_penalties` 与 `shortboard_caps` 用于抑制严重模糊、强噪声和高压缩伪影导致的乐观评分偏差。

这样设计的好处是：

1. `MANIQA` 保留为整体感知评分来源；
2. `technical score` 提供可解释的客观技术证据；
3. `LLM judge score` 提供类人工主观复核；
4. 最终分数既不完全依赖黑盒模型，也不完全依赖固定阈值规则。

## 8. 论文中可采用的表述方式

下面这段表述可以直接作为论文方法章节的基础版本：

> 为降低单一无参考图像质量评估模型在真实复杂失真场景下的偏差，本文设计了一种基于感知基线、技术证据与大模型审阅相结合的图像质量融合评分方法。该方法以 MANIQA 输出作为基础感知质量分，同时引入由 low-level feature 诊断模块生成的技术质量子分，并进一步利用多模态大模型进行结构化质量审阅。最终质量分由三路信号加权融合得到。该设计兼顾了主观质量预测能力、技术可解释性与类人工审阅能力，能够更稳定地反映真实场景图像的综合质量水平。

如果需要更正式一点的版本，可以写为：

> Considering that Mean Opinion Score (MOS) reflects holistic human perception rather than a single distortion factor, this work does not directly treat the output of a no-reference IQA model as the final quality label. Instead, a quality fusion module is introduced, where the MANIQA prediction serves as a perceptual prior, a technical quality sub-score is constructed from low-level blur, noise, exposure, contrast, and compression diagnostics, and a multimodal LLM-based judge provides a structured quality review. The final quality score is obtained through weighted fusion, improving both interpretability and robustness in authentic distortion scenarios.

## 9. 当前方案的边界与后续工作

本方案仍然属于“文献驱动 + 工程实现”的融合框架，而不是经过大规模标注数据回归拟合得到的最优权重模型。因此在论文中建议明确说明：

1. 本阶段权重为 literature-informed initial weights；
2. 当前 technical 模块仍基于 low-level heuristic features，后续可进一步用学习式失真预测模型替换；
3. 后续可基于自建数据集或人工标注样本进行参数校准；
4. 若未来补充颜色、自然感或任务可用性指标，可在本方案基础上进一步扩展。

## 10. 参考资料

1. ITU-R BT.500-15, *Methodologies for the subjective assessment of the quality of television images*  
   https://www.itu.int/rec/R-REC-BT.500-15-202305-I

2. Ghadiyaram, D., Bovik, A. C. (2016), *Massive Online Crowdsourced Study of Subjective and Objective Picture Quality*  
   https://live.ece.utexas.edu/publications/2016/ghadiyaram2016massive.pdf

3. Hosu, V., Lin, H., Sziranyi, T., Saupe, D. (2019), *KonIQ-10k: An ecologically valid database for deep learning of blind image quality assessment*  
   https://arxiv.org/abs/1910.06180

4. Choi, S., Pointer, M. R., Rhodes, P. A., Luo, M. R. (2008), *Investigation of Large Display Color Image Appearance I: Important Factors Affecting Perceived Quality*  
   https://library.imaging.org/admin/apis/public/api/ist/website/downloadArticle/jist/52/4/art00007

5. Golestaneh, S. A., Karam, L. J. (2017), *Spatially-Varying Blur Detection Based on Multiscale Fused and Sorted Transform Coefficients of Gradient Magnitudes*  
   https://openaccess.thecvf.com/content_cvpr_2017/html/Golestaneh_Spatially-Varying_Blur_Detection_CVPR_2017_paper.html

6. Colom, M., Buades, A. (2013), *Analysis of a Noise Estimation Method Based on Local Statistics*  
   https://www.ipol.im/pub/art/2013/45/

7. Wang, Z., Bovik, A. C., Evans, B. L. (2000), *Blind Measurement of Blocking Artifacts in Images*  
   https://ece.uwaterloo.ca/~z70wang/publications/blocking.pdf
