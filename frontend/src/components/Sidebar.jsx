import { useMemo, useState } from 'react';

const formatTimestamp = (value) => {
  if (!value) return '';
  try {
    return new Date(value).toLocaleString();
  } catch (error) {
    return value;
  }
};

const Sidebar = ({
  items = [],
  loading = false,
  activeBatchId = null,
  onRefresh,
  onLoadMore,
  onDelete,
  onOpen,
  onClearAll,
  hasMore = false,
}) => {
  const [searchTerm, setSearchTerm] = useState('');
  const hasItems = Array.isArray(items) && items.length > 0;
  const normalizedKeyword = searchTerm.trim().toLowerCase();
  const visibleItems = useMemo(() => {
    if (!normalizedKeyword) {
      return items;
    }
    return items.filter((item) => {
      const filename = `${item.filename || ''}`.toLowerCase();
      const caption = `${item.caption || ''}`.toLowerCase();
      const batchId = `${item.batch_id || ''}`.toLowerCase();
      return filename.includes(normalizedKeyword) || caption.includes(normalizedKeyword) || batchId.includes(normalizedKeyword);
    });
  }, [items, normalizedKeyword]);
  const showEmptyState = !hasItems && !loading;
  const showSearchEmpty = hasItems && !visibleItems.length;

  return (
    <aside className="sidebar">
      <header className="sidebar-header">
        <div>
          <span className="sidebar-kicker">History</span>
          <h3>历史记录</h3>
          <p className="muted sidebar-summary">{hasItems ? `共 ${items.length} 个批次` : '可随时回看已完成的分析批次'}</p>
        </div>
        <div className="sidebar-actions">
          <button type="button" className="ghost" onClick={onRefresh} disabled={loading}>
            {loading ? '刷新中...' : '刷新'}
          </button>
          <button
            type="button"
            className="ghost danger"
            onClick={() => onClearAll?.()}
            disabled={loading || !hasItems}
          >
            清空
          </button>
        </div>
      </header>

      <div className="sidebar-body">
        {hasItems && (
          <label className="sidebar-search">
            <span className="sr-only">搜索历史记录</span>
            <input
              type="search"
              value={searchTerm}
              onChange={(event) => setSearchTerm(event.target.value)}
              placeholder="按文件名、摘要或批次搜索"
            />
          </label>
        )}

        {showEmptyState && (
          <div className="sidebar-empty" role="status">
            <div className="sidebar-empty-icon" aria-hidden="true">
              <svg width="56" height="56" viewBox="0 0 56 56" fill="none">
                <rect x="5" y="12" width="46" height="34" rx="8" fill="url(#sidebar-empty-gradient)" />
                <path d="M18 20H38" stroke="#9BA7D6" strokeWidth="2" strokeLinecap="round" strokeOpacity="0.8" />
                <path d="M14 26H42" stroke="#9BA7D6" strokeWidth="2" strokeLinecap="round" strokeOpacity="0.5" />
                <path d="M14 32H30" stroke="#9BA7D6" strokeWidth="2" strokeLinecap="round" strokeOpacity="0.35" />
                <defs>
                  <linearGradient
                    id="sidebar-empty-gradient"
                    x1="5"
                    y1="12"
                    x2="40"
                    y2="54"
                    gradientUnits="userSpaceOnUse"
                  >
                    <stop stopColor="#EEF3FF" />
                    <stop offset="1" stopColor="#F5F8FF" />
                  </linearGradient>
                </defs>
              </svg>
            </div>
            <p>暂无记录</p>
            <span className="muted">上传图片后可查看历史记录</span>
          </div>
        )}

        {showSearchEmpty && (
          <div className="sidebar-empty sidebar-empty-compact" role="status">
            <p>没有匹配的历史记录</p>
            <span className="muted">可以换个关键词，或清空搜索后继续浏览</span>
          </div>
        )}

        {visibleItems.length > 0 && (
          <ul className="sidebar-list">
            {visibleItems.map((item) => (
              <li
                key={item.batch_id}
                className={['sidebar-item', activeBatchId === item.batch_id ? 'active' : ''].join(' ').trim()}
              >
                <button type="button" className="sidebar-thumb sidebar-open" onClick={() => onOpen?.(item.batch_id)} disabled={loading}>
                  {item.thumbnail ? (
                    <img src={item.thumbnail} alt={item.filename || item.batch_id} />
                  ) : (
                    <span className="thumb-placeholder">无图</span>
                  )}
                </button>
                <button
                  type="button"
                  className="sidebar-info sidebar-open"
                  onClick={() => onOpen?.(item.batch_id)}
                  disabled={loading}
                >
                  <strong className="sidebar-title" title={item.filename || item.batch_id}>
                    {item.filename || item.batch_id}
                  </strong>
                  <div className="sidebar-meta">
                    <span className="muted">
                      {item.item_count > 1 ? `平均分：${item.avg_score ?? '--'}` : `评分：${item.avg_score ?? '--'}`}
                    </span>
                    <span className="muted">{item.item_count || 1} 张</span>
                    <time>{formatTimestamp(item.timestamp)}</time>
                  </div>
                  {item.caption && <p className="sidebar-caption">{item.caption}</p>}
                </button>
                <button
                  type="button"
                  className="link danger"
                  onClick={() => onDelete?.(item.batch_id)}
                  disabled={loading}
                >
                  删除
                </button>
              </li>
            ))}
          </ul>
        )}

        {loading && <p className="muted">加载中...</p>}
      </div>

      {hasMore && hasItems && (
        <button type="button" className="secondary full" onClick={onLoadMore} disabled={loading}>
          加载更多
        </button>
      )}
    </aside>
  );
};

export default Sidebar;
