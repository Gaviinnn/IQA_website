import { useEffect, useMemo, useRef, useState } from 'react';

import ProgressBar from '../components/ProgressBar.jsx';
import ResultCard from '../components/ResultCard.jsx';
import UploadBox from '../components/UploadBox.jsx';
import {
  analyzeImages,
  chatFilterBatch,
  exportFilterBatch,
  fetchHistory,
  fetchHistoryBatch,
  resolveAssetUrl,
  uploadImages,
} from '../utils/api.js';
import { formatTimestamp, getResultScore } from '../utils/resultPresentation.js';

const DEFAULT_DETAIL = 'low';
const FILTER_ANALYSIS_SKILLS = ['quality_fusion', 'semantic'];
const QUICK_PROMPTS = [
  '先概括这个批次里主要有哪些场景和对象',
  '只保留质量最高的 6 张图片',
  '移除模糊、曝光异常或噪声偏高的图片',
  '只保留包含人物或建筑、适合展示的图片',
];

const normalizeHistoryList = (items = []) =>
  items
    .filter(Boolean)
    .map((item) => ({
      ...item,
      image: resolveAssetUrl(item.image),
      thumbnail: resolveAssetUrl(item.thumbnail || item.image),
    }));

const normalizeBatch = (batch) => {
  if (!batch) return null;
  return {
    ...batch,
    items: (batch.items || []).map((item) => {
      const result = item.result || item;
      return {
        ...result,
        snapshot: {
          ...(result.snapshot || {}),
          image: resolveAssetUrl(result?.snapshot?.image || item.image),
          thumbnail: resolveAssetUrl(result?.snapshot?.thumbnail || item.thumbnail || item.image),
        },
      };
    }),
  };
};

const normalizeResults = (items = []) =>
  items.map((item) => {
    const snapshot = item.snapshot || {};
    return {
      ...item,
      snapshot: {
        ...snapshot,
        image: resolveAssetUrl(snapshot.image),
        thumbnail: resolveAssetUrl(snapshot.thumbnail || snapshot.image),
      },
    };
  });

const normalizeFilterEntries = (items = []) =>
  items.map((item) => {
    const result = item.result || item;
    const normalizedResults = normalizeResults([result]);
    return {
      ...item,
      thumbnail: resolveAssetUrl(item.thumbnail) || normalizedResults[0]?.snapshot?.thumbnail,
      image: resolveAssetUrl(item.image) || normalizedResults[0]?.snapshot?.image,
      result: normalizedResults[0],
    };
  });

const createMessage = (role, content, extras = {}) => ({
  id: `${role}_${Date.now()}_${Math.random().toString(36).slice(2, 8)}`,
  role,
  content,
  ...extras,
});

const buildBatchReadyMessage = (batch) => {
  const count = batch?.item_count || batch?.items?.length || 0;
  const avgScore = batch?.avg_score ?? '--';
  return `批次已就绪，共 ${count} 张图片，平均分 ${avgScore}。你可以先问我这个批次里有什么，再决定是否执行筛选。`;
};

const toChatPayload = (messages = []) =>
  messages
    .filter((item) => item?.role === 'user' || item?.role === 'assistant')
    .map((item) => ({
      role: item.role,
      content: item.content,
    }));

const FilterStudio = () => {
  const [uploading, setUploading] = useState(false);
  const [uploadStatus, setUploadStatus] = useState('waiting');
  const [uploadProgress, setUploadProgress] = useState(0);
  const [historyItems, setHistoryItems] = useState([]);
  const [historyLoading, setHistoryLoading] = useState(false);
  const [selectedBatchId, setSelectedBatchId] = useState(null);
  const [selectedBatch, setSelectedBatch] = useState(null);
  const [draft, setDraft] = useState('');
  const [messages, setMessages] = useState([]);
  const [chatting, setChatting] = useState(false);
  const [downloading, setDownloading] = useState(false);
  const [runResult, setRunResult] = useState(null);
  const [activeTab, setActiveTab] = useState('kept');
  const [selectedDetail, setSelectedDetail] = useState(null);
  const [error, setError] = useState('');
  const chatThreadRef = useRef(null);
  const resultPanelRef = useRef(null);

  const refreshHistory = async ({ preferredBatchId } = {}) => {
    try {
      setHistoryLoading(true);
      const { data } = await fetchHistory({ limit: 20 });
      const items = normalizeHistoryList(data?.history || []);
      setHistoryItems(items);
      setSelectedBatchId((prev) => preferredBatchId || prev || items[0]?.batch_id || null);
    } catch (err) {
      console.error('获取历史批次失败', err);
      setError('获取历史批次失败');
    } finally {
      setHistoryLoading(false);
    }
  };

  useEffect(() => {
    refreshHistory();
  }, []);

  useEffect(() => {
    if (!selectedBatchId) {
      setSelectedBatch(null);
      setMessages([]);
      setRunResult(null);
      setSelectedDetail(null);
      return;
    }
    const loadBatch = async () => {
      try {
        const { data } = await fetchHistoryBatch(selectedBatchId);
        setSelectedBatch(normalizeBatch(data?.batch));
        setRunResult(null);
        setActiveTab('kept');
        setSelectedDetail(null);
      } catch (err) {
        console.error('获取批次详情失败', err);
        setError('获取批次详情失败');
      }
    };
    loadBatch();
  }, [selectedBatchId]);

  useEffect(() => {
    if (!selectedBatch) {
      setMessages([]);
      return;
    }
    setMessages([createMessage('assistant', buildBatchReadyMessage(selectedBatch))]);
    setDraft('');
    setError('');
  }, [selectedBatch]);

  useEffect(() => {
    if (!chatThreadRef.current) return;
    chatThreadRef.current.scrollTop = chatThreadRef.current.scrollHeight;
  }, [messages, chatting]);

  useEffect(() => {
    if (!runResult || !resultPanelRef.current) return;
    resultPanelRef.current.scrollIntoView({ behavior: 'smooth', block: 'start' });
  }, [runResult]);

  const displayedItems = useMemo(() => {
    if (!runResult) {
      return [];
    }
    if (activeTab === 'kept') return runResult.kept || [];
    if (activeTab === 'removed') return runResult.removed || [];
    return [...(runResult.kept || []), ...(runResult.removed || [])];
  }, [activeTab, runResult]);

  const activeScopeIds = useMemo(
    () => (runResult?.kept || []).map((item) => item.upload_id).filter(Boolean),
    [runResult]
  );

  const activeScopeCount = activeScopeIds.length;
  const usingFilteredScope = Boolean(runResult && activeScopeCount);

  const handleDirectUpload = async (files, resetInput) => {
    try {
      setUploading(true);
      setUploadStatus('uploading');
      setUploadProgress(5);
      setError('');
      setRunResult(null);

      const uploadResponse = await uploadImages(files, (event) => {
        if (event?.total) {
          const percent = Math.round((event.loaded / event.total) * 60);
          setUploadProgress(Math.min(60, Math.max(10, percent)));
        }
      });

      const uploaded = uploadResponse.data?.uploads || [];
      if (!uploaded.length) {
        throw new Error('上传失败，未获得上传 ID');
      }

      setUploadStatus('analyzing');
      setUploadProgress(70);

      const analyzeResponse = await analyzeImages({
        uploadIds: uploaded.map((item) => item.upload_id),
        detail: DEFAULT_DETAIL,
        skills: FILTER_ANALYSIS_SKILLS,
      });

      const results = normalizeResults(analyzeResponse.data?.results || []);
      const batchId = results[0]?.meta?.batch_id;
      const avgScore =
        results.length
          ? (results.reduce((sum, item) => sum + (getResultScore(item) || 0), 0) / results.length).toFixed(2)
          : null;
      setSelectedBatch(
        batchId
          ? {
              batch_id: batchId,
              item_count: results.length,
              avg_score: avgScore,
              items: results,
            }
          : null
      );
      setSelectedBatchId(batchId || null);
      setUploadStatus('completed');
      setUploadProgress(100);
      resetInput();
      if (batchId) {
        await refreshHistory({ preferredBatchId: batchId });
      }
    } catch (err) {
      console.error('筛选工作台上传分析失败', err);
      setUploadStatus('failed');
      setUploadProgress(0);
      setError(err?.response?.data?.detail || err?.message || '上传并分析失败');
    } finally {
      setUploading(false);
    }
  };

  const handleSend = async () => {
    const content = draft.trim();
    if (!selectedBatchId || !content || chatting || uploading) return;

    const userMessage = createMessage('user', content);
    const nextMessages = [...messages, userMessage];
    setMessages(nextMessages);
    setDraft('');
    setError('');

    try {
      setChatting(true);
      const { data } = await chatFilterBatch({
        batchId: selectedBatchId,
        messages: toChatPayload(nextMessages),
        activeUploadIds: activeScopeIds,
      });
      setMessages((prev) => [
        ...prev,
        createMessage('assistant', data?.assistant_message || '已处理这轮请求。', {
          didExecute: Boolean(data?.did_execute),
          assistantMode: data?.turn?.mode || '',
          hasToolTrace: Array.isArray(data?.turn?.tool_trace) && data.turn.tool_trace.length > 0,
          executionSummary: '',
        }),
      ]);
      if (data?.did_execute && data?.result) {
        setRunResult({
          ...(data?.result || {}),
          kept: normalizeFilterEntries(data?.result?.kept || []),
          removed: normalizeFilterEntries(data?.result?.removed || []),
        });
        setActiveTab('kept');
        setSelectedDetail(null);
      }
    } catch (err) {
      console.error('执行对话筛选失败', err);
      setMessages((prev) => [
        ...prev,
        createMessage('assistant', '这轮对话没有成功处理，请换一种描述方式，或先确认当前批次已分析完成。'),
      ]);
      setError(err?.response?.data?.detail || '执行对话筛选失败');
    } finally {
      setChatting(false);
    }
  };

  const handleDownload = async () => {
    const keptIds = (runResult?.kept || []).map((item) => item.upload_id).filter(Boolean);
    if (!selectedBatchId || !keptIds.length) return;
    try {
      setDownloading(true);
      setError('');
      const response = await exportFilterBatch({
        batchId: selectedBatchId,
        keptUploadIds: keptIds,
        filename: `filtered_${selectedBatchId}`,
      });
      const blob = response instanceof Blob ? response : response.data;
      const url = window.URL.createObjectURL(blob);
      const anchor = document.createElement('a');
      anchor.href = url;
      anchor.download = `filtered_${selectedBatchId}.zip`;
      anchor.click();
      window.URL.revokeObjectURL(url);
    } catch (err) {
      console.error('导出筛选结果失败', err);
      setError('导出筛选结果失败');
    } finally {
      setDownloading(false);
    }
  };

  const handleComposerKeyDown = (event) => {
    if (event.key === 'Enter' && !event.shiftKey) {
      event.preventDefault();
      handleSend();
    }
  };

  const handleResetScope = () => {
    if (!selectedBatch) return;
    setRunResult(null);
    setSelectedDetail(null);
    setActiveTab('kept');
    setMessages((prev) => [
      ...prev,
      createMessage('assistant', '已切回整批图片。接下来我会基于当前批次的全部图片继续回答或执行筛选。', {
        didExecute: false,
        assistantMode: 'scope_reset',
        hasToolTrace: false,
      }),
    ]);
  };

  const handleResetConversation = () => {
    if (!selectedBatch) return;
    setMessages([createMessage('assistant', buildBatchReadyMessage(selectedBatch))]);
    setDraft('');
    setError('');
  };

  return (
    <main className="page">
      <section className="hero-panel filter-hero-panel">
        <div className="hero-copy">
          <span className="hero-eyebrow">Image Curation Assistant</span>
          <h1>
            <span>图片整理助手</span>
          </h1>
          <p>面向批量图片整理与数据清洗，支持多轮对话理解批次内容、逐步确认条件，再执行筛选并导出结果。</p>
          <div className="hero-chip-row">
            <span className="hero-chip">固定分析：融合质量评审 + 语义增强</span>
            <span className="hero-chip">当前批次：{selectedBatch?.item_count || selectedBatch?.items?.length || 0} 张</span>
            <span className="hero-chip">
              状态：{chatting ? '助手回复中' : downloading ? '导出中' : uploading ? '上传分析中' : '等待消息'}
            </span>
          </div>
        </div>
      </section>

      <div className="filter-studio-shell">
        <section className="filter-studio-grid">
          <section className="panel filter-upload-card">
            <div className="results-title-group">
              <span className="result-kicker">Upload Batch</span>
              <h2>上传图片</h2>
              <p className="muted">上传后自动分析，并立即进入对话上下文。</p>
            </div>
            <UploadBox
              onUpload={handleDirectUpload}
              isUploading={uploading}
              status={uploadStatus}
              skills={[]}
              selectedSkills={[]}
              onToggleSkill={undefined}
              autoSubmit
              hideActions
            />
            <ProgressBar progress={uploadProgress} status={uploadStatus} />
            <p className="hint">选中图片后自动上传与分析。</p>
          </section>

          <section className="panel chat-panel">
            <div className="results-title-group">
              <span className="result-kicker">Image Curation Assistant</span>
              <h2>图片整理助手</h2>
              <p className="muted">你可以先问批次内容，再明确说保留或去掉什么类型的图片。</p>
            </div>

            <div className="chat-toolbar">
              <div className={usingFilteredScope ? 'chat-scope-banner active' : 'chat-scope-banner'}>
                <strong>{usingFilteredScope ? `后续基于已保留 ${activeScopeCount} 张继续筛` : '后续基于整批图片筛选'}</strong>
                <span>
                  {usingFilteredScope
                    ? '需要重新从全部图片开始时，使用下方重置范围。'
                    : '第一次执行筛选后，后续消息会默认接着保留结果继续收窄。'}
                </span>
              </div>
              {usingFilteredScope ? (
                <button type="button" className="ghost" onClick={handleResetScope}>
                  重新从整批开始
                </button>
              ) : null}
              <button type="button" className="ghost" onClick={handleResetConversation} disabled={!selectedBatchId || chatting || uploading}>
                清空对话
              </button>
            </div>

            <div ref={chatThreadRef} className="chat-thread" aria-live="polite">
              {!messages.length && (
                <div className="chat-empty">
                  <strong>先上传一个批次</strong>
                  <p>批次准备好之后，这里会进入可连续对话的整理模式。</p>
                </div>
              )}
              {messages.map((message) => (
                <div key={message.id} className={message.role === 'user' ? 'chat-message user' : 'chat-message assistant'}>
                  <span className="chat-role">{message.role === 'user' ? '你' : '图片整理助手'}</span>
                  <div className="chat-bubble">
                    {message.role === 'assistant' ? (
                      <div className="chat-badge-row">
                        <span className={message.didExecute ? 'chat-badge action' : 'chat-badge info'}>
                          {message.didExecute ? '已执行筛选' : '仅回复说明'}
                        </span>
                        {message.hasToolTrace ? <span className="chat-badge subtle">已结合看图判断</span> : null}
                      </div>
                    ) : null}
                    <p>{message.content}</p>
                    {message.executionSummary ? <small className="chat-execution-summary">{message.executionSummary}</small> : null}
                  </div>
                </div>
              ))}
              {chatting && (
                <div className="chat-message assistant">
                  <span className="chat-role">图片整理助手</span>
                  <div className="chat-bubble typing">
                    <p>正在结合当前批次与历史对话生成回复…</p>
                  </div>
                </div>
              )}
            </div>

            <div className="chat-composer">
              <div className="quick-prompt-row">
                {QUICK_PROMPTS.map((prompt) => (
                  <button
                    key={prompt}
                    type="button"
                    className="ghost quick-prompt"
                    onClick={() => setDraft(prompt)}
                    disabled={!selectedBatchId || uploading || chatting}
                  >
                    {prompt}
                  </button>
                ))}
              </div>
              <label className="sr-only" htmlFor="filter-chat-input">
                输入筛选需求
              </label>
              <textarea
                id="filter-chat-input"
                value={draft}
                onChange={(event) => setDraft(event.target.value)}
                onKeyDown={handleComposerKeyDown}
                placeholder="例：这里有夜晚场景吗？如果有，再只保留夜景里质量最高的 6 张"
                rows={4}
                disabled={!selectedBatchId || uploading}
              />
              <div className="actions">
                <button type="button" className="primary" onClick={handleSend} disabled={!selectedBatchId || !draft.trim() || chatting || uploading}>
                  {chatting ? '整理中...' : '发送'}
                </button>
                <button type="button" className="ghost" onClick={handleDownload} disabled={!runResult?.kept?.length || downloading}>
                  {downloading ? '导出中...' : `下载保留结果${runResult?.kept?.length ? `（${runResult.kept.length} 张）` : ''}`}
                </button>
              </div>
            </div>

            {error && <p className="error-banner">{error}</p>}
          </section>

          <div className="filter-context-column">
            {selectedBatch && (
              <section className="panel filter-context-panel">
                <div className="results-title-group">
                  <span className="result-kicker">Batch Context</span>
                  <h2>当前批次</h2>
                </div>
                <div className="filter-batch-summary-grid">
                  <div className="results-stat-card accent filter-batch-stat-card">
                    <span>批次 ID</span>
                    <strong>{selectedBatch.batch_id}</strong>
                    <small>
                      {selectedBatch.item_count || selectedBatch.items?.length || 0} 张图片，平均分 {selectedBatch.avg_score ?? '--'}
                    </small>
                  </div>
                  <div className="filter-scope-card">
                    <div>
                      <strong>{usingFilteredScope ? '已进入连续收窄模式' : '当前是整批范围'}</strong>
                      <p>
                        {usingFilteredScope
                          ? `当前范围共 ${activeScopeCount} 张。继续说“再保留…”或“再去掉…”会在这些图片里继续筛。`
                          : `当前范围共 ${selectedBatch.item_count || selectedBatch.items?.length || 0} 张。`}
                      </p>
                    </div>
                  </div>
                </div>
              </section>
            )}

            {historyItems.length > 0 && (
              <section className="panel filter-history-panel">
                <div className="results-title-group">
                  <span className="result-kicker">History Batches</span>
                  <h2>历史批次</h2>
                  <p className="muted">切换到已有批次继续筛选。</p>
                </div>
                <div className="filter-batch-list compact">
                  {historyLoading ? <p className="muted">加载批次中...</p> : null}
                  {historyItems.map((item) => (
                    <button
                      key={item.batch_id}
                      type="button"
                      className={selectedBatchId === item.batch_id ? 'filter-batch-item active' : 'filter-batch-item'}
                      onClick={() => setSelectedBatchId(item.batch_id)}
                    >
                      <strong>{item.filename || item.batch_id}</strong>
                      <span>{item.item_count || 1} 张</span>
                      <span>平均分 {item.avg_score ?? '--'}</span>
                      <span>{formatTimestamp(item.timestamp)}</span>
                    </button>
                  ))}
                </div>
              </section>
            )}
          </div>
        </section>

        {runResult && (
          <section ref={resultPanelRef} className="panel filter-result-panel">
            <div className="results-header">
              <div className="results-title-group">
                <span className="result-kicker">Filter Result</span>
                <h2>筛选结果</h2>
                <p className="muted">
                  共 {runResult.summary?.total ?? 0} 张，保留 {runResult.summary?.kept ?? 0} 张，移除 {runResult.summary?.removed ?? 0} 张。
                </p>
              </div>
              <div className="results-view-toggle">
                <button type="button" className={activeTab === 'kept' ? 'secondary active' : 'ghost'} onClick={() => setActiveTab('kept')}>
                  保留
                </button>
                <button type="button" className={activeTab === 'removed' ? 'secondary active' : 'ghost'} onClick={() => setActiveTab('removed')}>
                  移除
                </button>
                <button type="button" className={activeTab === 'all' ? 'secondary active' : 'ghost'} onClick={() => setActiveTab('all')}>
                  全部
                </button>
              </div>
            </div>

            <div className="results-grid filter-results-grid">
              {displayedItems.map((item) => {
                const result = item.result || item;
                const score = getResultScore(result);
                const previewImage = result?.snapshot?.thumbnail || item.thumbnail;
                return (
                  <button key={item.upload_id || result.upload_id} type="button" className="result-overview-card filter-result-card" onClick={() => setSelectedDetail(result)}>
                    <div className="result-overview-media filter-result-media">
                      <div className="result-overview-media-frame">
                        {previewImage ? (
                          <img src={previewImage} alt={result.filename || result.upload_id} loading="lazy" />
                        ) : (
                          <div className="result-overview-fallback">无缩略图</div>
                        )}
                      </div>
                    </div>
                    <div className="result-overview-body">
                      <div className="result-overview-head">
                        <strong>{result.filename || result.upload_id}</strong>
                        <span>{typeof score === 'number' ? `${score.toFixed(2)} / 100` : '--'}</span>
                      </div>
                      <p className="result-overview-summary">{item.reason || '符合筛选条件'}</p>
                      {item.decision_basis?.length ? (
                        <div className="filter-basis-list">
                          {item.decision_basis.slice(0, 3).map((basis, index) => (
                            <span key={`basis-${index}`}>{basis}</span>
                          ))}
                        </div>
                      ) : null}
                      {item.matched_rules?.length ? (
                        <div className="tag-list">
                          {item.matched_rules.slice(0, 2).map((rule, index) => (
                            <span key={`matched-${index}`} className="tag-chip">
                              命中：{rule}
                            </span>
                          ))}
                        </div>
                      ) : null}
                      {item.unmet_rules?.length ? (
                        <div className="tag-list">
                          {item.unmet_rules.slice(0, 2).map((rule, index) => (
                            <span key={`unmet-${index}`} className="tag-chip subtle">
                              未命中：{rule}
                            </span>
                          ))}
                        </div>
                      ) : null}
                    </div>
                  </button>
                );
              })}
            </div>
          </section>
        )}
      </div>

      {selectedDetail && (
        <div className="modal-backdrop" role="presentation" onClick={() => setSelectedDetail(null)}>
          <div className="modal-panel result-detail-panel" role="dialog" aria-modal="true" aria-label="筛选结果详情" onClick={(event) => event.stopPropagation()}>
            <div className="result-detail-toolbar">
              <div className="results-title-group">
                <span className="result-kicker">Filter Detail</span>
                <h2>筛选结果详情</h2>
              </div>
              <button type="button" className="ghost" onClick={() => setSelectedDetail(null)}>
                关闭详情
              </button>
            </div>
            {runResult ? (
              <section className="panel">
                <div className="results-title-group">
                  <span className="result-kicker">Rule Match</span>
                  <h3>筛选命中详情</h3>
                </div>
                {(() => {
                  const allItems = [...(runResult.kept || []), ...(runResult.removed || [])];
                  const current = allItems.find((item) => item.upload_id === selectedDetail.upload_id);
                  if (!current) {
                    return <p className="muted">当前图片未找到筛选记录。</p>;
                  }
                  return (
                    <>
                      <p className="muted">{current.reason}</p>
                      {current.matched_rules?.length ? (
                        <div className="tag-list">
                          {current.matched_rules.map((rule, index) => (
                            <span key={`detail-matched-${index}`} className="tag-chip">
                              命中：{rule}
                            </span>
                          ))}
                        </div>
                      ) : null}
                      {current.unmet_rules?.length ? (
                        <div className="tag-list">
                          {current.unmet_rules.map((rule, index) => (
                            <span key={`detail-unmet-${index}`} className="tag-chip subtle">
                              未命中：{rule}
                            </span>
                          ))}
                        </div>
                      ) : null}
                    </>
                  );
                })()}
              </section>
            ) : null}
            <ResultCard result={selectedDetail} />
          </div>
        </div>
      )}
    </main>
  );
};

export default FilterStudio;
