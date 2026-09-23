import { AlertTriangle, Clock3, Gauge, Link2Off, LoaderCircle, Save, ShieldCheck, Trash2 } from "lucide-react";
import { useEffect, useState } from "react";
import { useAuth } from "../auth/AuthContext";
import {
  deleteFamilySpace, getFamilyMetrics, getPrivacySettings, listShares, revokeShare,
  updatePrivacySettings, type FamilyMetrics, type PrivacySettings, type Share,
} from "../services/lifecycleApi";

function percent(value: number | null) {
  return value === null ? "暂无样本" : `${Math.round(value * 1000) / 10}%`;
}

export function PrivacyPage() {
  const { session, logout } = useAuth();
  const [settings, setSettings] = useState<PrivacySettings | null>(null);
  const [shares, setShares] = useState<Share[]>([]);
  const [metrics, setMetrics] = useState<FamilyMetrics | null>(null);
  const [familyName, setFamilyName] = useState("");
  const [busy, setBusy] = useState(false);
  const [message, setMessage] = useState("");
  const [error, setError] = useState("");

  const load = () => Promise.all([getPrivacySettings(), listShares(), getFamilyMetrics()])
    .then(([nextSettings, nextShares, nextMetrics]) => {
      setSettings(nextSettings); setShares(nextShares); setMetrics(nextMetrics);
    });

  useEffect(() => { void load().catch(() => setError("隐私设置暂时无法读取。")); }, []);

  const save = async () => {
    if (!settings) return;
    setBusy(true); setError(""); setMessage("");
    try {
      setSettings(await updatePrivacySettings({
        recording_retention_days: settings.recording_retention_days,
        share_default_hours: settings.share_default_hours,
        sharing_enabled: settings.sharing_enabled,
      }));
      setMessage("隐私设置已保存。");
      setShares(await listShares());
    } catch { setError("设置没有保存，请重试。"); }
    finally { setBusy(false); }
  };

  const revoke = async (shareId: string) => {
    setBusy(true); setError("");
    try { await revokeShare(shareId); setShares(await listShares()); }
    catch { setError("分享链接撤销失败，请重试。"); }
    finally { setBusy(false); }
  };

  const deleteFamily = async () => {
    const family = session?.family;
    if (!family || familyName !== family.name) return;
    setBusy(true); setError("");
    try { await deleteFamilySpace(family.id); logout(); }
    catch { setError("家庭空间未删除，请重试。所有原内容仍然保留。"); setBusy(false); }
  };

  if (!settings) return <div className="privacy-page"><section className="progress-loading">{error ? <p>{error}</p> : <><LoaderCircle className="spin" /><p>正在读取隐私设置…</p></>}</section></div>;
  return <div className="privacy-page">
    <header className="privacy-header"><span className="section-kicker">PRIVACY CONTROL</span><h1>家人的声音，只属于家人</h1><p>内容默认私密。只有你主动创建的限时链接，才能在登录外查看指定作品。</p></header>
    {error && <p className="moment-review-error"><AlertTriangle size={15} />{error}</p>}{message && <p className="privacy-success"><ShieldCheck size={15} />{message}</p>}
    <section className="privacy-grid">
      <article className="privacy-card"><div className="privacy-card-title"><Clock3 /><div><h2>保留与分享</h2><p>修改后会重新计算仍在保存中的原始录音清理日期。</p></div></div>
        <label>原始录音保留<select value={settings.recording_retention_days} onChange={(event) => setSettings({ ...settings, recording_retention_days: Number(event.target.value) })}>{[3, 7, 14, 30].map((days) => <option key={days} value={days}>{days} 天</option>)}</select></label>
        <label>分享链接默认有效<select value={settings.share_default_hours} onChange={(event) => setSettings({ ...settings, share_default_hours: Number(event.target.value) })}>{[1, 6, 24, 72, 168].map((hours) => <option key={hours} value={hours}>{hours < 24 ? `${hours} 小时` : `${hours / 24} 天`}</option>)}</select></label>
        <label className="privacy-switch"><span><strong>允许创建分享链接</strong><small>关闭后立即撤销全部现有链接</small></span><input type="checkbox" checked={settings.sharing_enabled} onChange={(event) => setSettings({ ...settings, sharing_enabled: event.target.checked })} /></label>
        <button className="primary-button" disabled={busy} onClick={() => void save()}>{busy ? <LoaderCircle className="spin" size={16} /> : <Save size={16} />}保存设置</button>
      </article>
      <article className="privacy-card"><div className="privacy-card-title"><Link2Off /><div><h2>分享记录</h2><p>服务端只保存令牌摘要，链接正文仅在创建时显示一次。</p></div></div>
        <div className="share-list">{shares.length ? shares.map((share) => {
          const inactive = Boolean(share.revoked_at) || new Date(share.expires_at) <= new Date();
          return <div key={share.id}><span><strong>{share.title}</strong><small>{share.creation_type === "COMIC" ? "家庭漫画" : "家庭播客"} · {inactive ? "已失效" : `有效至 ${new Date(share.expires_at).toLocaleString("zh-CN")}`}</small></span><button disabled={inactive || busy} onClick={() => void revoke(share.id)}>撤销</button></div>;
        }) : <p>还没有创建过分享链接。</p>}</div>
      </article>
    </section>
    {metrics && <section className="privacy-metrics"><div className="privacy-card-title"><Gauge /><div><h2>运行健康度</h2><p>基于当前家庭的真实任务与删除审计。</p></div></div><div><span><strong>{percent(metrics.upload_success_rate)}</strong><small>上传成功率</small></span><span><strong>{percent(metrics.analysis_success_rate)}</strong><small>高光分析成功率</small></span><span><strong>{percent(metrics.generation_success_rate)}</strong><small>作品生成成功率</small></span><span><strong>{metrics.processing_p95_seconds === null ? "暂无样本" : `${Math.round(metrics.processing_p95_seconds)} 秒`}</strong><small>处理 P95</small></span></div></section>}
    <section className="privacy-danger"><div><AlertTriangle /><span><h2>删除整个家庭空间</h2><p>这会删除录音、转写、高光、漫画、播客、分享链接及对应文件，无法恢复。</p></span></div><label>输入“{session?.family?.name}”确认<input value={familyName} onChange={(event) => setFamilyName(event.target.value)} /></label><button disabled={busy || familyName !== session?.family?.name} onClick={() => void deleteFamily()}><Trash2 size={16} />永久删除家庭空间</button></section>
  </div>;
}
