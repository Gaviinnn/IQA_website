import { useEffect, useMemo, useState } from 'react';

const EMPTY_FORM = {
  profile_id: '',
  name: '',
  provider_id: 'openai',
  base_url: '',
  model: '',
  api_key: '',
  api_version: '',
  organization: '',
  region: '',
};

const ProviderPanel = ({
  presets = [],
  profiles = [],
  activeProfileId,
  loading = false,
  onClose,
  onSave,
  onActivate,
  onDelete,
  onTest,
  onRefresh,
}) => {
  const [form, setForm] = useState(EMPTY_FORM);
  const [statusText, setStatusText] = useState('');
  const selectedPreset = useMemo(
    () => presets.find((item) => item.id === form.provider_id) || presets[0] || null,
    [form.provider_id, presets]
  );

  useEffect(() => {
    if (!selectedPreset) return;
    setForm((prev) => ({
      ...prev,
      base_url: prev.base_url || selectedPreset.default_base_url || '',
      model: prev.model || selectedPreset.default_model || '',
    }));
  }, [selectedPreset]);

  const resetForm = () => {
    const fallbackPreset = presets[0];
    setForm({
      ...EMPTY_FORM,
      provider_id: fallbackPreset?.id || 'openai',
      base_url: fallbackPreset?.default_base_url || '',
      model: fallbackPreset?.default_model || '',
    });
    setStatusText('');
  };

  const startEdit = (profile) => {
    if (!profile) return;
    setForm({
      profile_id: profile.profile_id || '',
      name: profile.name || '',
      provider_id: profile.provider_id || 'openai',
      base_url: profile.base_url || '',
      model: profile.model || '',
      api_key: '',
      api_version: profile.api_version || '',
      organization: profile.organization || '',
      region: profile.region || '',
    });
    setStatusText(`正在编辑：${profile.name}`);
  };

  const submit = async (event) => {
    event.preventDefault();
    setStatusText('');
    await onSave?.(form, setStatusText, resetForm);
  };

  return (
    <section className="provider-panel-shell">
      <div className="provider-panel-header">
        <div>
          <h2>模型配置中心</h2>
          <p className="muted">保存云厂商 Provider Profile，切换当前系统使用的模型供应商。</p>
        </div>
        <div className="provider-panel-toolbar">
          <button type="button" className="ghost" onClick={onRefresh} disabled={loading}>
            {loading ? '刷新中...' : '刷新'}
          </button>
          <button type="button" className="ghost" onClick={onClose}>
            关闭
          </button>
        </div>
      </div>

      <div className="provider-layout">
        <form className="provider-form" onSubmit={submit}>
          <div className="provider-grid">
            <label>
              <span>配置名称</span>
              <input
                value={form.name}
                onChange={(event) => setForm((prev) => ({ ...prev, name: event.target.value }))}
                placeholder="例如：实验用 Qwen"
                required
              />
            </label>

            <label>
              <span>厂商预设</span>
              <select
                value={form.provider_id}
                onChange={(event) => {
                  const nextId = event.target.value;
                  const preset = presets.find((item) => item.id === nextId);
                  setForm((prev) => ({
                    ...prev,
                    provider_id: nextId,
                    base_url: preset?.default_base_url || '',
                    model: preset?.default_model || '',
                  }));
                }}
              >
                {presets.map((preset) => (
                  <option key={preset.id} value={preset.id}>
                    {preset.label}
                  </option>
                ))}
              </select>
            </label>

            <label className="span-2">
              <span>Base URL</span>
              <input
                value={form.base_url}
                onChange={(event) => setForm((prev) => ({ ...prev, base_url: event.target.value }))}
                placeholder={selectedPreset?.default_base_url || 'https://api.example.com/v1'}
              />
            </label>

            <label>
              <span>模型名 / Deployment</span>
              <input
                value={form.model}
                onChange={(event) => setForm((prev) => ({ ...prev, model: event.target.value }))}
                placeholder={selectedPreset?.default_model || 'model-name'}
                required
              />
            </label>

            <label>
              <span>API Key</span>
              <input
                type="password"
                value={form.api_key}
                onChange={(event) => setForm((prev) => ({ ...prev, api_key: event.target.value }))}
                placeholder="留空则保留已保存的 key"
              />
            </label>

            <label>
              <span>API Version</span>
              <input
                value={form.api_version}
                onChange={(event) => setForm((prev) => ({ ...prev, api_version: event.target.value }))}
                placeholder="Azure / Anthropic 可选"
              />
            </label>

            <label>
              <span>Organization</span>
              <input
                value={form.organization}
                onChange={(event) => setForm((prev) => ({ ...prev, organization: event.target.value }))}
                placeholder="OpenAI 组织 ID，可选"
              />
            </label>

            <label>
              <span>Region</span>
              <input
                value={form.region}
                onChange={(event) => setForm((prev) => ({ ...prev, region: event.target.value }))}
                placeholder="云区域，可选"
              />
            </label>
          </div>

          {selectedPreset?.docs_url && (
            <p className="muted">
              官方文档：
              <a href={selectedPreset.docs_url} target="_blank" rel="noreferrer">
                {selectedPreset.docs_url}
              </a>
            </p>
          )}

          {statusText && <p className="hint">{statusText}</p>}

          <div className="actions">
            <button type="button" className="secondary" onClick={resetForm} disabled={loading}>
              新建
            </button>
            <button type="submit" className="primary" disabled={loading}>
              {form.profile_id ? '保存配置' : '创建配置'}
            </button>
          </div>
        </form>

        <div className="provider-list">
          <div className="provider-list-header">
            <strong>已保存配置</strong>
            <span className="muted">当前活跃配置会用于语义分析和质量解释。</span>
          </div>

          {!profiles.length && <p className="muted">暂无 Provider Profile。</p>}

          {profiles.map((profile) => (
            <article key={profile.profile_id} className={['provider-card', profile.profile_id === activeProfileId ? 'active' : ''].join(' ').trim()}>
              <div className="provider-card-head">
                <div>
                  <h3>{profile.name}</h3>
                  <p className="muted">
                    {profile.provider_id} | {profile.model}
                  </p>
                </div>
                {profile.profile_id === activeProfileId && <span className="provider-badge">已启用</span>}
              </div>

              <p className="muted provider-card-url">{profile.base_url || '使用厂商默认地址'}</p>
              {profile.api_key_masked && <p className="muted">API Key: {profile.api_key_masked}</p>}

              <div className="provider-card-actions">
                <button type="button" className="ghost" onClick={() => startEdit(profile)} disabled={loading}>
                  编辑
                </button>
                <button
                  type="button"
                  className="ghost"
                  onClick={() => onTest?.(profile.profile_id, setStatusText)}
                  disabled={loading}
                >
                  测试
                </button>
                <button
                  type="button"
                  className="ghost"
                  onClick={() => onActivate?.(profile.profile_id, setStatusText)}
                  disabled={loading || profile.profile_id === activeProfileId}
                >
                  启用
                </button>
                <button
                  type="button"
                  className="ghost danger"
                  onClick={() => onDelete?.(profile.profile_id, setStatusText)}
                  disabled={loading}
                >
                  删除
                </button>
              </div>
            </article>
          ))}
        </div>
      </div>
    </section>
  );
};

export default ProviderPanel;
