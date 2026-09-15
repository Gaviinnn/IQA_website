import Zoom from 'react-medium-image-zoom';
import 'react-medium-image-zoom/dist/styles.css';

import { API_BASE_URL, resolveAssetUrl } from '../utils/api.js';
import { formatTimestamp, getJudgeIssueTags, labelValue } from '../utils/resultPresentation.js';

const normalizeImageUrl = (filename, snapshot) => {
  if (snapshot?.image) {
    return resolveAssetUrl(snapshot.image);
  }

  const base = API_BASE_URL.replace(/\/$/, '');
  if (filename) {
    return `${base}/uploads/${filename}`;
  }

  if (snapshot?.thumbnail) {
    return resolveAssetUrl(snapshot.thumbnail);
  }

  return null;
};

const formatScoreValue = (value) => (typeof value === 'number' ? value : '--');

const ResultCard = ({ result }) => {
  if (!result) {
    return null;
  }

  const {
    upload_id: uploadId,
    filename,
    quality,
    quality_evidence: qualityEvidence,
    quality_judge: qualityJudge,
    quality_fusion: qualityFusion,
    diagnostics,
    content,
    semantic,
    meta,
    snapshot,
  } = result;
  const inferenceMs = meta?.elapsed_ms ?? meta?.inference_ms;
  const originalImage = normalizeImageUrl(filename, snapshot);
  const previewSrc = originalImage || (snapshot?.thumbnail ? resolveAssetUrl(snapshot.thumbnail) : null);
  const displayScore = qualityFusion?.final_score ?? quality?.score;
  const judgeTags = getJudgeIssueTags(result);

  return (
    <section className="result-card">
      <header className="result-header">
        <div className="result-title-group">
          <span className="result-kicker">Analysis</span>
          <h2>{filename || uploadId}</h2>
          {snapshot?.saved_at && <p className="muted">分析时间：{formatTimestamp(snapshot.saved_at)}</p>}
        </div>
        <div className="result-score-badge">
          {displayScore != null && <strong>{displayScore}</strong>}
          {inferenceMs && <span className="meta">耗时 {inferenceMs} ms</span>}
        </div>
      </header>

      {previewSrc && (
        <div className="result-thumbnail">
          <Zoom zoomMargin={24} overlayBgColorEnd="rgba(15, 23, 42, 0.8)" zoomImg={{ src: originalImage || previewSrc }}>
            <img src={previewSrc} alt={filename || uploadId} loading="lazy" />
          </Zoom>
        </div>
      )}

      {(quality || qualityFusion) && (
        <div className="result-block highlight">
          <h3>{qualityFusion ? '融合质量评审' : '图像质量'}</h3>
          <p className="score">
            综合得分：<strong>{displayScore ?? '--'} / 100</strong>
          </p>
          {qualityFusion?.level ? <p>等级：{qualityFusion.level}</p> : quality?.level ? <p>等级：{quality.level}</p> : null}
          {qualityFusion ? (
            <div className="result-metrics">
              <span>基础评分：{formatScoreValue(qualityFusion.base_score)}</span>
              <span>技术质量分：{formatScoreValue(qualityFusion.technical_score)}</span>
              <span>审阅分：{formatScoreValue(qualityFusion.judge_score)}</span>
              <span>置信度：{labelValue(qualityFusion.confidence)}</span>
            </div>
          ) : null}
          {qualityFusion?.reason ? <p className="muted">{qualityFusion.reason}</p> : null}
          {quality?.explanation && <p className="muted">{quality.explanation}</p>}
        </div>
      )}

      {qualityEvidence && (
        <div className="result-block">
          <h3>质量证据</h3>
          <p className="muted">{qualityEvidence.summary}</p>
          <div className="pill-list">
            <span className="pill">清晰度：{formatScoreValue(qualityEvidence.factor_scores?.blur)}</span>
            <span className="pill">噪声控制：{formatScoreValue(qualityEvidence.factor_scores?.noise)}</span>
            <span className="pill">曝光表现：{formatScoreValue(qualityEvidence.factor_scores?.exposure)}</span>
            <span className="pill">对比度：{formatScoreValue(qualityEvidence.factor_scores?.contrast)}</span>
            <span className="pill">压缩影响：{formatScoreValue(qualityEvidence.factor_scores?.compression)}</span>
          </div>
        </div>
      )}

      {qualityJudge && (
        <div className="result-block">
          <h3>LLM 质量审阅</h3>
          <p className="muted">{qualityJudge.reason}</p>
          <div className="pill-list">
            <span className="pill">清晰度：{qualityJudge.sharpness_score ?? '--'}</span>
            <span className="pill">噪声控制：{qualityJudge.noise_score ?? '--'}</span>
            <span className="pill">曝光表现：{qualityJudge.exposure_score ?? '--'}</span>
            <span className="pill">对比度：{qualityJudge.contrast_score ?? '--'}</span>
            <span className="pill">压缩影响：{qualityJudge.compression_score ?? '--'}</span>
          </div>
          <div className="result-metrics">
            <span>综合审阅分：{formatScoreValue(qualityJudge.overall_quality_score)}</span>
            <span>审阅置信度：{labelValue(qualityJudge.confidence)}</span>
          </div>
          {judgeTags.length ? (
            <div className="tag-list">
              {judgeTags.map((issue) => (
                <span key={`${uploadId}-${issue}`} className="tag-chip">
                  {issue}
                </span>
              ))}
            </div>
          ) : null}
        </div>
      )}

      {diagnostics && (
        <div className="result-block">
          <h3>技术证据</h3>
          <p className="muted">以下诊断结果用于解释质量下降原因，并作为融合评分的辅助证据。</p>
          <div className="pill-list">
            <span className="pill">模糊：{labelValue(diagnostics.blur)}</span>
            <span className="pill">噪声：{labelValue(diagnostics.noise)}</span>
            <span className="pill">曝光：{labelValue(diagnostics.exposure)}</span>
            <span className="pill">对比度：{labelValue(diagnostics.contrast)}</span>
            <span className="pill">压缩痕迹：{labelValue(diagnostics.compression_artifacts)}</span>
          </div>
          {diagnostics.metrics && (
            <div className="result-metrics">
              <span>模糊评分：{formatScoreValue(diagnostics.metrics.blur_score)}</span>
              <span>亮度均值：{formatScoreValue(diagnostics.metrics.brightness_mean)}</span>
              <span>对比度统计：{formatScoreValue(diagnostics.metrics.contrast_std)}</span>
              <span>噪声评分：{formatScoreValue(diagnostics.metrics.noise_score)}</span>
              <span>压缩评分：{formatScoreValue(diagnostics.metrics.compression_score)}</span>
            </div>
          )}
        </div>
      )}

      {content && (
        <div className="result-block">
          <h3>内容识别</h3>
          {content.caption ? <p>{content.caption}</p> : <p className="muted">未检索到描述</p>}
          <p className="muted confidence-note">模型置信度（score）用于解释识别结果的可信程度。</p>
          {content.objects?.length ? (
            <ul className="object-list">
              {content.objects.map((item) => (
                <li key={`${uploadId}-${item.label}`}>
                  <span>{item.label}</span>
                  <span className="muted">{Math.round((item.score ?? 0) * 100)}%</span>
                </li>
              ))}
            </ul>
          ) : (
            <p className="muted">暂无识别目标</p>
          )}
        </div>
      )}

      {semantic && (
        <div className="result-block">
          <h3>语义增强</h3>
          <div className="pill-list">
            <span className="pill">场景：{labelValue(semantic.scene)}</span>
            <span className="pill">目标数：{semantic.object_count ?? '--'}</span>
            <span className="pill">复杂度：{labelValue(semantic.complexity)}</span>
            <span className="pill">场景杂乱度：{labelValue(semantic.scene_clutter)}</span>
          </div>
          {semantic.semantic_tags?.length ? (
            <div className="tag-list">
              {semantic.semantic_tags.map((tag) => (
                <span key={`${uploadId}-${tag}`} className="tag-chip">
                  {tag}
                </span>
              ))}
            </div>
          ) : (
            <p className="muted">暂无语义标签</p>
          )}
        </div>
      )}

      {meta && (
        <footer className="result-footer">
          <div>质量模型：{meta.models?.quality || 'MANIQA v1.2'}</div>
          {meta.models?.quality_judge && <div>审阅模型：{meta.models.quality_judge}</div>}
          <div>内容模型：{meta.models?.content || 'Doubao Vision'}</div>
          {meta.models?.diagnostics && <div>诊断模块：{meta.models.diagnostics}</div>}
          <div>分析粒度：{meta.detail}</div>
          {meta.skill_order?.length ? <div>技能链：{meta.skill_order.join(' → ')}</div> : null}
          {meta.degraded && <div className="warning">结果可能不完整：{meta.reason || '推理降级'}</div>}
        </footer>
      )}
    </section>
  );
};

export default ResultCard;
