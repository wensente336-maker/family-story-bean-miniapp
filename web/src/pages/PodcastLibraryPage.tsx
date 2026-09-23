import { ArrowRight, Headphones, LoaderCircle, Play, Plus, Search, Sparkles, Tag, Trash2 } from "lucide-react";
import { useEffect, useMemo, useState } from "react";
import { Link, useNavigate } from "react-router-dom";
import { getHomeData } from "../services/homeApi";
import { listPodcastProducts, listPodcastTrash, trashPodcastProduct, type PodcastProduct } from "../services/podcastApi";
import { PodcastQuickActions } from "../components/PodcastQuickActions";
import { PodcastDialog } from "../components/PodcastDialog";
import { PodcastSharePanel } from "../components/PodcastSharePanel";
import type { Processing } from "../types";

function formatDuration(durationMs: number) {
  const seconds = Math.max(0, Math.round(durationMs / 1000));
  return `${Math.floor(seconds / 60)}:${String(seconds % 60).padStart(2, "0")}`;
}

function PodcastWorkCard({ product, onShare, onDelete }: { product: PodcastProduct; onShare: () => void; onDelete: () => void }) {
  const navigate = useNavigate();
  const coverUrl = product.cover?.thumbnail_url || product.cover?.url || "/assets/family-vinyl-record.png";
  return <article className="podcast-work-card">
    <div className="podcast-work-cover has-cover" style={{ backgroundImage: `url(${coverUrl})` }}>
      <span><Play size={11} fill="currentColor" />{formatDuration(product.duration_ms)}</span>
    </div>
    <div className="podcast-work-copy">
      <span>家庭留声机 · {new Date(product.updated_at).toLocaleDateString("zh-CN", { month: "long", day: "numeric" })}</span>
      <h2><Link className="podcast-work-link" to={`/recordings/${product.recording_id}/podcast`}>{product.title}</Link></h2>
      <p>{product.description || "家人的真实声音，由第三人称解说串成完整故事。"}</p>
      {product.tags.length > 0 && <div>{product.tags.map((item) => <small key={item.id}>#{item.name}</small>)}</div>}
      <strong>打开作品<ArrowRight size={15} /></strong>
    </div>
    <PodcastQuickActions title={product.title} onEdit={() => navigate(`/recordings/${product.recording_id}/podcast?edit=1`)} onShare={onShare} onDelete={onDelete} />
  </article>;
}

export function PodcastLibraryPage() {
  const navigate = useNavigate();
  const [products, setProducts] = useState<PodcastProduct[]>([]);
  const [processing, setProcessing] = useState<Processing | null>(null);
  const [query, setQuery] = useState("");
  const [tag, setTag] = useState("");
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [trash, setTrash] = useState<PodcastProduct[]>([]);
  const [sharing, setSharing] = useState<PodcastProduct | null>(null);
  const [deleting, setDeleting] = useState<PodcastProduct | null>(null);
  const [deleteBusy, setDeleteBusy] = useState(false);
  const [deleteError, setDeleteError] = useState("");
  const [notice, setNotice] = useState("");
  const [reload, setReload] = useState(0);

  useEffect(() => {
    let active = true;
    setLoading(true); setError("");
    Promise.all([listPodcastProducts(), getHomeData(), listPodcastTrash()])
      .then(([result, home, deleted]) => {
        if (!active) return;
        setProducts(result.sort((left, right) => new Date(right.updated_at).getTime() - new Date(left.updated_at).getTime()));
        setProcessing(home.processing);
        setTrash(deleted);
      })
      .catch(() => { if (active) setError("家庭留声机作品暂时无法读取，请稍后重试。"); })
      .finally(() => { if (active) setLoading(false); });
    return () => { active = false; };
  }, [reload]);

  const confirmDelete = async () => {
    if (!deleting || deleteBusy) return;
    setDeleteBusy(true); setDeleteError("");
    try {
      const result = await trashPodcastProduct(deleting.recording_id);
      setProducts((current) => current.filter((item) => item.recording_id !== deleting.recording_id));
      setTrash((current) => [{ ...deleting, deleted_at: result.deleted_at }, ...current.filter((item) => item.recording_id !== deleting.recording_id)]);
      setNotice(`“${deleting.title}”已移至回收站。`);
      setDeleting(null);
      requestAnimationFrame(() => document.querySelector<HTMLElement>(".podcast-trash-link")?.focus());
    } catch { setDeleteError("未能移至回收站，作品仍保留。请重试。"); }
    finally { setDeleteBusy(false); }
  };

  const tagOptions = useMemo(() => Array.from(new Set(products.flatMap((product) => product.available_tags.map((item) => item.name)))), [products]);
  const visibleProducts = useMemo(() => {
    const keyword = query.trim().toLocaleLowerCase("zh-CN");
    return products.filter((product) => {
      const matchesTag = !tag || product.tags.some((item) => item.name === tag);
      const searchable = `${product.title} ${product.description} ${product.tags.map((item) => item.name).join(" ")}`.toLocaleLowerCase("zh-CN");
      return matchesTag && (!keyword || searchable.includes(keyword));
    });
  }, [products, query, tag]);

  const hasActiveCreation = Boolean(processing?.recordingId && ![...products, ...trash].some((product) => product.recording_id === processing.recordingId));
  const continuePath = hasActiveCreation && processing?.recordingId ? `/recordings/${processing.recordingId}/moments` : "/upload";

  return <div className="podcast-library-page">
    <header className="podcast-library-header">
      <div><span className="section-kicker">FAMILY GRAMOPHONE</span><h1>家庭留声机</h1><p>把家人的声音珍藏成一张张会唱歌的唱片。</p></div>
      <div className="podcast-library-header-actions"><Link className="secondary-button podcast-trash-link" to="/podcasts/trash"><Trash2 size={16} />回收站{!loading && !error ? `（${trash.length}）` : ""}</Link><button className="primary-button" onClick={() => navigate(continuePath)}><Plus size={17} />{hasActiveCreation ? "继续创作" : "创建留声机"}</button></div>
    </header>
    {notice && <p className="plan-notice" role="status">{notice}<Link to="/podcasts/trash">查看回收站</Link></p>}

    {hasActiveCreation && processing?.recordingId && <section className="podcast-continue-card">
      <span><Sparkles size={21} /></span><div><small>正在创作</small><h2>{processing.title}</h2><p>{processing.detail} · {processing.progress}%</p></div>
      <button onClick={() => navigate(continuePath)}>继续处理<ArrowRight size={16} /></button>
    </section>}

    <section className="podcast-library-title"><div><span className="section-kicker">作品库</span><h2>全部留声机作品</h2></div><strong>{visibleProducts.length} 个作品</strong></section>
    <section className="podcast-library-tools">
      <label><Search size={16} /><input value={query} onChange={(event) => setQuery(event.target.value)} placeholder="搜索标题、简介或标签" /></label>
      <label><Tag size={15} /><select value={tag} onChange={(event) => setTag(event.target.value)}><option value="">全部标签</option>{tagOptions.map((item) => <option key={item} value={item}>#{item}</option>)}</select></label>
    </section>

    {loading ? <section className="progress-loading"><LoaderCircle className="spin" /><p>正在整理家庭留声机…</p></section>
      : error ? <p className="moment-review-error" role="alert">{error}<button className="text-action" onClick={() => setReload((value) => value + 1)}>重试</button></p>
      : visibleProducts.length ? <section className="podcast-work-grid">{visibleProducts.map((product) => <PodcastWorkCard key={product.podcast_version_id} product={product} onShare={() => setSharing(product)} onDelete={() => { setDeleteError(""); setDeleting(product); }} />)}</section>
      : <section className="podcast-library-empty"><Headphones size={38} /><h2>{products.length ? "没有找到对应作品" : "还没有家庭留声机"}</h2><p>{products.length ? "换一个搜索词或标签试试。" : "从一段家庭录音开始，留下第一张声音唱片。"}</p>{!products.length && <button className="primary-button" onClick={() => navigate(continuePath)}>开始创作</button>}</section>}
    {sharing && <PodcastDialog title={`分享 · ${sharing.title}`} onClose={() => setSharing(null)}><PodcastSharePanel key={sharing.recording_id} product={sharing} /></PodcastDialog>}
    {deleting && <PodcastDialog title="移至回收站？" busy={deleteBusy} onClose={() => setDeleting(null)}>
      <p className="podcast-delete-title">{deleting.title}</p><p className="podcast-dialog-description">作品将从作品库中移除，你可以在回收站恢复。现有分享链接会失效，恢复作品后需重新分享。</p>
      {deleteError && <p className="moment-review-error" role="alert">{deleteError}</p>}
      <div className="podcast-dialog-actions"><button data-initial-focus className="secondary-button" disabled={deleteBusy} onClick={() => setDeleting(null)}>取消</button><button className="podcast-danger-button" disabled={deleteBusy} onClick={() => void confirmDelete()}>{deleteBusy ? "正在移入…" : "确认移至回收站"}</button></div>
    </PodcastDialog>}
  </div>;
}
