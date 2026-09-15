const HISTORY_CACHE_KEY = 'iqa_history_cache_v2';
const HISTORY_CACHE_LIMIT = 10;

const hasStorage = () => typeof window !== 'undefined' && !!window.localStorage;

export const loadHistoryCache = () => {
  if (!hasStorage()) return [];
  try {
    const raw = window.localStorage.getItem(HISTORY_CACHE_KEY);
    if (!raw) return [];
    const parsed = JSON.parse(raw);
    return Array.isArray(parsed) ? parsed : [];
  } catch (error) {
    console.warn('读取历史缓存失败', error);
    return [];
  }
};

export const saveHistoryCache = (items = []) => {
  if (!hasStorage()) return;
  try {
    const slice = items.slice(0, HISTORY_CACHE_LIMIT);
    window.localStorage.setItem(HISTORY_CACHE_KEY, JSON.stringify(slice));
  } catch (error) {
    console.warn('写入历史缓存失败', error);
  }
};

export const clearHistoryCache = () => {
  if (!hasStorage()) return;
  try {
    window.localStorage.removeItem(HISTORY_CACHE_KEY);
  } catch (error) {
    console.warn('清理历史缓存失败', error);
  }
};
