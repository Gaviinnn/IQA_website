import { useEffect, useMemo, useState } from 'react';

import ResultCard from './ResultCard.jsx';
import {
  countScreeningMatches,
  formatElapsed,
  formatTimestamp,
  getPrimaryTags,
  getQualityBucket,
  getResultElapsedMs,
  getResultScore,
  getResultSummary,
  hasSemanticIssue,
  matchesScreeningRule,
  SCREENING_RULES,
} from '../utils/resultPresentation.js';

const FILTERS = [
  { id: 'all', label: '全部结果' },
  { id: 'low', label: '低分图片' },
  { id: 'degraded', label: '降级结果' },
  { id: 'semantic_issue', label: '语义异常' },
];

const SORT_OPTIONS = [
  { id: 'score_desc', label: '按分数从高到低' },
  { id: 'score_asc', label: '按分数从低到高' },
  { id: 'time_desc', label: '按耗时从高到低' },
  { id: 'time_asc', label: '按耗时从低到高' },
  { id: 'latest', label: '按最近分析排序' },
];

const getResultDate = (result) => {
  const value = result?.snapshot?.saved_at;
  if (!value) return 0;
  const time = new Date(value).getTime();
  return Number.isFinite(time) ? time : 0;
};

const applyFilter = (result, filterId) => {
  if (filterId === 'low') {
    return getQualityBucket(result) === 'low';
  }
  if (SCREENING_RULES.some((rule) => rule.id === filterId)) {
    return matchesScreeningRule(result, filterId);
  }
  if (filterId === 'degraded') {
    return Boolean(result?.meta?.degraded);
  }
  if (filterId === 'semantic_issue') {
    return hasSemanticIssue(result);
  }
  return true;
};

const applySort = (items, sortId) => {
  const sorted = [...items];
  sorted.sort((left, right) => {
    const leftScore = getResultScore(left) ?? -1;
    const rightScore = getResultScore(right) ?? -1;
    const leftTime = getResultElapsedMs(left) ?? -1;
    const rightTime = getResultElapsedMs(right) ?? -1;
    const leftDate = getResultDate(left);
    const rightDate = getResultDate(right);

    if (sortId === 'score_asc') return leftScore - rightScore;
    if (sortId === 'score_desc') return rightScore - leftScore;
    if (sortId === 'time_asc') return leftTime - rightTime;
    if (sortId === 'time_desc') return rightTime - leftTime;
    return rightDate - leftDate;
  });
  return sorted;
};

const ResultsWorkspace = ({ results = [] }) => {
  const [viewMode, setViewMode] = useState('overview');
  const [filterId, setFilterId] = useState('all');
  const [sortId, setSortId] = useState('latest');
  const [searchTerm, setSearchTerm] = useState('');
  const [selectedResultId, setSelectedResultId] = useState(null);
  const [isDetailOpen, setIsDetailOpen] = useState(false);

  useEffect(() => {
    if (!results.length) {
      setSelectedResultId(null);
      setIsDetailOpen(false);
      return;
    }
    setSelectedResultId((prev) => (prev && results.some((item) => item.upload_id === prev) ? prev : results[0].upload_id));
  }, [results]);

  const stats = useMemo(() => {
    const scores = results.map((item) => getResultScore(item)).filter((value) => typeof value === 'number');
    const averageScore = scores.length ? scores.reduce((sum, value) => sum + value, 0) / scores.length : null;
    const lowQualityCount = results.filter((item) => getQualityBucket(item) === 'low').length;
    const degradedCount = results.filter((item) => item?.meta?.degraded).length;
    const semanticIssueCount = results.filter((item) => hasSemanticIssue(item)).length;
    const best = [...results]
      .filter((item) => getResultScore(item) != null)
      .sort((left, right) => (getResultScore(right) ?? -1) - (getResultScore(left) ?? -1))[0];
    const screening = SCREENING_RULES.map((rule) => ({
      ...rule,
      count: countScreeningMatches(results, rule.id),
    }));
    return {
      total: results.length,
      averageScore,
      lowQualityCount,
      degradedCount,
      semanticIssueCount,
      best,
      screening,
    };
  }, [results]);

  const filteredResults = useMemo(() => {
    const keyword = searchTerm.trim().toLowerCase();
    const matched = results.filter((result) => {
      if (!applyFilter(result, filterId)) {
        return false;
      }
      if (!keyword) {
        return true;
      }
      const filename = (result?.filename || '').toLowerCase();
      const caption = (result?.content?.caption || '').toLowerCase();
      return filename.includes(keyword) || caption.includes(keyword);
    });
    return applySort(matched, sortId);
  }, [results, filterId, searchTerm, sortId]);

  const selectedIndex = filteredResults.findIndex((item) => item.upload_id === selectedResultId);
  const selectedResult = selectedIndex >= 0 ? filteredResults[selectedIndex] : null;

  useEffect(() => {
    if (!selectedResultId) {
      return;
    }
    if (!filteredResults.length) {
      setSelectedResultId(null);
      setIsDetailOpen(false);
      return;
    }
    if (!filteredResults.some((item) => item.upload_id === selectedResultId)) {
      setSelectedResultId(filteredResults[0].upload_id);
    }
  }, [filteredResults, selectedResultId]);

  useEffect(() => {
    if (viewMode !== 'overview' && isDetailOpen) {
      setIsDetailOpen(false);
    }
  }, [isDetailOpen, viewMode]);

  const openResult = (resultId) => {
    setSelectedResultId(resultId);
    setIsDetailOpen(true);
  };
  const closeResult = () => setIsDetailOpen(false);
  const showPrev = selectedIndex > 0;
  const showNext = selectedIndex >= 0 && selectedIndex < filteredResults.length - 1;

  if (!results.length) {
    return null;
  }

  return (
    <>
      <section className="panel results-shell">
        <div className="results-header">
          <div className="results-title-group">
            <span className="result-kicker">Workspace</span>
            <h2>分析结果工作台</h2>
            <p className="muted">默认展示批量总览，点击任一结果可查看完整分析详情。</p>
          </div>
          <div className="results-view-toggle" role="tablist" aria-label="结果视图">
            <button
              type="button"
              className={viewMode === 'overview' ? 'secondary active' : 'ghost'}
              onClick={() => setViewMode('overview')}
            >
              总览模式
            </button>
            <button
              type="button"
              className={viewMode === 'expanded' ? 'secondary active' : 'ghost'}
              onClick={() => setViewMode('expanded')}
            >
              展开模式
            </button>
          </div>
        </div>

        <section className="results-top-grid">
          <div className="results-stats-grid">
            <article className="results-stat-card">
              <span>结果总数</span>
              <strong>{stats.total}</strong>
              <small>当前批次已完成分析的图片数量</small>
            </article>
            <article className="results-stat-card">
              <span>平均分</span>
              <strong>{stats.averageScore != null ? stats.averageScore.toFixed(1) : '--'}</strong>
              <small>用于快速判断整批图片的总体质量</small>
            </article>
            <article className="results-stat-card">
              <span>低分图片</span>
              <strong>{stats.lowQualityCount}</strong>
              <small>综合得分低于 60 分的图片</small>
            </article>
            <article className="results-stat-card accent">
              <span>最佳样本</span>
              <strong>{stats.best?.filename || '暂无'}</strong>
              <small>{stats.best ? `最高分 ${getResultScore(stats.best)?.toFixed(2)} / 100` : '等待结果'}</small>
            </article>
          </div>

          <section className="screening-panel">
            <div className="screening-panel-header">
              <div>
                <span className="result-kicker">Auto Screening</span>
                <h3>自动图像筛选</h3>
              </div>
              <p className="muted">面向数据集清洗和相册整理，一键定位低质量、模糊、噪声高与曝光异常图片。</p>
            </div>
            <div className="screening-grid">
              {stats.screening.map((rule) => {
                const active = filterId === rule.id;
                return (
                  <button
                    key={rule.id}
                    type="button"
                    className={active ? 'screening-card active' : 'screening-card'}
                    onClick={() => setFilterId(rule.id)}
                  >
                    <span className="screening-count">{rule.count}</span>
                    <strong>{rule.label}</strong>
                    <p>{rule.count ? `检测到 ${rule.count} 张` : rule.emptyText}</p>
                  </button>
                );
              })}
            </div>
          </section>
        </section>

        <div className="results-toolbar">
          <div className="results-filter-strip">
            {FILTERS.map((filter) => (
              <button
                key={filter.id}
                type="button"
                className={filter.id === filterId ? 'secondary active' : 'ghost'}
                onClick={() => setFilterId(filter.id)}
              >
                {filter.label}
              </button>
            ))}
          </div>
          <div className="results-toolbar-controls">
            <label className="results-search">
              <span className="sr-only">搜索结果</span>
              <input
                type="search"
                value={searchTerm}
                placeholder="按文件名或描述筛选"
                onChange={(event) => setSearchTerm(event.target.value)}
              />
            </label>
            <label className="results-sort">
              <span>排序</span>
              <select value={sortId} onChange={(event) => setSortId(event.target.value)}>
                {SORT_OPTIONS.map((option) => (
                  <option key={option.id} value={option.id}>
                    {option.label}
                  </option>
                ))}
              </select>
            </label>
          </div>
        </div>

        <div className="results-meta-row">
          <span className="hero-chip">语义异常：{stats.semanticIssueCount}</span>
          <span className="hero-chip">降级结果：{stats.degradedCount}</span>
          <span className="hero-chip">当前筛选后：{filteredResults.length}</span>
        </div>

        {viewMode === 'overview' ? (
          <div className="results-grid">
            {filteredResults.map((result) => {
              const score = getResultScore(result);
              const elapsed = getResultElapsedMs(result);
              const tags = getPrimaryTags(result);
              return (
                <button
                  key={result.upload_id}
                  type="button"
                  className="result-overview-card"
                  onClick={() => openResult(result.upload_id)}
                >
                  <div className="result-overview-media">
                    <div className="result-overview-media-frame">
                      {result?.snapshot?.thumbnail ? (
                        <img src={result.snapshot.thumbnail} alt={result.filename || result.upload_id} loading="lazy" />
                      ) : (
                        <div className="result-overview-fallback">无缩略图</div>
                      )}
                    </div>
                    <span className={`result-overview-grade bucket-${getQualityBucket(result)}`}>
                      {result?.quality?.level || '未评级'}
                    </span>
                  </div>
                  <div className="result-overview-body">
                    <div className="result-overview-head">
                      <strong title={result.filename || result.upload_id}>{result.filename || result.upload_id}</strong>
                      <span>{score != null ? `${score.toFixed(2)} / 100` : '--'}</span>
                    </div>
                    <p className="result-overview-summary">{getResultSummary(result)}</p>
                    <div className="tag-list result-overview-tags">
                      {tags.map((tag) => (
                        <span key={`${result.upload_id}-${tag}`} className="tag-chip">
                          {tag}
                        </span>
                      ))}
                    </div>
                    <div className="result-overview-meta">
                      <span>{formatElapsed(elapsed)}</span>
                      <span>{formatTimestamp(result?.snapshot?.saved_at)}</span>
                    </div>
                  </div>
                </button>
              );
            })}
          </div>
        ) : (
          <div className="results-expanded-list">
            {filteredResults.map((item) => (
              <ResultCard key={item.upload_id} result={item} />
            ))}
          </div>
        )}

        {!filteredResults.length && (
          <div className="results-empty">
            <p>当前筛选条件下没有结果。</p>
            <span className="muted">可以切换筛选、排序，或者清空搜索关键词。</span>
          </div>
        )}
      </section>

      {isDetailOpen && selectedResult && viewMode === 'overview' && (
        <div className="modal-backdrop" role="presentation" onClick={closeResult}>
          <div
            className="modal-panel result-detail-panel"
            role="dialog"
            aria-modal="true"
            aria-label="分析结果详情"
            onClick={(event) => event.stopPropagation()}
          >
            <div className="result-detail-toolbar">
              <div className="result-detail-nav">
                <button type="button" className="ghost" onClick={() => openResult(filteredResults[selectedIndex - 1]?.upload_id)} disabled={!showPrev}>
                  上一张
                </button>
                <button type="button" className="ghost" onClick={() => openResult(filteredResults[selectedIndex + 1]?.upload_id)} disabled={!showNext}>
                  下一张
                </button>
              </div>
              <button type="button" className="ghost" onClick={closeResult}>
                关闭详情
              </button>
            </div>
            <ResultCard result={selectedResult} />
          </div>
        </div>
      )}
    </>
  );
};

export default ResultsWorkspace;
