import { BookOpen, CalendarDays, Headphones, Image, LoaderCircle, Mic2, Sparkles, Tag, Trash2, UsersRound } from "lucide-react";
import { useEffect, useState } from "react";
import { useNavigate } from "react-router-dom";
import { useAuth } from "../auth/AuthContext";
import { deleteCreation, deleteRecording, listTimeline, type TimelineItem, type TimelineKind } from "../services/lifecycleApi";
import { listPodcastProducts, type PodcastProduct } from "../services/podcastApi";

const kindCopy: Record<TimelineKind, { label: string; icon: typeof Mic2 }> = {
  recording: { label: "录音", icon: Mic2 }, moment: { label: "高光", icon: Sparkles },
  comic: { label: "漫画", icon: Image }, podcast: { label: "播客", icon: Headphones },
};

export function podcastProductTimelineItem(product: PodcastProduct): TimelineItem {
  return {
    id: product.podcast_version_id, kind: "podcast", title: product.title,
    subtitle: `${product.description || "家庭声音播客"} · ${product.tags.map((item) => `#${item.name}`).join(" ")}`,
    status: "product-v2", created_at: product.created_at, recording_id: product.recording_id,
    target_path: `/recordings/${product.recording_id}/podcast`, member_ids: [],
  };
}

function inDateRange(createdAt: string, dateFrom: string, dateTo: string) {
  const created = new Date(createdAt).getTime();
  return (!dateFrom || created >= new Date(`${dateFrom}T00:00:00+08:00`).getTime())
    && (!dateTo || created <= new Date(`${dateTo}T23:59:59+08:00`).getTime());
}

export function TimelinePage() {
  const navigate = useNavigate();
  const { session } = useAuth();
  const [items, setItems] = useState<TimelineItem[]>([]);
  const [kind, setKind] = useState<TimelineKind | "">("");
  const [memberId, setMemberId] = useState("");
  const [dateFrom, setDateFrom] = useState("");
  const [dateTo, setDateTo] = useState("");
  const [tag, setTag] = useState("");
  const [podcastProducts, setPodcastProducts] = useState<PodcastProduct[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");

  const remove = async (item: TimelineItem) => {
    if (!window.confirm(`确定永久删除“${item.title}”吗？此操作无法恢复。`)) return;
    setError("");
    try {
      if (item.kind === "recording") await deleteRecording(item.id);
      else if (item.kind === "comic" || item.kind === "podcast") await deleteCreation(item.id);
      setItems((current) => current.filter((entry) => entry.id !== item.id));
    } catch { setError("内容未删除，请重试。"); }
  };

  useEffect(() => {
    setLoading(true); setError("");
    if (tag) {
      listPodcastProducts(tag).then((products) => {
        setPodcastProducts(products);
        setItems(products.filter((product) => inDateRange(product.created_at, dateFrom, dateTo)).map(podcastProductTimelineItem));
      }).catch(() => setError("按标签检索播客失败。")).finally(() => setLoading(false));
      return;
    }
    Promise.all([
      listTimeline({ content_type: kind, member_id: memberId, date_from: dateFrom, date_to: dateTo }),
      listPodcastProducts(),
    ])
      .then(([result, products]) => {
        setPodcastProducts(products);
        const productItems = products
          .filter((product) => (!kind || kind === "podcast") && !memberId && inDateRange(product.created_at, dateFrom, dateTo))
          .map(podcastProductTimelineItem);
        setItems([...result.items, ...productItems].sort(
          (left, right) => new Date(right.created_at).getTime() - new Date(left.created_at).getTime()
        ));
      })
      .catch(() => setError("时间线暂时无法读取，请稍后重试。"))
      .finally(() => setLoading(false));
  }, [kind, memberId, dateFrom, dateTo, tag]);

  const tagOptions = Array.from(new Set(podcastProducts.flatMap((item) => item.available_tags.map((entry) => entry.name))));
  const productsByVersion = new Map(podcastProducts.map((product) => [product.podcast_version_id, product]));

  return <div className="timeline-page">
    <header className="timeline-header"><span className="section-kicker">FAMILY TIMELINE</span><h1>成长时间线</h1><p>录音、高光和家庭播客，按发生的时间重新聚在一起；已经生成的历史漫画仍会保留。</p></header>
    <section className="timeline-filters">
      <label><BookOpen size={15} /><select value={kind} onChange={(event) => setKind(event.target.value as TimelineKind | "")}><option value="">全部内容</option>{Object.entries(kindCopy).map(([value, copy]) => <option key={value} value={value}>{copy.label}</option>)}</select></label>
      <label><UsersRound size={15} /><select value={memberId} onChange={(event) => setMemberId(event.target.value)}><option value="">全部家人</option>{session?.family?.members.map((member) => <option key={member.id} value={member.id}>{member.nickname}</option>)}</select></label>
      <label><CalendarDays size={15} /><input aria-label="开始日期" type="date" value={dateFrom} onChange={(event) => setDateFrom(event.target.value)} /></label>
      <label><span>至</span><input aria-label="结束日期" type="date" value={dateTo} onChange={(event) => setDateTo(event.target.value)} /></label>
      <label><Tag size={15} /><select value={tag} onChange={(event) => { setTag(event.target.value); if (event.target.value) setKind("podcast"); }}><option value="">全部标签</option>{tagOptions.map((item) => <option key={item} value={item}>#{item}</option>)}</select></label>
    </section>
    {loading ? <section className="progress-loading"><LoaderCircle className="spin" /><p>正在整理家庭时光…</p></section> : error ? <p className="moment-review-error">{error}</p> : items.length ? <section className="timeline-card-stream">{items.map((item, index) => {
      const copy = kindCopy[item.kind]; const Icon = copy.icon;
      const date = new Date(item.created_at);
      const product = item.status === "product-v2" ? productsByVersion.get(item.id) : undefined;
      const coverUrl = product?.cover?.thumbnail_url || product?.cover?.url;
      return <div key={`${item.kind}-${item.id}`} className="timeline-card-event">
        <div className="timeline-card-date"><strong>{date.getDate()}</strong><span>{date.toLocaleDateString("zh-CN", { month: "short" })}</span><time>{date.toLocaleTimeString("zh-CN", { hour: "2-digit", minute: "2-digit" })}</time></div>
        <div className={`timeline-card-node ${item.kind}`}><Icon size={17} /></div>
        <article className={`timeline-info-card ${item.kind}`} tabIndex={0} role="button" onClick={() => navigate(item.target_path)} onKeyDown={(event) => event.key === "Enter" && navigate(item.target_path)}>
          <div className={`timeline-card-visual ${coverUrl ? "has-cover" : ""}`} style={coverUrl ? { backgroundImage: `url(${coverUrl})` } : undefined}>
            {!coverUrl && <Icon size={31} />}
            <span>{product ? "完整作品" : copy.label}</span>
          </div>
          <div className="timeline-card-copy">
            <span>{copy.label} · {index === 0 ? "最近更新" : date.toLocaleDateString("zh-CN", { year: "numeric", month: "long", day: "numeric" })}</span>
            <h2>{item.title}</h2><p>{item.subtitle}</p>
            {product && product.tags.length > 0 && <div className="timeline-card-tags">{product.tags.map((entry) => <span key={entry.id}>#{entry.name}</span>)}</div>}
            <strong>{product ? "打开完整作品" : "查看这一刻"}<span aria-hidden="true">→</span></strong>
          </div>
          {item.status !== "product-v2" && (item.kind === "recording" || item.kind === "comic" || item.kind === "podcast") && <button className="timeline-card-delete" aria-label={`删除${item.title}`} onClick={(event) => { event.stopPropagation(); void remove(item); }}><Trash2 size={15} /></button>}
        </article>
      </div>;
    })}</section> : <section className="timeline-empty"><CalendarDays size={34} /><h2>还没有符合条件的时光</h2><p>换一个筛选条件，或者上传一段新的家庭录音。</p><button className="primary-button" onClick={() => navigate("/upload")}>上传录音</button></section>}
  </div>;
}
