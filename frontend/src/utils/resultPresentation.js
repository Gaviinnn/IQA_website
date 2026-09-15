export const LABEL_MAP = {
  low: '低',
  medium: '中',
  high: '高',
  normal: '正常',
  underexposed: '欠曝',
  overexposed: '过曝',
  indoor: '室内',
  outdoor: '室外',
  landscape: '风景',
  portrait: '人像',
  food: '食物',
  document: '文档',
  urban: '城市场景',
  nature: '自然场景',
  product: '商品',
  other: '其他',
};

export const labelValue = (value) => LABEL_MAP[value] || value || '--';

const hasNumericScore = (value) => typeof value === 'number' && !Number.isNaN(value);

export const getJudgeFactorScores = (result) => ({
  sharpness: result?.quality_judge?.sharpness_score,
  noise: result?.quality_judge?.noise_score,
  exposure: result?.quality_judge?.exposure_score,
  contrast: result?.quality_judge?.contrast_score,
  compression: result?.quality_judge?.compression_score,
});

export const getJudgeIssueTags = (result) => {
  const judge = result?.quality_judge;
  if (!judge) return [];

  const tags = [];
  const scores = getJudgeFactorScores(result);
  if (hasNumericScore(scores.sharpness) && scores.sharpness < 60) {
    tags.push('模糊明显');
  }
  if (hasNumericScore(scores.noise) && scores.noise < 60) {
    tags.push('噪声偏高');
  }
  if (hasNumericScore(scores.exposure) && scores.exposure < 65) {
    tags.push('曝光异常');
  }
  if (hasNumericScore(scores.contrast) && scores.contrast < 65) {
    tags.push('对比度不足');
  }
  if (hasNumericScore(scores.compression) && scores.compression < 60) {
    tags.push('压缩明显');
  }

  if (!tags.length && Array.isArray(judge.key_issues)) {
    return judge.key_issues.slice(0, 4);
  }
  return tags.slice(0, 4);
};

export const getResultScore = (result) => {
  const score = result?.quality_fusion?.final_score ?? result?.quality?.score;
  return typeof score === 'number' ? score : null;
};

export const getResultElapsedMs = (result) => result?.meta?.elapsed_ms ?? result?.meta?.inference_ms ?? null;

export const formatElapsed = (elapsedMs) => {
  if (typeof elapsedMs !== 'number' || Number.isNaN(elapsedMs)) {
    return '--';
  }
  if (elapsedMs >= 1000) {
    return `${(elapsedMs / 1000).toFixed(1)} s`;
  }
  return `${elapsedMs} ms`;
};

export const formatTimestamp = (value) => {
  if (!value) return '';
  try {
    return new Date(value).toLocaleString();
  } catch {
    return value;
  }
};

export const hasSemanticIssue = (result) => {
  const semanticStatus = result?.meta?.skill_status?.semantic;
  return semanticStatus && semanticStatus !== 'ok';
};

export const getQualityBucket = (result) => {
  const score = getResultScore(result);
  if (score == null) return 'unknown';
  if (score < 60) return 'low';
  if (score < 80) return 'medium';
  return 'high';
};

export const getPrimaryTags = (result) => {
  const tags = [];
  const judgeTags = getJudgeIssueTags(result);
  const semantic = result?.semantic;

  tags.push(...judgeTags);

  if (semantic?.scene) {
    tags.push(labelValue(semantic.scene));
  }
  if (semantic?.complexity) {
    tags.push(`复杂度${labelValue(semantic.complexity)}`);
  }

  if (!tags.length && result?.quality?.level) {
    tags.push(result.quality.level);
  }

  return tags.slice(0, 4);
};

export const getResultSummary = (result) =>
  result?.quality_fusion?.reason ||
  result?.quality_judge?.reason ||
  result?.diagnostics?.summary ||
  result?.content?.caption ||
  result?.quality?.explanation ||
  '暂无摘要';

export const SCREENING_RULES = [
  {
    id: 'quality_lt_50',
    label: '低质量图片',
    description: '综合得分低于 50，适合用于数据集清洗。',
    emptyText: '未检测到低质量图片',
  },
  {
    id: 'blur_issue',
    label: '模糊图片',
    description: '基于 LLM 质量审阅中的清晰度评分，快速找出失焦样本。',
    emptyText: '未检测到明显模糊图片',
  },
  {
    id: 'noise_issue',
    label: '高噪声图片',
    description: '基于 LLM 质量审阅中的噪声评分，适合筛出高 ISO 或压缩劣化样本。',
    emptyText: '未检测到高噪声图片',
  },
  {
    id: 'exposure_issue',
    label: '曝光异常',
    description: '基于 LLM 质量审阅中的曝光评分，适合相册整理和采集质检。',
    emptyText: '未检测到曝光异常图片',
  },
];

export const matchesScreeningRule = (result, ruleId) => {
  const score = getResultScore(result);
  const factorScores = getJudgeFactorScores(result);

  if (ruleId === 'quality_lt_50') {
    return typeof score === 'number' && score < 50;
  }
  if (ruleId === 'blur_issue') {
    return hasNumericScore(factorScores.sharpness) && factorScores.sharpness < 60;
  }
  if (ruleId === 'noise_issue') {
    return hasNumericScore(factorScores.noise) && factorScores.noise < 60;
  }
  if (ruleId === 'exposure_issue') {
    return hasNumericScore(factorScores.exposure) && factorScores.exposure < 65;
  }
  return true;
};

export const countScreeningMatches = (results = [], ruleId) =>
  results.filter((result) => matchesScreeningRule(result, ruleId)).length;
