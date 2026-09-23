import { AlertTriangle, ArrowLeft, Check, ChevronDown, ChevronUp, Clock3, Headphones, LoaderCircle, Pause, Play, Sparkles, X } from "lucide-react";
import { useEffect, useRef, useState } from "react";
import { useNavigate, useParams } from "react-router-dom";
import { env } from "../config/env";
import { listMoments, updateMoment, type Moment } from "../services/momentApi";
import { getPlaybackUrl } from "../services/transcriptApi";
import { createComic } from "../services/comicApi";
import { createPodcastMaterialDraft } from "../services/podcastApi";

function clock(milliseconds: number) {
  const total = Math.max(0, Math.floor(milliseconds / 1000));
  return `${Math.floor(total / 60)}:${String(total % 60).padStart(2, "0")}`;
}

const scoreLabels: Record<string, string> = {
  humor: "欢乐", warmth: "温暖", surprise: "转折", expression: "情绪",
  participation: "参与", completeness: "完整", reliability: "可信"
};

export function MomentSelectionPage() {
  const { id = "" } = useParams();
  const navigate = useNavigate();
  const audioRef = useRef<HTMLAudioElement>(null);
  const stopAtRef = useRef<number | null>(null);
  const [moments, setMoments] = useState<Moment[]>([]);
  const [audioUrl, setAudioUrl] = useState("");
  const [expanded, setExpanded] = useState<string | null>(null);
  const [playing, setPlaying] = useState<string | null>(null);
  const [saving, setSaving] = useState<string | null>(null);
  const [creatingComic, setCreatingComic] = useState(false);
  const [creatingPodcast, setCreatingPodcast] = useState(false);
  const [error, setError] = useState("");

  useEffect(() => {
    Promise.all([listMoments(id), getPlaybackUrl(id)])
      .then(([nextMoments, url]) => { setMoments(nextMoments); setAudioUrl(url); })
      .catch(() => setError("高光暂时无法读取，请返回转写页后重试。"));
  }, [id]);

  useEffect(() => {
    const audio = audioRef.current;
    if (!audio) return;
    const onTime = () => {
      if (stopAtRef.current !== null && audio.currentTime >= stopAtRef.current) {
        audio.pause();
        setPlaying(null);
        stopAtRef.current = null;
      }
    };
    const onEnded = () => setPlaying(null);
    audio.addEventListener("timeupdate", onTime);
    audio.addEventListener("ended", onEnded);
    return () => {
      audio.removeEventListener("timeupdate", onTime);
      audio.removeEventListener("ended", onEnded);
    };
  }, [audioUrl]);

  const play = async (moment: Moment) => {
    const audio = audioRef.current;
    if (!audio) return;
    if (playing === moment.id) {
      audio.pause(); setPlaying(null); return;
    }
    audio.currentTime = moment.start_ms / 1000;
    stopAtRef.current = moment.end_ms / 1000;
    await audio.play();
    setPlaying(moment.id);
  };

  const patch = async (moment: Moment, changes: Parameters<typeof updateMoment>[1]) => {
    setSaving(moment.id); setError("");
    try {
      const updated = await updateMoment(moment.id, changes);
      setMoments((current) => current.map((item) => item.id === updated.id ? updated : item));
    } catch {
      setError("这次修改没有保存，请重试。");
    } finally {
      setSaving(null);
    }
  };

  const openComic = async () => {
    const kept = moments.find((item) => item.selection_state === "kept");
    if (!kept) return;
    setCreatingComic(true); setError("");
    try {
      const comic = await createComic(kept.id);
      navigate(`/comics/${comic.id}`);
    } catch {
      setError("漫画暂时无法生成，请稍后重试。");
      setCreatingComic(false);
    }
  };

  const openPodcast = async () => {
    const kept = moments.filter((item) => item.selection_state === "kept").slice(0, 3);
    if (!kept.length) return;
    setCreatingPodcast(true); setError("");
    try {
      await createPodcastMaterialDraft(id);
      navigate(`/recordings/${id}/materials`);
    } catch {
      setError("声音素材确认台暂时无法创建，请确认已保留 1～3 个高光。");
      setCreatingPodcast(false);
    }
  };

  if (!moments.length && !error) return <div className="moment-review-page"><section className="progress-loading"><LoaderCircle className="spin" /><p>正在整理最值得留下的时刻…</p></section></div>;

  return <div className="moment-review-page">
    <button className="progress-back" onClick={() => navigate(`/recordings/${id}/transcript`)}><ArrowLeft size={17} />返回转写校对</button>
    <header className="moment-review-header"><span className="section-kicker">FAMILY HIGHLIGHTS</span><h1>选出想留下的家庭时刻</h1><p>AI 先找出三个候选，每句原话都能回到录音。你可以试听、调整边界或删除。</p></header>
    <audio ref={audioRef} src={audioUrl} preload="metadata" />
    {error && <p className="moment-review-error"><AlertTriangle size={16} />{error}</p>}
    <section className="moment-review-list">{moments.map((moment) => {
      const isExpanded = expanded === moment.id;
      return <article key={moment.id} className={`moment-review-card ${moment.selection_state}`}>
        <div className="moment-rank">{moment.rank}</div>
        <div className="moment-review-main">
          <div className="moment-review-meta"><span>{moment.theme}</span><time><Clock3 size={13} />{clock(moment.start_ms)}–{clock(moment.end_ms)}</time><b>{Math.round(moment.score * 100)} 分</b></div>
          <h2>{moment.title}</h2>
          <blockquote>“{moment.storyboard.highlight_quote}”</blockquote>
          <div className="moment-characters">{moment.storyboard.characters.map((character) => <span key={character.speaker_key}>{character.display_name}</span>)}</div>
          <div className="moment-review-actions">
            <button className="moment-play-button" onClick={() => void play(moment)}>{playing === moment.id ? <Pause size={16} /> : <Play size={16} />}{playing === moment.id ? "暂停" : "试听原声"}</button>
            <button className={moment.selection_state === "kept" ? "keep active" : "keep"} disabled={saving === moment.id} onClick={() => void patch(moment, { selection_state: "kept" })}><Check size={16} />保留</button>
            <button className={moment.selection_state === "dismissed" ? "dismiss active" : "dismiss"} disabled={saving === moment.id} onClick={() => void patch(moment, { selection_state: "dismissed" })}><X size={16} />不保留</button>
            <button className="story-toggle" onClick={() => setExpanded(isExpanded ? null : moment.id)}>故事板{isExpanded ? <ChevronUp size={15} /> : <ChevronDown size={15} />}</button>
          </div>
          {isExpanded && <div className="storyboard-panel">
            <div className="story-flow"><span><small>开场</small>{moment.storyboard.setup}</span><span><small>转折</small>{moment.storyboard.turning_point}</span><span><small>结尾</small>{moment.storyboard.ending}</span></div>
            <div className="emotion-curve">{moment.storyboard.emotion_curve.map((emotion) => <span key={emotion}>{emotion}</span>)}</div>
            <details><summary>查看原话证据 · {moment.storyboard.source_segments.length} 句</summary>{moment.storyboard.source_segments.map((source) => <p key={source.transcript_segment_id}><time>{clock(source.start_ms)}</time>{source.quote}</p>)}</details>
            <BoundaryEditor moment={moment} onSave={(start, end) => void patch(moment, { start_ms: start, end_ms: end })} disabled={saving === moment.id} />
            <div className="score-reasons"><strong><Sparkles size={15} />为什么推荐</strong>{Object.entries(moment.score_breakdown).map(([key, value]) => <span key={key}>{scoreLabels[key] ?? key}<i style={{ width: `${value * 100}%` }} /></span>)}</div>
          </div>}
        </div>
      </article>;
    })}</section>
    <footer className="moment-review-footer"><span>已保留 {moments.filter((item) => item.selection_state === "kept").length} 个时刻</span><div className="moment-create-actions">{env.features.comicCreation && <button className="secondary-button" disabled={!moments.some((item) => item.selection_state === "kept") || creatingComic || creatingPodcast} onClick={() => void openComic()}>{creatingComic ? <LoaderCircle className="spin" size={16} /> : null}{creatingComic ? "正在生成" : "家庭漫画"}</button>}{env.features.podcastCreation && <button className="primary-button" disabled={!moments.some((item) => item.selection_state === "kept") || creatingComic || creatingPodcast} onClick={() => void openPodcast()}>{creatingPodcast ? <LoaderCircle className="spin" size={16} /> : <Headphones size={16} />}{creatingPodcast ? "正在混音" : "生成家庭播客"}</button>}</div><small>{env.features.podcastCreation ? "先确认 1～3 个声音片段，再由 AI 生成第三人称串讲" : "播客创建正在灰度中，已生成作品仍可在时光页播放"}</small></footer>
  </div>;
}

function BoundaryEditor({ moment, onSave, disabled }: { moment: Moment; onSave: (start: number, end: number) => void; disabled: boolean }) {
  const [start, setStart] = useState(moment.start_ms / 1000);
  const [end, setEnd] = useState(moment.end_ms / 1000);
  useEffect(() => { setStart(moment.start_ms / 1000); setEnd(moment.end_ms / 1000); }, [moment.start_ms, moment.end_ms]);
  return <div className="boundary-editor"><strong>调整原声边界</strong><label>开始<input type="number" min="0" step="0.1" value={start} onChange={(event) => setStart(Number(event.target.value))} />秒</label><label>结束<input type="number" min={start + 0.1} step="0.1" value={end} onChange={(event) => setEnd(Number(event.target.value))} />秒</label><button disabled={disabled || end <= start} onClick={() => onSave(Math.round(start * 1000), Math.round(end * 1000))}>保存边界</button></div>;
}
