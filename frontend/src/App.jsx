import { useEffect, useState } from 'react';

import Home from './pages/Home.jsx';
import FilterStudio from './pages/FilterStudio.jsx';

const getPageFromHash = () => {
  const hash = window.location.hash.replace(/^#/, '');
  if (hash === '/filter' || hash === 'filter') {
    return 'filter';
  }
  return 'analysis';
};

const App = () => {
  const [page, setPage] = useState(getPageFromHash());

  useEffect(() => {
    const onHashChange = () => setPage(getPageFromHash());
    window.addEventListener('hashchange', onHashChange);
    return () => window.removeEventListener('hashchange', onHashChange);
  }, []);

  return (
    <>
      <header className="app-nav">
        <div className="app-nav-inner">
          <span className="hero-eyebrow">IQA Platform</span>
          <div className="results-view-toggle">
            <button
              type="button"
              className={page === 'analysis' ? 'secondary active' : 'ghost'}
              onClick={() => {
                window.location.hash = '/analysis';
                setPage('analysis');
              }}
            >
              分析工作台
            </button>
            <button
              type="button"
              className={page === 'filter' ? 'secondary active' : 'ghost'}
              onClick={() => {
                window.location.hash = '/filter';
                setPage('filter');
              }}
            >
              筛选工作台
            </button>
          </div>
        </div>
      </header>
      <div className={page === 'analysis' ? 'workspace-view active' : 'workspace-view hidden'} aria-hidden={page !== 'analysis'}>
        <Home />
      </div>
      <div className={page === 'filter' ? 'workspace-view active' : 'workspace-view hidden'} aria-hidden={page !== 'filter'}>
        <FilterStudio />
      </div>
    </>
  );
};

export default App;

