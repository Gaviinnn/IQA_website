const LABELS = {
  waiting: '等待上传',
  uploading: '上传中',
  analyzing: 'AI 思考中',
  completed: '已完成',
  failed: '失败',
};

const ProgressBar = ({ progress = 0, status = 'waiting' }) => {
  const statusLabel = LABELS[status] || LABELS.waiting;

  return (
    <div className="progress-bar">
      <div className="progress-head">
        <span className="progress-state">{statusLabel}</span>
        <span className="progress-value">{Math.round(progress)}%</span>
      </div>
      <div className="progress-track">
        <div className="progress-fill" style={{ width: `${Math.min(100, Math.max(0, progress))}%` }} />
      </div>
    </div>
  );
};

export default ProgressBar;
