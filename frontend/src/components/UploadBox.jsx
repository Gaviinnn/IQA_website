import { useEffect, useMemo, useRef, useState } from 'react';

const ACCEPTED_TYPES = ['image/jpeg', 'image/png', 'image/webp'];
const MAX_SIZE_MB = 20;
const getFileKey = (file) => `${file.name}_${file.size}_${file.lastModified}`;

const UploadBox = ({
  onUpload,
  isUploading,
  status = 'waiting',
  skills = [],
  selectedSkills = [],
  onToggleSkill,
  autoSubmit = false,
  hideActions = false,
}) => {
  const inputRef = useRef(null);
  const pendingAutoSubmitRef = useRef(false);
  const [files, setFiles] = useState([]);
  const [previews, setPreviews] = useState([]);
  const [error, setError] = useState('');
  const [isDragActive, setIsDragActive] = useState(false);

  useEffect(() => {
    return () => {
      previews.forEach((preview) => URL.revokeObjectURL(preview.url));
    };
  }, [previews]);

  const reset = () => {
    previews.forEach((preview) => URL.revokeObjectURL(preview.url));
    setFiles([]);
    setPreviews([]);
    setError('');
    pendingAutoSubmitRef.current = false;
    if (inputRef.current) {
      inputRef.current.value = '';
    }
  };

  const validateFile = (candidate) => {
    if (!candidate) {
      return '请选择图片文件';
    }
    if (!ACCEPTED_TYPES.includes(candidate.type)) {
      return '仅支持 JPG / PNG / WEBP 图片';
    }
    if (candidate.size > MAX_SIZE_MB * 1024 * 1024) {
      return `单个文件不得超过 ${MAX_SIZE_MB} MB`;
    }
    return '';
  };

  const preparePreviews = (items) =>
    items.map((file) => ({
      id: getFileKey(file),
      url: URL.createObjectURL(file),
      name: file.name,
    }));

  const handleFiles = (fileList, mode = 'replace') => {
    const candidates = Array.from(fileList || []);
    if (!candidates.length) {
      if (mode === 'replace') {
        reset();
      }
      return;
    }

    const existing = mode === 'append' ? files : [];
    const valid = [];
    let firstError = '';
    const seenKeys = new Set(existing.map(getFileKey));

    candidates.forEach((file) => {
      const message = validateFile(file);
      if (message) {
        if (!firstError) {
          firstError = `${file.name}: ${message}`;
        }
      } else {
        const fileKey = getFileKey(file);
        if (seenKeys.has(fileKey)) {
          if (!firstError) {
            firstError = `${file.name}: 已在当前列表中`;
          }
          return;
        }
        seenKeys.add(fileKey);
        valid.push(file);
      }
    });

    previews.forEach((preview) => URL.revokeObjectURL(preview.url));

    const nextFiles = [...existing, ...valid];

    setFiles(nextFiles);
    setPreviews(preparePreviews(nextFiles));
    setError(firstError);
    pendingAutoSubmitRef.current = autoSubmit && nextFiles.length > 0 && !firstError;
  };

  const handleChange = (event) => {
    handleFiles(event.target.files, files.length ? 'append' : 'replace');
    if (inputRef.current) {
      inputRef.current.value = '';
    }
  };

  const handleDrop = (event) => {
    event.preventDefault();
    setIsDragActive(false);
    handleFiles(event.dataTransfer?.files, files.length ? 'append' : 'replace');
  };

  const handleDragOver = (event) => {
    event.preventDefault();
    if (!isDragActive) {
      setIsDragActive(true);
    }
  };

  const handleDragLeave = (event) => {
    event.preventDefault();
    const nextTarget = event.relatedTarget;
    if (event.currentTarget.contains(nextTarget)) {
      return;
    }
    setIsDragActive(false);
  };

  const handleRemoveFile = (fileKey) => {
    const nextFiles = files.filter((file) => getFileKey(file) !== fileKey);
    previews.forEach((preview) => URL.revokeObjectURL(preview.url));
    setFiles(nextFiles);
    setPreviews(preparePreviews(nextFiles));
    setError('');
    pendingAutoSubmitRef.current = false;
    if (!nextFiles.length && inputRef.current) {
      inputRef.current.value = '';
    }
  };

  const handleSubmit = async (event) => {
    event.preventDefault();
    if (!files.length || isUploading) {
      return;
    }
    pendingAutoSubmitRef.current = false;
    await onUpload(files, reset);
  };

  useEffect(() => {
    if (!autoSubmit || !pendingAutoSubmitRef.current || !files.length || isUploading) {
      return;
    }
    pendingAutoSubmitRef.current = false;
    onUpload(files, reset);
  }, [autoSubmit, files, isUploading, onUpload]);

  const summary = useMemo(() => {
    if (!files.length) {
      return '支持批量上传，可拖拽补充图片并逐个移除';
    }
    if (files.length === 1) {
      return `已选择 1 张图片：${files[0].name}`;
    }
    return `已选择 ${files.length} 张图片，可继续拖入或点击补充`;
  }, [files]);

  const firstPreview = previews[0];
  const extraCount = previews.length > 1 ? previews.length - 1 : 0;

  return (
    <form className="upload-box" onSubmit={handleSubmit}>
      <div
        className={[
          'drop-zone',
          previews.length ? 'has-preview' : '',
          isUploading ? 'is-uploading' : '',
          isDragActive ? 'drag-active' : '',
        ]
          .join(' ')
          .trim()}
        onDrop={handleDrop}
        onDragOver={handleDragOver}
        onDragLeave={handleDragLeave}
        role="presentation"
        onClick={() => inputRef.current?.click()}
      >
        {firstPreview ? (
          <div className="preview-wrapper">
            <img src={firstPreview.url} alt="预览图" className="preview-image" />
            {extraCount > 0 && <span className="preview-count">+{extraCount}</span>}
            <div className="preview-overlay">
              <strong>{files.length > 1 ? `已选 ${files.length} 张` : '已选 1 张'}</strong>
              <span>点击或拖入更多图片继续补充</span>
            </div>
          </div>
        ) : (
          <div className="placeholder">
            <strong>拖拽或点击上传图片</strong>
            <span>支持 JPG / PNG / WEBP，单张不超过 {MAX_SIZE_MB} MB</span>
          </div>
        )}
      </div>

      <input
        ref={inputRef}
        type="file"
        accept={ACCEPTED_TYPES.join(',')}
        multiple
        onChange={handleChange}
        hidden
      />

      {error && <p className="hint error">{error}</p>}
      {!error && <p className="hint">{summary}</p>}

      {skills.length > 0 && (
        <div className="skill-panel">
          <div className="skill-panel-header">
            <strong>执行技能</strong>
            <span className="muted">至少保留一个技能</span>
          </div>
          <div className="skill-grid">
            {skills.map((skill) => {
              const checked = selectedSkills.includes(skill.id);
              return (
                <label key={skill.id} className={['skill-option', checked ? 'selected' : ''].join(' ').trim()}>
                  <input
                    type="checkbox"
                    checked={checked}
                    onChange={() => onToggleSkill?.(skill.id)}
                  />
                  <div>
                    <span>{skill.label || skill.id}</span>
                    <small>{skill.description}</small>
                  </div>
                </label>
              );
            })}
          </div>
        </div>
      )}

      {files.length > 0 && (
        <ul className="file-list">
          {files.map((file) => (
            <li key={getFileKey(file)}>
              <div className="file-item-meta">
                <span>{file.name}</span>
                <span className="muted">{Math.round(file.size / 1024)} KB</span>
              </div>
              <button
                type="button"
                className="file-remove"
                onClick={() => handleRemoveFile(getFileKey(file))}
                disabled={isUploading}
              >
                移除
              </button>
            </li>
          ))}
        </ul>
      )}

      {!hideActions && (
        <div className="actions">
          <button type="button" className="secondary" onClick={reset} disabled={isUploading}>
            清空选择
          </button>
          <button type="submit" className="primary" disabled={!files.length || isUploading}>
            {isUploading ? (status === 'analyzing' ? 'AI 思考中...' : '上传中...') : '上传并分析'}
          </button>
        </div>
      )}
    </form>
  );
};

export default UploadBox;
