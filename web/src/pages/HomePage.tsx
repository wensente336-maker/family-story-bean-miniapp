import {
  ArrowRight,
  Check,
  ChevronRight,
  FileAudio,
  Headphones,
  Image as ImageIcon,
  LockKeyhole,
  Pause,
  Play,
  Sparkles,
  Upload
} from "lucide-react";
import { useEffect, useState } from "react";
import { useNavigate } from "react-router-dom";
import { env } from "../config/env";
import { getHomeData } from "../services/homeApi";
import { listHighlightWorks, type HighlightWork } from "../services/highlightApi";
import { listPodcastProducts, type PodcastProduct } from "../services/podcastApi";
import type { HomeData, Moment } from "../types";

function FamilyAvatars({ members }: { members: string[] }) {
  return <div className="family-avatars" aria-label={`家庭成员：${members.join("、")}`}>
    {members.map((member, index) => <span key={member} className={`avatar avatar-${index + 1}`}>{member}</span>)}
  </div>;
}

function MomentCard({ moment, coverUrl, onOpen }: { moment: Moment; coverUrl?: string; onOpen: () => void }) {
  const imageUrl = coverUrl || moment.image;
  return (
    <article className={`moment-card ${moment.tone}`} tabIndex={0} role="button" onClick={onOpen} onKeyDown={(event) => event.key === "Enter" && onOpen()}>
      <div className="moment-meta"><span>{moment.theme}</span><time>{moment.duration}</time></div>
      {imageUrl ? (
        <img src={imageUrl} alt={coverUrl ? `${moment.title}的声音明信片封面` : "家庭声音高光插画"} />
      ) : (
        <div className="wave-art" aria-hidden="true">
          {[30, 58, 42, 75, 88, 48, 64, 36, 72, 54, 28, 60].map((height, index) => <i key={index} style={{ height: `${height}%` }} />)}
          <span className="wave-caption"><FileAudio size={18} /> 周日晚餐 · 原声片段</span>
        </div>
      )}
      <h3>{moment.title}</h3>
      <blockquote>“{moment.quote}”</blockquote>
      <footer><span className="round-play"><Play size={14} fill="currentColor" /></span><span>听听这一刻</span><ArrowRight size={18} /></footer>
    </article>
  );
}

function formatDuration(durationMs: number) {
  const totalSeconds = Math.max(0, Math.round(durationMs / 1000));
  return `${Math.floor(totalSeconds / 60)}:${String(totalSeconds % 60).padStart(2, "0")}`;
}

function PodcastKeepsakeCard({ product, onOpen }: { product: PodcastProduct; onOpen: () => void }) {
  const coverUrl = product.cover?.thumbnail_url || product.cover?.url || "/assets/family-vinyl-record.png";
  return <article className="keepsake-product-card" tabIndex={0} role="button" onClick={onOpen} onKeyDown={(event) => event.key === "Enter" && onOpen()}>
    <div className="keepsake-product-cover has-cover" style={{ backgroundImage: `url(${coverUrl})` }}>
      <span><Headphones size={13} />家庭留声机作品</span>
    </div>
    <div className="keepsake-product-copy">
      <span className="section-kicker">已保存到家庭时光</span>
      <h3>{product.title}</h3>
      <p>{product.description || "家人的真实声音，由第三人称解说串成一段完整故事。"}</p>
      {product.tags.length > 0 && <div className="keepsake-product-tags">{product.tags.map((tag) => <span key={tag.id}>#{tag.name}</span>)}</div>}
      <footer><span><Play size={14} fill="currentColor" />{formatDuration(product.duration_ms)}</span><strong>打开完整作品<ArrowRight size={17} /></strong></footer>
    </div>
  </article>;
}

export function HomePage() {
  const navigate = useNavigate();
  const [data, setData] = useState<HomeData | null>(null);
  const [podcastProducts, setPodcastProducts] = useState<PodcastProduct[]>([]);
  const [highlightWorks, setHighlightWorks] = useState<HighlightWork[]>([]);
  const [isPlaying, setIsPlaying] = useState(false);
  const [loadError, setLoadError] = useState("");

  const loadHome = () => {
    setLoadError("");
    Promise.all([getHomeData(), listPodcastProducts().catch(() => []), listHighlightWorks().catch(() => [])])
      .then(([homeData, products, highlights]) => {
        setData(homeData);
        setPodcastProducts(products.sort((left, right) => new Date(right.updated_at).getTime() - new Date(left.updated_at).getTime()));
        setHighlightWorks(highlights);
      })
      .catch(() => setLoadError("家庭故事暂时加载失败，请稍后再试。"));
  };

  useEffect(() => {
    loadHome();
    const timer = window.setInterval(() => {
      if (document.visibilityState === "visible") loadHome();
    }, 3000);
    return () => window.clearInterval(timer);
  }, []);

  if (!data && loadError) return <div className="home-page"><section className="load-error"><FileAudio size={30} /><h1>没有加载成功</h1><p>{loadError}</p><button className="primary-button" onClick={loadHome}>重新加载</button></section></div>;
  if (!data) return <div className="home-page"><div className="loading-line" /><div className="skeleton hero-skeleton" /><div className="skeleton card-skeleton" /></div>;

  const completedProcessingProduct = podcastProducts.find((product) => product.recording_id === data.processing.recordingId);
  const creationPath = data.processing.recordingId && !completedProcessingProduct ? `/recordings/${data.processing.recordingId}/moments` : "/upload";
  const highlightsByMoment = new Map(highlightWorks.filter((work) => work.source_moment_id).map((work) => [work.source_moment_id, work]));

  return (
    <div className="home-page">
      <header className="page-header">
        <div><span className="family-name">{data.family.name}</span><h1>把日常，变成可以重听的故事<span className="headline-bean" /></h1></div>
        <FamilyAvatars members={data.family.members} />
      </header>

      <section className="hero-grid">
        <div className="upload-stage">
          <div className="privacy-pill"><LockKeyhole size={14} />仅你的家人可见</div>
          <h2>让今天的笑声，<br />成为明天的故事。</h2>
          <p>上传音频或视频、直接用手机录音，也可以导入录音豆里的家庭声音。</p>
          <button className="primary-button" onClick={() => navigate("/upload")}><Upload size={19} />开始记录</button>
          <small>三种采集方式 · 最长 15 分钟 · 视频自动提取声音</small>
          <div className="audio-orbit" aria-hidden="true">
            <span className="orbit orbit-one" /><span className="orbit orbit-two" /><span className="orbit orbit-three" />
            <span className="recording-bean"><i /><b /></span>
          </div>
        </div>

        <aside className="today-panel">
          <div className="today-heading"><span>正在发生</span><span className="live-dot">{completedProcessingProduct ? "已完成" : data.processing.stage === "UPLOADED" ? "已上传" : data.processing.stage === "EMPTY" ? "等待记录" : "处理中"}</span></div>
          <div className="processing-compact">
            <div className="processing-icon"><FileAudio size={24} /></div>
            <div><strong>{data.processing.title}</strong><span>{completedProcessingProduct ? "家庭留声机已经保存到作品库" : data.processing.detail}</span></div>
            <b>{data.processing.progress}%</b>
          </div>
          <div className="progress-track"><span style={{ width: `${data.processing.progress}%` }} /></div>
          <div className="process-steps">
            <span className="done"><Check size={14} />音频已读取</span>
            <span className={completedProcessingProduct ? "done" : "current"}><Sparkles size={14} />{completedProcessingProduct ? "高光已确认" : data.processing.stage === "UPLOADED" ? "等待 AI 处理" : "发现高光"}</span>
            <span className={completedProcessingProduct ? "done" : ""}>{completedProcessingProduct ? <Check size={14} /> : null}{completedProcessingProduct ? "留声机已生成" : "整理声音素材"}</span>
          </div>
          <button className="text-button" disabled={!data.processing.recordingId} onClick={() => data.processing.recordingId && navigate(completedProcessingProduct ? `/recordings/${data.processing.recordingId}/podcast` : `/recordings/${data.processing.recordingId}`)}>{completedProcessingProduct ? "打开完整作品" : "查看处理详情"}<ChevronRight size={16} /></button>
        </aside>
      </section>

      <section className="content-section">
        <div className="section-heading"><div><span className="section-kicker">今日发现</span><h2>今天的声音明信片</h2></div><button onClick={() => navigate("/postcards")}>查看明信片<ArrowRight size={16} /></button></div>
        <div className="moment-grid">
          {data.moments.map((moment) => {
            const highlight = highlightsByMoment.get(moment.id);
            const coverUrl = highlight?.cover?.thumbnail_url || highlight?.cover?.url;
            return <MomentCard key={moment.id} moment={moment} coverUrl={coverUrl} onOpen={() => navigate(highlight ? `/highlights/${highlight.id}` : `/recordings/${moment.recordingId}/story`)} />;
          })}
        </div>
      </section>

      {podcastProducts.length > 0 && <section className="content-section recent-work-section">
        <div className="section-heading"><div><span className="section-kicker">家庭作品</span><h2>最近完成的留声机</h2></div><button onClick={() => navigate("/podcasts")}>全部作品<ArrowRight size={16} /></button></div>
        <div className="keepsake-products">
          {podcastProducts.slice(0, 1).map((product) => <PodcastKeepsakeCard key={product.podcast_version_id} product={product} onOpen={() => navigate(`/recordings/${product.recording_id}/podcast`)} />)}
        </div>
      </section>}

      {env.features.podcastCreation && <section className="content-section creation-section">
        <div className="section-heading"><div><span className="section-kicker">声音创作</span><h2>开始或继续一段创作</h2></div><button onClick={() => navigate("/podcasts")}>创作与作品<ArrowRight size={16} /></button></div>
        <div className={`creation-grid ${env.features.comicCreation ? "" : "podcast-only"}`}>
          {env.features.comicCreation && <button className="creation-card comic" onClick={() => navigate("/comics/new")}>
            <span className="creation-icon"><ImageIcon size={28} /></span><span><strong>家庭漫画</strong><small>把金句画成四格故事</small></span><ArrowRight size={20} />
          </button>}
          <button className="creation-card podcast" onClick={() => navigate(creationPath)}>
            <span className="creation-icon"><Headphones size={28} /></span><span><strong>{data.processing.recordingId && !completedProcessingProduct ? "继续最近的声音创作" : "创建新的家庭留声机"}</strong><small>确认家人的真实原声，由 AI 用第三人称解说串成完整故事</small></span><ArrowRight size={20} />
          </button>
        </div>
      </section>}

      <button className="timeline-card" onClick={() => navigate("/postcards")}>
        <span className="calendar"><small>SEP</small><strong>18</strong></span>
        <span><small>家庭声音明信片</small><strong>把普通日子的声音，寄给未来。</strong></span>
        <ChevronRight size={24} />
      </button>

      <button className="floating-audio" aria-label={isPlaying ? "暂停示例音频" : "播放示例音频"} onClick={() => setIsPlaying((value) => !value)}>
        {isPlaying ? <Pause size={18} fill="currentColor" /> : <Play size={18} fill="currentColor" />}<span>{isPlaying ? "正在播放家庭片段" : "试听家庭片段"}</span>
      </button>
    </div>
  );
}
