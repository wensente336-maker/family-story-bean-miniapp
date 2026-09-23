import { AlertTriangle, ArrowDown, ArrowLeft, ArrowUp, Copy, Download, Headphones, LoaderCircle, Mic2, Play, RefreshCw, Share2, Sparkles, Volume2 } from "lucide-react";
import { useEffect, useRef, useState } from "react";
import { useNavigate, useParams } from "react-router-dom";
import { getPlaybackUrl } from "../services/transcriptApi";
import { getPodcast, getPodcastPlayback, remixPodcast, type Podcast, type PodcastPlayback } from "../services/podcastApi";
import { createShare, getPrivacySettings } from "../services/lifecycleApi";

function clock(milliseconds = 0) {
  const seconds = Math.max(0, Math.round(milliseconds / 1000));
  return `${Math.floor(seconds / 60)}:${String(seconds % 60).padStart(2, "0")}`;
}

export function PodcastPage() {
  const { id = "" } = useParams();
  const navigate = useNavigate();
  const originalAudio = useRef<HTMLAudioElement>(null);
  const stopAt = useRef<number | null>(null);
  const [podcast, setPodcast] = useState<Podcast | null>(null);
  const [playback, setPlayback] = useState<PodcastPlayback | null>(null);
  const [originalUrl, setOriginalUrl] = useState("");
  const [intro, setIntro] = useState("");
  const [outro, setOutro] = useState("");
  const [momentIds, setMomentIds] = useState<string[]>([]);
  const [remixing, setRemixing] = useState(false);
  const [error, setError] = useState("");
  const [shareUrl, setShareUrl] = useState("");
  const [sharing, setSharing] = useState(false);
  const [shareHours, setShareHours] = useState(24);

  const load = async () => {
    const next = await getPodcast(id);
    setPodcast(next); setIntro(next.metadata.intro ?? ""); setOutro(next.metadata.outro ?? "");
    setMomentIds(next.moments.map((item) => item.id));
    if (next.status === "COMPLETED") setPlayback(await getPodcastPlayback(id));
    setOriginalUrl(await getPlaybackUrl(next.recording_id));
  };

  useEffect(() => {
    void load().catch(() => setError("播客暂时无法读取，请稍后重试。"));
    getPrivacySettings().then((settings) => setShareHours(settings.share_default_hours)).catch(() => undefined);
  }, [id]);
  useEffect(() => {
    const audio = originalAudio.current;
    if (!audio) return;
    const onTime = () => {
      if (stopAt.current !== null && audio.currentTime >= stopAt.current) {
        audio.pause(); stopAt.current = null;
      }
    };
    audio.addEventListener("timeupdate", onTime);
    return () => audio.removeEventListener("timeupdate", onTime);
  }, [originalUrl]);

  const playOriginal = async (start: number, end: number) => {
    const audio = originalAudio.current;
    if (!audio) return;
    audio.currentTime = start / 1000; stopAt.current = end / 1000;
    await audio.play();
  };

  const move = (index: number, direction: -1 | 1) => {
    const target = index + direction;
    if (target < 0 || target >= momentIds.length) return;
    setMomentIds((current) => {
      const next = [...current]; [next[index], next[target]] = [next[target], next[index]]; return next;
    });
  };

  const remix = async () => {
    if (!intro.trim() || !outro.trim()) return;
    setRemixing(true); setError(""); setPlayback(null);
    try {
      const next = await remixPodcast(id, { moment_ids: momentIds, intro: intro.trim(), outro: outro.trim() });
      setPodcast(next);
      if (next.status === "COMPLETED") setPlayback(await getPodcastPlayback(id));
    } catch {
      setError("重新混音失败，原版本仍然保留。");
    } finally { setRemixing(false); }
  };

  const share = async () => {
    setSharing(true); setError("");
    try {
      const result = await createShare(id, shareHours); setShareUrl(result.url);
      await navigator.clipboard?.writeText(result.url);
    } catch { setError("分享链接创建失败，请检查隐私设置。"); }
    finally { setSharing(false); }
  };

  if (!podcast) return <div className="podcast-page"><section className="progress-loading">{error ? <><AlertTriangle /><p>{error}</p></> : <><LoaderCircle className="spin" /><p>正在调出家庭播客…</p></>}</section></div>;
  const orderedMoments = momentIds.map((momentId) => podcast.moments.find((item) => item.id === momentId)).filter(Boolean);
  const naturalNarrator = podcast.metadata.tts_provider?.includes("volcengine-doubao");
  return <div className="podcast-page">
    <button className="progress-back" onClick={() => navigate(-1)}><ArrowLeft size={17} />返回高光</button>
    <header className="podcast-header"><span className="section-kicker">FAMILY PODCAST</span><h1>{podcast.title}</h1><p>用自然 AI 主持人串起家人的真实原声，不克隆任何家庭成员的声音。</p></header>
    {error && <p className="comic-error"><AlertTriangle size={15} />{error}</p>}
    <section className="podcast-hero">
      <div className="podcast-cover"><span>家庭故事豆</span><Headphones size={62} /><strong>{podcast.title}</strong><small>VOL. {String(podcast.version).padStart(2, "0")}</small></div>
      <div className="podcast-player"><div className="podcast-status"><span><Sparkles size={15} />{podcast.metadata.render_mode === "original_only" ? "原声精剪版" : "AI 主持人 + 家人原声"}</span><b>{clock(podcast.metadata.duration_ms)}</b></div>
        {playback ? <audio controls preload="metadata" src={playback.url} /> : <p>音频尚未可用</p>}
        <div className="podcast-assurances"><span><Mic2 size={15} />{naturalNarrator ? "豆包真人感 AI 主持人" : podcast.metadata.render_mode === "original_only" ? "仅保留家人原声" : "系统备用 AI 主持人"}</span><span><Volume2 size={15} />真实原声可溯源</span></div>
        {podcast.metadata.tts_fallback_used && <p className="podcast-voice-fallback"><AlertTriangle size={14} />真人感音色暂时不可用，本期已自动使用备用方案。</p>}
        {shareUrl && <span className="creation-share-url"><input readOnly value={shareUrl} /><button onClick={() => void navigator.clipboard?.writeText(shareUrl)}><Copy size={14} />复制</button></span>}
        <span className="podcast-output-actions"><button disabled={sharing} onClick={() => void share()}>{sharing ? <LoaderCircle className="spin" size={16} /> : <Share2 size={16} />}限时分享</button>{playback && <a className="primary-button" href={playback.download_url}><Download size={16} />下载 MP3</a>}</span>
      </div>
    </section>
    <section className="podcast-script"><div className="podcast-section-title"><div><span className="section-kicker">EPISODE SCRIPT</span><h2>节目脚本</h2></div><span>v{podcast.version}</span></div>
      <label><span>主持人开场 <em>AI 旁白</em></span><textarea value={intro} onChange={(event) => setIntro(event.target.value)} /></label>
      <div className="podcast-moment-order">{orderedMoments.map((moment, index) => moment && <article key={moment.id}><span>{index + 1}</span><div><strong>{moment.title}</strong><small>{clock(moment.start_ms)}–{clock(moment.end_ms)} · {moment.theme}</small></div><button aria-label="上移" disabled={index === 0} onClick={() => move(index, -1)}><ArrowUp size={15} /></button><button aria-label="下移" disabled={index === orderedMoments.length - 1} onClick={() => move(index, 1)}><ArrowDown size={15} /></button></article>)}</div>
      <div className="podcast-segments">{podcast.segments.filter((item) => item.kind === "original").map((segment) => <article key={segment.id}><span><Volume2 size={15} />家人真实原声</span><blockquote>“{segment.text}”</blockquote><small>{clock(segment.start_ms ?? 0)}–{clock(segment.end_ms ?? 0)} · 转写片段 {segment.source_segment_id?.slice(0, 8)}</small><button onClick={() => void playOriginal(segment.start_ms ?? 0, segment.end_ms ?? 0)}><Play size={14} />回到原录音试听</button></article>)}</div>
      <label><span>主持人片尾 <em>AI 旁白</em></span><textarea value={outro} onChange={(event) => setOutro(event.target.value)} /></label>
      <button className="podcast-remix primary-button" disabled={remixing || !intro.trim() || !outro.trim()} onClick={() => void remix()}>{remixing ? <LoaderCircle className="spin" size={16} /> : <RefreshCw size={16} />}{remixing ? "正在重新混音" : "保存脚本并重新混音"}</button>
    </section>
    <audio ref={originalAudio} src={originalUrl} preload="metadata" />
    <p className="comic-ai-note"><Sparkles size={13} />旁白与家人原声在数据和页面中始终分开标识。</p>
  </div>;
}
