import { useEffect, useState } from "react";
import { ArrowLeft, Headphones, LoaderCircle, RotateCcw, Trash2 } from "lucide-react";
import { Link } from "react-router-dom";
import { listPodcastTrash, restorePodcastProduct, type PodcastProduct } from "../services/podcastApi";
import { listHighlightTrash, restoreHighlightWork, type HighlightWork } from "../services/highlightApi";

export function PodcastTrashPage() {
  const [products, setProducts] = useState<PodcastProduct[]>([]);
  const [highlights, setHighlights] = useState<HighlightWork[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [notice, setNotice] = useState("");
  const [busy, setBusy] = useState<string | null>(null);
  const [reload, setReload] = useState(0);
  useEffect(() => {
    let active = true;
    setLoading(true); setError("");
    void Promise.all([listPodcastTrash(), listHighlightTrash()]).then(([items, moments]) => { if (active) { setProducts(items); setHighlights(moments); } })
      .catch(() => { if (active) setError("回收站暂时无法读取，请重试。"); })
      .finally(() => { if (active) setLoading(false); });
    return () => { active = false; };
  }, [reload]);
  const restore = async (product: PodcastProduct) => {
    if (busy) return;
    setBusy(product.recording_id); setError("");
    try {
      await restorePodcastProduct(product.recording_id);
      setProducts((items) => items.filter((item) => item.recording_id !== product.recording_id));
      setNotice(`“${product.title}”已恢复到作品库。旧分享链接仍保持失效。`);
      requestAnimationFrame(() => document.querySelector<HTMLElement>(".podcast-trash-back")?.focus());
    } catch { setError("恢复失败，作品仍保留在回收站，请重试。"); }
    finally { setBusy(null); }
  };
  const restoreHighlight = async (work: HighlightWork) => {
    if (busy) return; setBusy(work.id); setError("");
    try { await restoreHighlightWork(work.id); setHighlights((items) => items.filter((item) => item.id !== work.id)); setNotice(`“${work.title}”已恢复到声音明信片。旧分享链接仍保持失效。`); }
    catch { setError("恢复失败，高光仍保留在回收站，请重试。"); }
    finally { setBusy(null); }
  };
  return <div className="podcast-library-page">
    <Link className="progress-back podcast-trash-back" to="/podcasts"><ArrowLeft size={17} />返回家庭留声机</Link>
    <header className="podcast-library-header"><div><span className="section-kicker">FAMILY PODCASTS</span><h1>回收站</h1><p>暂时收起的声音故事都在这里，可随时恢复。作品不会自动清除。</p></div></header>
    {notice && <p className="plan-notice" role="status">{notice}<Link to="/podcasts">查看作品库</Link></p>}
    {error && <p className="moment-review-error" role="alert">{error}<button className="text-action" disabled={Boolean(busy)} onClick={() => setReload((value) => value + 1)}>重新加载</button></p>}
    {loading ? <section className="progress-loading"><LoaderCircle className="spin" /><p>正在读取回收站…</p></section> : products.length || highlights.length ? <>
      <section className="podcast-library-title"><h2>已删除作品</h2><strong>{products.length + highlights.length} 个作品</strong></section>
      <section className="podcast-trash-list">{products.map((product) => <article key={product.recording_id} className="podcast-trash-card">
        <div className="podcast-trash-cover">{product.cover ? <img src={product.cover.thumbnail_url || product.cover.url} alt="" /> : <Headphones size={28} />}</div>
        <div className="podcast-trash-copy"><h2>{product.title}</h2><p>{product.description}</p><small>移入时间：{product.deleted_at ? new Date(product.deleted_at).toLocaleString("zh-CN") : "—"}</small></div>
        <button className="secondary-button" disabled={Boolean(busy)} onClick={() => void restore(product)}>{busy === product.recording_id ? <LoaderCircle size={16} className="spin" /> : <RotateCcw size={16} />}{busy === product.recording_id ? "正在恢复…" : "恢复作品"}</button>
      </article>)}{highlights.map((work) => <article key={work.id} className="podcast-trash-card">
        <div className="podcast-trash-cover">{work.cover ? <img src={work.cover.thumbnail_url || work.cover.url} alt="" /> : <Headphones size={28} />}</div>
        <div className="podcast-trash-copy"><small>声音明信片</small><h2>{work.title}</h2><p>“{work.quote}”</p><small>移入时间：{work.deleted_at ? new Date(work.deleted_at).toLocaleString("zh-CN") : "—"}</small></div>
        <button className="secondary-button" disabled={Boolean(busy)} onClick={() => void restoreHighlight(work)}>{busy === work.id ? <LoaderCircle size={16} className="spin" /> : <RotateCcw size={16} />}{busy === work.id ? "正在恢复…" : "恢复高光"}</button>
      </article>)}</section>
    </> : !error && <section className="podcast-library-empty"><Trash2 size={36} /><h2>回收站是空的</h2><p>被移除的留声机作品会保存在这里，等待你再次拾起。</p><Link className="secondary-button" to="/podcasts">返回作品库</Link></section>}
  </div>;
}
