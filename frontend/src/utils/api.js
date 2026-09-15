import axios from 'axios';

export const API_BASE_URL = import.meta.env.VITE_API_BASE_URL || 'http://127.0.0.1:8000';
const USE_MOCK = import.meta.env.VITE_USE_API_MOCK === 'true';

const http = axios.create({
  baseURL: API_BASE_URL,
  timeout: 60000,
  headers: {
    'Content-Type': 'application/json',
  },
});

export const resolveAssetUrl = (path) => {
  if (!path) return path;
  if (/^https?:\/\//i.test(path)) {
    return path;
  }
  const base = API_BASE_URL.replace(/\/$/, '');
  const normalized = path.startsWith('/') ? path : `/${path}`;
  return `${base}${normalized}`;
};

export const uploadImages = async (files, onUploadProgress) => {
  if (!files?.length) {
    throw new Error('未选择有效文件');
  }

  if (USE_MOCK) {
    return new Promise((resolve) => {
      setTimeout(() => {
        const uploads = files.map((file, index) => ({
          upload_id: `ul_mock_${Date.now()}_${index}`,
          filename: file.name,
          mime: file.type,
          size_kb: Math.round((file.size / 1024) * 10) / 10,
          width: 1024,
          height: 768,
          thumbnail: '/uploads/mock_thumb.jpg',
          timestamp: new Date().toISOString(),
        }));
        resolve({ data: { uploads } });
      }, 400);
    });
  }

  const formData = new FormData();
  files.forEach((file) => {
    formData.append('files', file);
  });

  return http.post('/upload', formData, {
    headers: { 'Content-Type': 'multipart/form-data' },
    onUploadProgress,
  });
};

export const analyzeImages = async ({ uploadIds, detail = 'low', model, prompt, skills } = {}) => {
  if (USE_MOCK) {
    return new Promise((resolve) => {
      setTimeout(() => {
        const results = (uploadIds || ['mock']).map((id, index) => ({
          upload_id: id,
          filename: `mock_${index + 1}.jpg`,
            quality: {
              score: 82.4,
              level: '良好',
              explanation: '图像结构完整，细节保留较好，存在轻微噪点。',
            },
            quality_evidence: {
              base_maniqa_score: 82.4,
              technical_score: 79.5,
              factor_scores: {
                blur: 88,
                noise: 76,
                exposure: 90,
                contrast: 82,
                compression: 91,
              },
              summary: 'MANIQA 基础分 82.4，技术质量子分 79.5，主要关注：噪声medium。',
            },
            quality_judge: {
              sharpness_score: 86,
              noise_score: 74,
              exposure_score: 90,
              contrast_score: 82,
              compression_score: 90,
              overall_quality_score: 81,
              confidence: 84,
              level: '良好',
              evidence_alignment: 'aligned',
              reason: '画面整体清晰，细节保持较好，但存在轻微噪点。',
              key_issues: ['轻微噪声'],
            },
            quality_fusion: {
              base_score: 82.4,
              technical_score: 79.5,
              judge_score: 81,
              final_score: 81.17,
              level: '良好',
              confidence: 'high',
              weights: { maniqa: 0.45, technical: 0.25, judge: 0.3 },
              judge_alignment: 'aligned',
              judge_confidence: 84,
              reason: '融合 MANIQA、技术证据与 LLM 审阅后，图像质量等级为良好。',
              key_issues: ['轻微噪声'],
            },
            diagnostics: {
              blur: 'low',
              noise: 'low',
              exposure: 'normal',
            contrast: 'normal',
            compression_artifacts: 'low',
            summary: '未检测到明显质量缺陷。',
            metrics: {
              blur_score: 0.0061,
              brightness_mean: 0.52,
              contrast_std: 0.18,
              noise_score: 0.011,
              compression_score: 0.003,
            },
          },
          content: {
            caption: '一只在沙滩奔跑的狗，背景是晴朗天空。',
            objects: [
              { label: 'dog', score: 0.98 },
              { label: 'beach', score: 0.87 },
            ],
          },
          semantic: {
            scene: 'landscape',
            object_count: 3,
            complexity: 'medium',
            scene_clutter: 'low',
            semantic_tags: ['海滩', '宠物', '户外'],
          },
          meta: {
            models: {
              quality: 'MANIQA v1.2',
              diagnostics: 'Heuristic Diagnostic Analyzer v1',
              quality_evidence: 'Quality Evidence Builder v1',
              quality_judge: 'Qwen-VL Reviewer',
              quality_fusion: 'Quality Fusion Engine v1',
              content: 'Doubao-Seed-1.6-Vision',
              semantic: 'Doubao-Seed-1.6-Vision',
            },
            detail,
            elapsed_ms: 1320,
            degraded: false,
            request_id: `mock_${Date.now()}`,
            skill_order: skills || ['quality_fusion', 'semantic'],
            skill_status: {
              quality: 'ok',
              diagnostics: 'ok',
              quality_evidence: 'ok',
              quality_judge: 'ok',
              quality_fusion: 'ok',
              semantic: 'ok',
            },
          },
          snapshot: {
            image: resolveAssetUrl('/uploads/mock.jpg'),
            thumbnail: resolveAssetUrl('/uploads/mock_thumb.jpg'),
            saved_at: new Date().toISOString(),
          },
        }));
        resolve({ data: { results } });
      }, 600);
    });
  }

  return http.post('/analyze', {
    upload_ids: uploadIds,
    detail,
    model,
    prompt,
    skills,
  });
};

export const fetchHistory = async (params = {}) => {
  if (USE_MOCK) {
    return {
      data: {
        history: [
          {
            batch_id: 'bat_mock_1',
            filename: 'demo_1.jpg / demo_2.jpg',
            avg_score: 88.6,
            min_score: 84.2,
            max_score: 92.8,
            item_count: 2,
            caption: '示例图像描述',
            thumbnail: resolveAssetUrl('/uploads/mock_thumb.jpg'),
            image: resolveAssetUrl('/uploads/mock.jpg'),
            degraded: false,
            timestamp: new Date().toISOString(),
          },
        ],
        next_cursor: null,
      },
    };
  }

  return http.get('/history', { params });
};

export const fetchHistoryBatch = async (batchId) => {
  if (USE_MOCK) {
    return {
      data: {
        batch: {
          batch_id: batchId,
          timestamp: new Date().toISOString(),
          item_count: 2,
          avg_score: 88.6,
          items: [
            {
              upload_id: 'mock_history_item_1',
              batch_id: batchId,
              filename: 'demo_1.jpg',
              score: 92.8,
              caption: '示例图像一',
              objects: ['树木', '建筑'],
              thumbnail: resolveAssetUrl('/uploads/mock_thumb.jpg'),
              image: resolveAssetUrl('/uploads/mock.jpg'),
              timestamp: new Date().toISOString(),
              result: null,
            },
          ],
        },
      },
    };
  }
  return http.get(`/history/${batchId}`);
};

export const planFilterBatch = async ({ batchId, query, model, providerProfileId } = {}) => {
  if (!batchId || !query) {
    throw new Error('batchId 和 query 不能为空');
  }
  if (USE_MOCK) {
    return {
      data: {
        batch_id: batchId,
        query,
        dsl: {
          mode: 'keep_matching',
          logic: 'and',
          rules: [
            { field: 'quality_judge.sharpness_score', op: '>=', value: 60 },
            { field: 'quality_judge.noise_score', op: '>=', value: 60 },
          ],
          sort: { field: 'quality_fusion.final_score', direction: 'desc' },
          limit: null,
        },
        explanation: '将保留清晰度评分和噪声评分均不低于 60 的图片。',
        tool_trace: [],
        mode: 'mock',
      },
    };
  }
  return http.post(`/filtering/batches/${batchId}/plan`, {
    query,
    model,
    provider_profile_id: providerProfileId,
  });
};

export const runFilterBatch = async ({ batchId, dsl } = {}) => {
  if (!batchId) {
    throw new Error('batchId 不能为空');
  }
  if (USE_MOCK) {
    const batch = await fetchHistoryBatch(batchId);
    const items = (batch.data?.batch?.items || []).map((item) => ({
      upload_id: item.upload_id,
      filename: item.filename,
      score: item.score,
      thumbnail: item.thumbnail,
      image: item.image,
      reason: '符合筛选条件',
      matched_rules: ['清晰度评分 >= 60'],
      unmet_rules: [],
      result: item.result || item,
    }));
    return {
      data: {
        batch_id: batchId,
        dsl,
        summary: {
          total: items.length,
          kept: items.length,
          removed: 0,
        },
        kept: items,
        removed: [],
      },
    };
  }
  return http.post(`/filtering/batches/${batchId}/run`, { dsl });
};

export const chatFilterBatch = async ({ batchId, messages, activeUploadIds, model, providerProfileId } = {}) => {
  if (!batchId || !messages?.length) {
    throw new Error('batchId 和 messages 不能为空');
  }
  if (USE_MOCK) {
    const batch = await fetchHistoryBatch(batchId);
    const items = (batch.data?.batch?.items || []).map((item) => ({
      upload_id: item.upload_id,
      filename: item.filename,
      score: item.score,
      thumbnail: item.thumbnail,
      image: item.image,
      reason: '符合筛选条件',
      matched_rules: ['清晰度评分 >= 60'],
      unmet_rules: [],
      result: item.result || item,
    }));
    return {
      data: {
        batch_id: batchId,
        query: messages[messages.length - 1]?.content || '',
        assistant_message: `已根据你的描述完成筛选。本轮共检查 ${items.length} 张图片，保留 ${items.length} 张，移除 0 张。`,
        did_execute: true,
        turn: {
          batch_id: batchId,
          query: messages[messages.length - 1]?.content || '',
          dsl: {
            mode: 'keep_matching',
            logic: 'and',
            rules: [{ field: 'quality_judge.sharpness_score', op: '>=', value: 60 }],
            sort: { field: 'quality_fusion.final_score', direction: 'desc' },
            limit: null,
          },
          explanation: '保留清晰度评分不低于 60 的图片',
          tool_trace: [],
          mode: 'mock',
        },
        result: {
          batch_id: batchId,
          summary: {
            total: items.length,
            kept: items.length,
            removed: 0,
          },
          kept: items,
          removed: [],
        },
      },
    };
  }
  return http.post(`/filtering/batches/${batchId}/chat`, {
    messages,
    active_upload_ids: activeUploadIds || [],
    model,
    provider_profile_id: providerProfileId,
  });
};

export const exportFilterBatch = async ({ batchId, keptUploadIds, filename } = {}) => {
  if (!batchId || !keptUploadIds?.length) {
    throw new Error('batchId 和 keptUploadIds 不能为空');
  }
  if (USE_MOCK) {
    return new Blob(['mock zip content'], { type: 'application/zip' });
  }
  return http.post(
    `/filtering/batches/${batchId}/export`,
    { kept_upload_ids: keptUploadIds, filename },
    { responseType: 'blob' }
  );
};

export const deleteHistoryItem = async (batchId) => {
  if (USE_MOCK) {
    return { data: { deleted: true } };
  }
  return http.delete('/delete', { data: { batch_id: batchId } });
};

export const clearHistory = async () => {
  if (USE_MOCK) {
    return { data: { cleared: true } };
  }
  return http.delete('/history');
};

export const healthCheck = () => http.get('/health');

export const fetchSkills = async () => {
  if (USE_MOCK) {
    return {
      data: {
        skills: [
          { id: 'quality', description: 'MANIQA quality scoring' },
          { id: 'diagnostics', description: 'Blur, noise, exposure, and compression diagnostics' },
          { id: 'semantic', description: 'Caption, objects, scene classification, and complexity' },
        ],
      },
    };
  }
  return http.get('/skills');
};

export const fetchProviderPresets = async () => {
  if (USE_MOCK) {
    return {
      data: {
        presets: [
          {
            id: 'openai',
            label: 'OpenAI',
            protocol: 'openai_compatible',
            default_base_url: 'https://api.openai.com/v1',
            default_model: 'gpt-4.1-mini',
          },
          {
            id: 'qwen',
            label: 'Alibaba Qwen',
            protocol: 'openai_compatible',
            default_base_url: 'https://dashscope.aliyuncs.com/compatible-mode/v1',
            default_model: 'qwen-plus',
          },
        ],
      },
    };
  }
  return http.get('/providers/presets');
};

export const fetchProviderProfiles = async () => {
  if (USE_MOCK) {
    return {
      data: {
        profiles: [],
        active_profile_id: null,
      },
    };
  }
  return http.get('/providers/profiles');
};

export const fetchActiveProviderProfile = async () => {
  if (USE_MOCK) {
    return { data: { profile: null } };
  }
  return http.get('/providers/active');
};

export const saveProviderProfile = async (payload) => {
  if (USE_MOCK) {
    return { data: { profile: { ...payload, profile_id: payload.profile_id || `prf_${Date.now()}` } } };
  }
  return http.post('/providers/profiles', payload);
};

export const activateProviderProfile = async (profileId) => {
  if (USE_MOCK) {
    return { data: { profile: { profile_id: profileId, is_active: true } } };
  }
  return http.post('/providers/profiles/activate', { profile_id: profileId });
};

export const deleteProviderProfile = async (profileId) => {
  if (USE_MOCK) {
    return { data: { deleted: true } };
  }
  return http.delete(`/providers/profiles/${profileId}`);
};

export const testProviderProfile = async (profileId) => {
  if (USE_MOCK) {
    return { data: { ok: true, detail: 'mock provider connection ok' } };
  }
  return http.post('/providers/test', { profile_id: profileId });
};
