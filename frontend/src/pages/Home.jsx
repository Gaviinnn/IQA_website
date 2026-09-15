import { useCallback, useEffect, useMemo, useState } from 'react';
import UploadBox from '../components/UploadBox.jsx';
import ProviderPanel from '../components/ProviderPanel.jsx';
import ProgressBar from '../components/ProgressBar.jsx';
import ResultsWorkspace from '../components/ResultsWorkspace.jsx';
import ResultCard from '../components/ResultCard.jsx';
import Sidebar from '../components/Sidebar.jsx';
import {
  activateProviderProfile,
  analyzeImages,
  deleteHistoryItem,
  deleteProviderProfile,
  fetchActiveProviderProfile,
  fetchHistoryBatch,
  fetchHistory,
  fetchProviderPresets,
  fetchProviderProfiles,
  fetchSkills,
  saveProviderProfile,
  testProviderProfile,
  uploadImages,
  resolveAssetUrl,
  clearHistory,
} from '../utils/api.js';
import { clearHistoryCache, loadHistoryCache, saveHistoryCache } from '../utils/storage.js';

const DEFAULT_DETAIL = 'low';
const DEFAULT_SKILL_SELECTION = ['quality_fusion', 'semantic'];
const FALLBACK_SKILLS = [
  { id: 'quality', label: '质量评分', description: 'MANIQA 质量得分、等级与解释' },
  { id: 'diagnostics', label: '质量诊断', description: 'Blur、噪声、曝光、对比度与压缩痕迹诊断' },
  { id: 'quality_fusion', label: '融合质量评审', description: '结合 MANIQA、诊断证据与 LLM 审阅生成最终质量分' },
  { id: 'semantic', label: '语义增强', description: 'Caption、目标、场景分类与复杂度分析' },
];

const normalizeResults = (items = []) =>
  items.map((item) => {
    const snapshot = item.snapshot || {};
    const image = resolveAssetUrl(snapshot.image);
    const thumbnail = resolveAssetUrl(snapshot.thumbnail || snapshot.image);
    return {
      ...item,
      snapshot: {
        ...snapshot,
        image,
        thumbnail,
      },
    };
  });

const normalizeHistoryList = (items = []) =>
  items
    .filter(Boolean)
    .map((item) => {
      const image = resolveAssetUrl(item.image);
      const thumbnail = resolveAssetUrl(item.thumbnail || item.image);
      return {
        ...item,
        batch_id: item.batch_id,
        image,
        thumbnail,
      };
    });

const mergeHistoryLists = (prev = [], next = [], append = false) => {
  if (!append) {
    return next;
  }
  const map = new Map();
  prev.forEach((item) => {
    if (!map.has(item.batch_id)) {
      map.set(item.batch_id, item);
    }
  });
  next.forEach((item) => {
    if (!map.has(item.batch_id)) {
      map.set(item.batch_id, item);
    }
  });
  return Array.from(map.values());
};

const Home = () => {
  const [isUploading, setIsUploading] = useState(false);
  const [progress, setProgress] = useState(0);
  const [status, setStatus] = useState('waiting');
  const [error, setError] = useState('');
  const [results, setResults] = useState([]);
  const [uploads, setUploads] = useState([]);
  const [historyItems, setHistoryItems] = useState(() => normalizeHistoryList(loadHistoryCache()));
  const [historyCursor, setHistoryCursor] = useState(null);
  const [historyLoading, setHistoryLoading] = useState(false);
  const [historyDetailLoading, setHistoryDetailLoading] = useState(false);
  const [historyDetailBatch, setHistoryDetailBatch] = useState(null);
  const [historyDetailSelectedId, setHistoryDetailSelectedId] = useState(null);
  const [availableSkills, setAvailableSkills] = useState(FALLBACK_SKILLS);
  const [selectedSkills, setSelectedSkills] = useState(DEFAULT_SKILL_SELECTION);
  const [providerPresets, setProviderPresets] = useState([]);
  const [providerProfiles, setProviderProfiles] = useState([]);
  const [activeProviderId, setActiveProviderId] = useState(null);
  const [activeProviderLabel, setActiveProviderLabel] = useState('未配置');
  const [providerLoading, setProviderLoading] = useState(false);
  const [isProviderPanelOpen, setIsProviderPanelOpen] = useState(false);
  const selectedSkillLabels = useMemo(
    () => selectedSkills.map((skillId) => availableSkills.find((item) => item.id === skillId)?.label || skillId),
    [availableSkills, selectedSkills]
  );

  const progressLabel = useMemo(() => {
    switch (status) {
      case 'waiting':
        return '等待上传';
      case 'uploading':
        return '上传文件中';
      case 'analyzing':
        return 'AI 思考中';
      case 'completed':
        return '分析完成';
      case 'failed':
        return '操作失败';
      default:
        return '处理中';
    }
  }, [status]);

  const resetState = useCallback(() => {
    setIsUploading(false);
    setProgress(0);
    setStatus('waiting');
    setError('');
    setResults([]);
    setUploads([]);
  }, []);

  const hydrateHistory = useCallback(
    async ({ cursor, append = false } = {}) => {
      try {
        setHistoryLoading(true);
        const { data } = await fetchHistory({ cursor, limit: 20 });
        setHistoryCursor(data.next_cursor || null);
        setHistoryItems((prev) => {
          const normalized = normalizeHistoryList(data.history || []);
          const merged = mergeHistoryLists(prev, normalized, append);
          saveHistoryCache(merged);
          return merged;
        });
      } catch (err) {
        console.error('获取历史记录失败', err);
      } finally {
        setHistoryLoading(false);
      }
    },
    []
  );

  useEffect(() => {
    hydrateHistory({ append: false });
  }, [hydrateHistory]);

  useEffect(() => {
    fetchSkills()
      .then(({ data }) => {
        const incoming = Array.isArray(data?.skills) ? data.skills : [];
        if (!incoming.length) return;
        const merged = incoming.map((item) => {
          const fallback = FALLBACK_SKILLS.find((skill) => skill.id === item.id);
          return {
            id: item.id,
            label: fallback?.label || item.id,
            description: fallback?.description || item.description || item.id,
          };
        });
        setAvailableSkills(merged);
        setSelectedSkills((prev) => {
          const validIds = new Set(merged.map((item) => item.id));
          const filtered = prev.filter((item) => validIds.has(item));
          return filtered.length ? filtered : merged.map((item) => item.id);
        });
      })
      .catch((err) => {
        console.error('获取技能列表失败', err);
      });
  }, []);

  const hydrateProviders = useCallback(async () => {
    try {
      setProviderLoading(true);
      const [{ data: presetsData }, { data: profilesData }, { data: activeData }] = await Promise.all([
        fetchProviderPresets(),
        fetchProviderProfiles(),
        fetchActiveProviderProfile(),
      ]);
      setProviderPresets(presetsData?.presets || []);
      setProviderProfiles(profilesData?.profiles || []);
      setActiveProviderId(profilesData?.active_profile_id || null);
      const activeProfile = activeData?.profile;
      setActiveProviderLabel(
        activeProfile ? (activeProfile.name || activeProfile.model || '未配置') : '未配置'
      );
    } catch (err) {
      console.error('获取 Provider 配置失败', err);
    } finally {
      setProviderLoading(false);
    }
  }, []);

  useEffect(() => {
    hydrateProviders();
  }, [hydrateProviders]);

  useEffect(() => {
    if (!historyDetailBatch?.items?.length) {
      setHistoryDetailSelectedId(null);
      return;
    }
    setHistoryDetailSelectedId((prev) =>
      prev && historyDetailBatch.items.some((item) => item.upload_id === prev)
        ? prev
        : historyDetailBatch.items[0].upload_id
    );
  }, [historyDetailBatch]);

  const toggleSkill = useCallback((skillId) => {
    setSelectedSkills((prev) => {
      if (prev.includes(skillId)) {
        if (prev.length === 1) {
          return prev;
        }
        return prev.filter((item) => item !== skillId);
      }
      return [...prev, skillId];
    });
  }, []);

  const handleUpload = useCallback(
    async (files, resetInput) => {
      if (!selectedSkills.length) {
        setError('请至少选择一个分析技能');
        return;
      }
      try {
        setIsUploading(true);
        setError('');
        setResults([]);
        setUploads([]);
        setStatus('uploading');
        setProgress(5);

        const uploadResponse = await uploadImages(files, (event) => {
          if (event?.total) {
            const percent = Math.round((event.loaded / event.total) * 60);
            setProgress(Math.min(60, Math.max(10, percent)));
          } else {
            setProgress((prev) => Math.min(60, prev + 5));
          }
        });

        const uploaded = uploadResponse.data?.uploads || [];
        setUploads(uploaded);
        if (!uploaded.length) {
          throw new Error('上传失败，未获得上传 ID');
        }

        setStatus('analyzing');
        setProgress((prev) => Math.max(prev, 70));

        const analyzeResponse = await analyzeImages({
          uploadIds: uploaded.map((item) => item.upload_id),
          detail: DEFAULT_DETAIL,
          skills: selectedSkills,
        });

        const analyzeResults = normalizeResults(analyzeResponse.data?.results || []);
        setResults(analyzeResults);
        setStatus('completed');
        setProgress(100);
        resetInput();
        hydrateHistory({ append: false });
      } catch (err) {
        console.error(err);
        setStatus('failed');
        setProgress(0);
        const message =
          err?.response?.data?.detail ||
          err?.response?.data?.message ||
          err?.message ||
          '上传或分析失败，请稍后重试';
        setError(message);
      } finally {
        setIsUploading(false);
      }
    },
    [hydrateHistory, selectedSkills]
  );

  const handleHistoryDelete = useCallback(async (batchId) => {
    if (!batchId) return;
    try {
      await deleteHistoryItem(batchId);
      setHistoryItems((prev) => {
        const filtered = prev.filter((item) => item.batch_id !== batchId);
        saveHistoryCache(filtered);
        return filtered;
      });
      setHistoryDetailBatch((prev) => (prev?.batch_id === batchId ? null : prev));
    } catch (err) {
      console.error('删除历史记录失败', err);
    }
  }, []);

  const handleHistoryClear = useCallback(async () => {
    try {
      setHistoryLoading(true);
      await clearHistory();
      setHistoryItems([]);
      setHistoryCursor(null);
      setHistoryDetailBatch(null);
      clearHistoryCache();
    } catch (err) {
      console.error('清空历史记录失败', err);
    } finally {
      setHistoryLoading(false);
    }
  }, []);

  const loadMoreHistory = useCallback(() => {
    if (!historyCursor || historyLoading) return;
    hydrateHistory({ cursor: historyCursor, append: true });
  }, [historyCursor, historyLoading, hydrateHistory]);

  const handleOpenHistoryBatch = useCallback(async (batchId) => {
    if (!batchId) return;
    try {
      setHistoryDetailLoading(true);
      const { data } = await fetchHistoryBatch(batchId);
      const batch = data?.batch;
      if (!batch) return;
      setHistoryDetailBatch({
        ...batch,
        items: normalizeResults((batch.items || []).map((item) => item.result || item)),
      });
    } catch (err) {
      console.error('获取历史详情失败', err);
    } finally {
      setHistoryDetailLoading(false);
    }
  }, []);

  const handleSaveProvider = useCallback(
    async (form, setStatusText, resetForm) => {
      try {
        const { data } = await saveProviderProfile(form);
        setStatusText(`已保存配置：${data?.profile?.name || form.name}`);
        resetForm();
        hydrateProviders();
      } catch (err) {
        console.error('保存 Provider 配置失败', err);
        setStatusText(err?.response?.data?.detail || '保存失败');
      }
    },
    [hydrateProviders]
  );

  const handleActivateProvider = useCallback(
    async (profileId, setStatusText) => {
      try {
        const { data } = await activateProviderProfile(profileId);
        setStatusText(`已启用：${data?.profile?.name || profileId}`);
        hydrateProviders();
      } catch (err) {
        console.error('启用 Provider 配置失败', err);
        setStatusText(err?.response?.data?.detail || '启用失败');
      }
    },
    [hydrateProviders]
  );

  const handleDeleteProvider = useCallback(
    async (profileId, setStatusText) => {
      try {
        await deleteProviderProfile(profileId);
        setStatusText('已删除配置');
        hydrateProviders();
      } catch (err) {
        console.error('删除 Provider 配置失败', err);
        setStatusText(err?.response?.data?.detail || '删除失败');
      }
    },
    [hydrateProviders]
  );

  const handleTestProvider = useCallback(async (profileId, setStatusText) => {
    try {
      const { data } = await testProviderProfile(profileId);
      setStatusText(data?.ok ? `连接成功：${data.detail}` : `连接失败：${data.detail}`);
    } catch (err) {
      console.error('测试 Provider 配置失败', err);
      setStatusText(err?.response?.data?.detail || '测试失败');
    }
  }, []);

  const historyDetailItems = historyDetailBatch?.items || [];
  const historyDetailSelectedIndex = historyDetailItems.findIndex((item) => item.upload_id === historyDetailSelectedId);
  const historyDetailSelectedResult =
    historyDetailSelectedIndex >= 0 ? historyDetailItems[historyDetailSelectedIndex] : null;
  const canShowPrevHistoryDetail = historyDetailSelectedIndex > 0;
  const canShowNextHistoryDetail =
    historyDetailSelectedIndex >= 0 && historyDetailSelectedIndex < historyDetailItems.length - 1;

  return (
    <main className="page">
      <section className="hero-panel">
        <div className="hero-topline">
          <span className="hero-eyebrow">AI Image Analysis Platform</span>
          <button
            type="button"
            className="ghost hero-settings-button"
            onClick={() => setIsProviderPanelOpen(true)}
            disabled={providerLoading}
          >
            {providerLoading ? '加载模型配置...' : '模型配置中心'}
          </button>
        </div>
        <div className="hero-grid">
          <div className="hero-copy">
            <h1>
              <span>图像质量评估</span>
              <span>与内容识别</span>
            </h1>
            <p>
              面向研究展示与高质量演示的图像分析工作台，统一编排质量评分、诊断、语义理解与云模型配置。
            </p>
            <div className="hero-chip-row">
              <span className="hero-chip">当前模型：{activeProviderLabel}</span>
              <span className="hero-chip">技能数：{selectedSkillLabels.length}</span>
              <span className="hero-chip">历史记录：{historyItems.length}</span>
            </div>
          </div>
          <div className="hero-rail">
            <div className="hero-stat-card">
              <span className="hero-stat-label">执行状态</span>
              <strong>{progressLabel}</strong>
              <p>
                {status === 'waiting'
                  ? '系统空闲，等待新的图像分析任务。'
                  : status === 'analyzing'
                    ? 'AI 正在结合所选技能链思考并生成分析结果。'
                    : status === 'completed'
                      ? '本轮分析已完成，可以继续浏览结果、回看历史或发起新任务。'
                      : '当前任务正在按技能链进行处理。'}
              </p>
            </div>
            <div className="hero-stat-card accent">
              <span className="hero-stat-label">当前技能链</span>
              <strong>{selectedSkillLabels.join(' / ')}</strong>
              <p>可以自由组合质量、诊断、语义模块，以适配不同的实验与演示需求。</p>
            </div>
          </div>
        </div>
      </section>

      {isProviderPanelOpen && (
        <div className="modal-backdrop" role="presentation" onClick={() => setIsProviderPanelOpen(false)}>
          <div
            className="modal-panel"
            role="dialog"
            aria-modal="true"
            aria-label="模型配置中心"
            onClick={(event) => event.stopPropagation()}
          >
            <ProviderPanel
              presets={providerPresets}
              profiles={providerProfiles}
              activeProfileId={activeProviderId}
              loading={providerLoading}
              onClose={() => setIsProviderPanelOpen(false)}
              onSave={handleSaveProvider}
              onActivate={handleActivateProvider}
              onDelete={handleDeleteProvider}
              onTest={handleTestProvider}
              onRefresh={hydrateProviders}
            />
          </div>
        </div>
      )}

      {historyDetailBatch && (
        <div className="modal-backdrop" role="presentation" onClick={() => setHistoryDetailBatch(null)}>
          <div
            className="modal-panel result-detail-panel"
            role="dialog"
            aria-modal="true"
            aria-label="历史批次详情"
            onClick={(event) => event.stopPropagation()}
          >
            <div className="result-detail-toolbar">
              <div className="results-title-group">
                <span className="result-kicker">Batch Detail</span>
                <h2>历史分析详情</h2>
                <p className="muted">
                  {historyDetailBatch.item_count || historyDetailBatch.items?.length || 0} 张图片，
                  平均分 {historyDetailBatch.avg_score ?? '--'}
                </p>
              </div>
              <div className="result-detail-nav">
                <button
                  type="button"
                  className="ghost"
                  onClick={() => setHistoryDetailSelectedId(historyDetailItems[historyDetailSelectedIndex - 1]?.upload_id)}
                  disabled={!canShowPrevHistoryDetail}
                >
                  上一张
                </button>
                <button
                  type="button"
                  className="ghost"
                  onClick={() => setHistoryDetailSelectedId(historyDetailItems[historyDetailSelectedIndex + 1]?.upload_id)}
                  disabled={!canShowNextHistoryDetail}
                >
                  下一张
                </button>
                <button type="button" className="ghost" onClick={() => setHistoryDetailBatch(null)}>
                  关闭详情
                </button>
              </div>
            </div>
            {historyDetailLoading ? <p className="muted">加载中...</p> : null}
            {!historyDetailLoading && historyDetailSelectedResult ? (
              <>
                <p className="muted">
                  当前查看 {historyDetailSelectedIndex + 1} / {historyDetailItems.length}
                </p>
                <ResultCard key={historyDetailSelectedResult.upload_id} result={historyDetailSelectedResult} />
              </>
            ) : null}
          </div>
        </div>
      )}

      <div className="layout">
        <div className="main-column">
          <section className="panel">
            <UploadBox
              onUpload={handleUpload}
              isUploading={isUploading}
              status={status}
              skills={availableSkills}
              selectedSkills={selectedSkills}
              onToggleSkill={toggleSkill}
            />
          </section>

          <section className="panel">
            <div className="status-row command-row">
              <div className="command-main">
                <span className="command-label">任务状态</span>
                <strong>{progressLabel}</strong>
              </div>
              {uploads.length > 0 && (
                <span className="muted command-meta">
                  任务：{uploads.length} 个 | 首个 ID：{uploads[0]?.upload_id}
                </span>
              )}
            </div>
            <div className="status-chip-strip">
              {selectedSkillLabels.map((label) => (
                <span key={label} className="status-chip">
                  {label}
                </span>
              ))}
            </div>
            <ProgressBar progress={progress} status={status} />
            {error && <p className="error-banner">{error}</p>}
          </section>

          <ResultsWorkspace results={results} />

          {!results.length && status === 'completed' && (
            <section className="panel">
              <p className="muted">分析完成，但未返回结果。</p>
            </section>
          )}

          <footer className="footer">
            <button type="button" className="link" onClick={resetState} disabled={isUploading}>
              重置
            </button>
            <span className="muted">接口地址：{import.meta.env.VITE_API_BASE_URL || 'http://127.0.0.1:8000'}</span>
          </footer>
        </div>

        <Sidebar
          items={historyItems}
          loading={historyLoading}
          activeBatchId={historyDetailBatch?.batch_id || null}
          hasMore={Boolean(historyCursor)}
          onOpen={handleOpenHistoryBatch}
          onRefresh={() => hydrateHistory({ append: false })}
          onClearAll={handleHistoryClear}
          onLoadMore={loadMoreHistory}
          onDelete={handleHistoryDelete}
        />
      </div>
    </main>
  );
};

export default Home;
