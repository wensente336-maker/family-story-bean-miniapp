import { useEffect, useState } from "react";
import { Check, Clock3, Copy, Download, ExternalLink, LoaderCircle, Share2, XCircle } from "lucide-react";
import { ApiClientError } from "../services/apiClient";
import { createPodcastShare, listPodcastShares, revokePodcastShare, type PodcastProduct, type PodcastShare } from "../services/podcastApi";
import { shareOrCopy } from "../utils/share";

export function PodcastSharePanel({ product }: { product: PodcastProduct }) {
  const [hours, setHours] = useState(24);
  const [shares, setShares] = useState<PodcastShare[]>([]);
  const [shareUrl, setShareUrl] = useState("");
  const [busy, setBusy] = useState(false);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [notice, setNotice] = useState("");
  const [reload, setReload] = useState(0);
  useEffect(() => {
    let active = true;
    setLoading(true); setError("");
    void listPodcastShares(product.recording_id).then((items) => { if (active) setShares(items); })
      .catch(() => { if (active) setError("分享记录暂时无法读取，请重试。"); })
      .finally(() => { if (active) setLoading(false); });
    return () => { active = false; };
  }, [product.recording_id, reload]);

  const create = async () => {
    if (busy) return;
    setBusy(true); setError(""); setNotice("");
    try {
      const share = await createPodcastShare(product.recording_id, hours);
      setShares((current) => [share, ...current]); setShareUrl(share.url);
      setNotice("限时链接已创建，可复制或使用系统分享。");
      try { await navigator.clipboard.writeText(share.url); setNotice("限时链接已创建并复制，可随时撤销。"); }
      catch { /* The link is already created; clipboard failure must not cause duplicate creation. */ }
    } catch (reason) { setError(reason instanceof ApiClientError ? reason.message : "分享链接创建失败，请重试。"); }
    finally { setBusy(false); }
  };
  const revoke = async (id: string) => {
    if (busy) return;
    setBusy(true); setError(""); setNotice("");
    try {
      const result = await revokePodcastShare(id);
      setShares((current) => current.map((item) => item.id === id ? result : item));
      if (shares.some((item) => item.id === id && item.url === shareUrl)) setShareUrl("");
      setNotice("分享链接已撤销。");
    } catch { setError("撤销失败，请重试。"); }
    finally { setBusy(false); }
  };
  const copy = async () => {
    try { await navigator.clipboard.writeText(shareUrl); setNotice("链接已复制。"); }
    catch { setError("复制失败，请选择链接后手动复制。"); }
  };
  const systemShare = async () => {
    try {
      const result = await shareOrCopy({ title: product.title, text: product.description, url: shareUrl });
      if (result === "copied") setNotice("当前浏览器不支持系统分享，链接已复制。");
    } catch (reason) { if (!(reason instanceof Error && reason.name === "AbortError")) setError("暂时无法分享，请复制链接。"); }
  };
  return <section className="product-sharing podcast-share-panel" aria-label="限时私密分享">
    <div className="product-section-title"><Share2 size={20} /><div><strong>限时私密分享</strong><small>只分享封面、介绍、标签和成品音频，不公开逐字稿与家人资料</small></div></div>
    {error && <p className="moment-review-error" role="alert">{error}{!loading && <button className="text-action" onClick={() => setReload((value) => value + 1)}>重载分享记录</button>}</p>}
    {notice && <p className="plan-notice" role="status"><Check size={15} />{notice}</p>}
    <div className="share-create-row"><label>有效期<select aria-label="分享有效期" value={hours} disabled={busy} onChange={(event) => setHours(Number(event.target.value))}><option value={24}>24 小时</option><option value={72}>3 天</option><option value={168}>7 天</option></select></label><button className="primary-button" disabled={busy || loading} onClick={() => void create()}>{busy ? <LoaderCircle size={15} className="spin" /> : <Share2 size={15} />}创建限时链接</button>{product.cover && <a className="secondary-button" href={`${product.cover.url}?download=true`}><Download size={15} />下载分享封面</a>}</div>
    {shareUrl && <div className="share-ready"><input aria-label="分享链接" readOnly value={shareUrl} onFocus={(event) => event.target.select()} /><button onClick={() => void copy()}><Copy size={14} />复制</button><button onClick={() => void systemShare()}><ExternalLink size={14} />系统分享</button><a href={shareUrl} target="_blank" rel="noreferrer"><ExternalLink size={14} />预览</a></div>}
    <div className="share-history">{loading ? <p>正在读取分享记录…</p> : shares.length ? shares.map((share) => {
      const inactive = Boolean(share.revoked_at) || new Date(share.expires_at) <= new Date();
      return <article key={share.id} className={inactive ? "inactive" : ""}><div><strong>{share.revoked_at ? "已撤销" : inactive ? "已过期" : "分享中"}</strong><small><Clock3 size={12} />{new Date(share.expires_at).toLocaleString("zh-CN")} 失效 · 访问 {share.access_count} 次</small></div>{!inactive && <button disabled={busy} onClick={() => void revoke(share.id)}><XCircle size={14} />撤销</button>}</article>;
    }) : <p>还没有创建过分享链接。</p>}</div>
  </section>;
}
