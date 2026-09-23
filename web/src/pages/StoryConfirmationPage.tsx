import {
  AlertTriangle, Check, Edit3, Headphones, LoaderCircle, Pause, Play,
  RefreshCw, Save, Sparkles, UsersRound, X
} from "lucide-react";
import { useEffect, useMemo, useRef, useState } from "react";
import { useNavigate, useParams } from "react-router-dom";
import { CreationStepNav } from "../components/CreationStepNav";
import { listMoments, rebuildMoments, updateMoment, type Moment } from "../services/momentApi";
import { saveMomentAsHighlight } from "../services/highlightApi";
import {
  createPodcastMaterialDraft, createPodcastPlanDraft, createPodcastRenderJob,
  updatePodcastMaterialSet, updatePodcastPlan, type PodcastNarrativeStyle,
} from "../services/podcastApi";
import {
  getPlaybackUrl, getTranscript, updateSpeakerMapping, updateTranscriptSegment,
  type Transcript, type TranscriptSegment,
} from "../services/transcriptApi";

function clock(milliseconds: number) {
  const seconds = Math.max(0, Math.floor(milliseconds / 1000));
  return `${Math.floor(seconds / 60)}:${String(seconds % 60).padStart(2, "0")}`;
}

function targetMomentCount(durationMs: number) {
  const minutes = durationMs / 60_000;
  if (minutes <= 5) return 5;
  if (minutes <= 10) return 7;
  if (minutes <= 15) return 10;
  if (minutes <= 30) return 15;
  return 20;
}

const narrativeStyles: Array<{ value: PodcastNarrativeStyle; label: string }> = [
  { value: "warm", label: "温暖自然" },
  { value: "humorous", label: "轻松有趣" },
  { value: "growth", label: "成长记录" },
  { value: "documentary", label: "家庭纪实" },
];

export function StoryConfirmationPage() {
  const { id = "" } = useParams();
  const navigate = useNavigate();
  const audioRef = useRef<HTMLAudioElement>(null);
  const stopAtRef = useRef<number | null>(null);
  const [transcript, setTranscript] = useState<Transcript | null>(null);
  const [moments, setMoments] = useState<Moment[]>([]);
  const [audioUrl, setAudioUrl] = useState("");
  const [editing, setEditing] = useState<string | null>(null);
  const [draft, setDraft] = useState("");
  const [playing, setPlaying] = useState<string | null>(null);
  const [style, setStyle] = useState<PodcastNarrativeStyle>("warm");
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [generating, setGenerating] = useState(false);
  const [error, setError] = useState("");
  const [savedHighlights, setSavedHighlights] = useState<Set<string>>(new Set());
  const [savingHighlight, setSavingHighlight] = useState<string | null>(null);

  useEffect(() => {
    let active = true;
    Promise.all([getTranscript(id), listMoments(id), getPlaybackUrl(id)])
      .then(async ([nextTranscript, nextMoments, nextUrl]) => {
        const target = targetMomentCount(nextTranscript.duration_ms);
        let candidates = nextMoments.length < Math.min(target, nextTranscript.segments.length)
          ? await rebuildMoments(id) : nextMoments;
        if (candidates.length && !candidates.some((item) => item.selection_state === "kept")) {
          candidates = await Promise.all(candidates.map((item) => (
            updateMoment(item.id, { selection_state: "kept" })
          )));
        }
        if (!active) return;
        setTranscript(nextTranscript); setMoments(candidates); setAudioUrl(nextUrl);
      })
      .catch(() => active && setError("故事素材暂时无法读取，请稍后重试。"))
      .finally(() => active && setLoading(false));
    return () => { active = false; };
  }, [id]);

  useEffect(() => {
    const audio = audioRef.current;
    if (!audio) return;
    const onTime = () => {
      if (stopAtRef.current !== null && audio.currentTime >= stopAtRef.current) {
        audio.pause(); stopAtRef.current = null; setPlaying(null);
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

  const speakerNames = useMemo(() => Object.fromEntries(
    (transcript?.speakers ?? []).map((speaker) => [speaker.speaker_key, speaker.display_name])
  ), [transcript]);
  const speakerSamples = useMemo(() => Object.fromEntries(
    (transcript?.speakers ?? []).map((speaker) => {
      const sample = (transcript?.segments ?? [])
        .filter((segment) => segment.speaker_key === speaker.speaker_key && segment.end_ms > segment.start_ms)
        .sort((left, right) => {
          const confidenceGap = (right.confidence ?? 0) - (left.confidence ?? 0);
          if (Math.abs(confidenceGap) > 0.05) return confidenceGap;
          return (right.end_ms - right.start_ms) - (left.end_ms - left.start_ms);
        })[0];
      return [speaker.speaker_key, sample];
    })
  ), [transcript]);
  const keptCount = moments.filter((item) => item.selection_state === "kept").length;

  const playRange = async (key: string, startMs: number, endMs: number) => {
    const audio = audioRef.current;
    if (!audio) return;
    if (playing === key) { audio.pause(); setPlaying(null); return; }
    audio.currentTime = startMs / 1000; stopAtRef.current = endMs / 1000;
    try { await audio.play(); setPlaying(key); }
    catch { stopAtRef.current = null; setError("原声暂时无法播放，请刷新页面后重试。"); }
  };

  const mapSpeaker = async (speakerKey: string, memberId: string) => {
    if (!transcript) return;
    const member = transcript.family_members.find((item) => item.id === memberId);
    try {
      const mapping = await updateSpeakerMapping(
        id, speakerKey, member?.id ?? null, member?.nickname ?? speakerNames[speakerKey]
      );
      setTranscript({
        ...transcript,
        speakers: transcript.speakers.map((item) => item.speaker_key === speakerKey ? mapping : item),
      });
    } catch { setError("人物标注未保存，请重试。"); }
  };

  const saveText = async (segment: TranscriptSegment) => {
    if (!draft.trim()) return;
    setSaving(true);
    try {
      const updated = await updateTranscriptSegment(id, segment.id, { text: draft.trim() });
      setTranscript((current) => current ? {
        ...current,
        segments: current.segments.map((item) => item.id === updated.id ? updated : item),
      } : current);
      setEditing(null);
      setMoments(await rebuildMoments(id));
    } catch { setError("文字修改未保存，请重试。"); }
    finally { setSaving(false); }
  };

  const selectMoment = async (moment: Moment, keep: boolean) => {
    try {
      const updated = await updateMoment(moment.id, { selection_state: keep ? "kept" : "dismissed" });
      setMoments((current) => current.map((item) => item.id === updated.id ? updated : item));
    } catch { setError("高光选择没有保存，请重试。"); }
  };

  const saveHighlight = async (moment: Moment) => {
    setSavingHighlight(moment.id); setError("");
    try {
      if (moment.selection_state !== "kept") {
        const updated = await updateMoment(moment.id, { selection_state: "kept" });
        setMoments((current) => current.map((item) => item.id === updated.id ? updated : item));
      }
      await saveMomentAsHighlight(moment.id);
      setSavedHighlights((current) => new Set(current).add(moment.id));
    } catch { setError("高光作品暂时无法保存，请重试。"); }
    finally { setSavingHighlight(null); }
  };

  const generatePodcast = async () => {
    if (!keptCount) return;
    setGenerating(true); setError("");
    try {
      const materialWorkspace = await createPodcastMaterialDraft(id);
      const confirmedMaterials = await updatePodcastMaterialSet(id, "CONFIRMED", materialWorkspace.materials.map((item, index) => ({
        id: item.id,
        family_member_id: item.family_member_id,
        speaker_label: item.speaker_label,
        role: index === 0 ? "setup" : index === materialWorkspace.materials.length - 1 ? "ending" : "highlight",
        position: index + 1,
        start_ms: item.start_ms,
        end_ms: item.end_ms,
        confirmed_text: item.confirmed_text,
        share_allowed: item.share_allowed,
      })));
      if (confirmedMaterials.status !== "CONFIRMED") throw new Error("materials not confirmed");
      const planWorkspace = await createPodcastPlanDraft(id, style);
      await updatePodcastPlan(id, "CONFIRMED", planWorkspace.plan);
      await createPodcastRenderJob(id);
      navigate(`/recordings/${id}/render`, { replace: true });
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "播客创作没有启动成功，请重试。");
      setGenerating(false);
    }
  };

  if (loading || !transcript) return <div className="story-confirm-page"><CreationStepNav current={2} recordingId={id} processing /><section className="progress-loading">{error ? <><AlertTriangle /><p>{error}</p></> : <><LoaderCircle className="spin" /><p>正在整理故事素材…</p></>}</section></div>;

  return <div className="story-confirm-page">
    <CreationStepNav current={2} recordingId={id} />
    <header className="story-confirm-header"><span className="section-kicker">STORY CHECK</span><h1>确认这段家庭故事</h1><p>只需确认真实原声。人物可以跳过，AI 会自动完成串讲、排序和混音。</p></header>
    <section className="story-source-summary"><Headphones size={22} /><div><strong>{transcript.title}</strong><small>{clock(transcript.duration_ms)} · {transcript.asr_model} · {moments.length} 个候选时刻</small></div><audio ref={audioRef} src={audioUrl} controls preload="metadata" /></section>
    {error && <p className="moment-review-error"><AlertTriangle size={15} />{error}</p>}

    <section className="story-section"><div className="story-section-heading"><UsersRound size={20} /><div><h2>这些声音是谁？ <small>可跳过</small></h2><p>先试听一段代表原声，再选择对应家人；不确定也可以继续创作。</p></div></div><div className="story-speaker-grid">{transcript.speakers.map((speaker) => {
      const sample = speakerSamples[speaker.speaker_key];
      const sampleKey = `speaker-${speaker.speaker_key}`;
      const sampleEnd = sample ? Math.min(sample.end_ms, sample.start_ms + 12_000) : 0;
      return <article key={speaker.speaker_key} className="story-speaker-card"><div><strong>{speaker.display_name}</strong>{sample && <small>代表原声 · {clock(sample.start_ms)}</small>}</div>{sample ? <><button type="button" className={playing === sampleKey ? "playing" : ""} onClick={() => void playRange(sampleKey, sample.start_ms, sampleEnd)}>{playing === sampleKey ? <Pause size={15} /> : <Play size={15} />}{playing === sampleKey ? "暂停试听" : "试听这段声音"}</button><p>“{sample.text}”</p></> : <p className="story-speaker-empty">没有找到可试听片段</p>}<label><span>这位是</span><select aria-label={`${speaker.display_name}对应的家庭成员`} value={speaker.family_member_id ?? ""} onChange={(event) => void mapSpeaker(speaker.speaker_key, event.target.value)}><option value="">暂不确定</option>{transcript.family_members.map((member) => <option key={member.id} value={member.id}>{member.nickname}</option>)}</select></label></article>;
    })}</div></section>

    <details className="story-transcript"><summary><span><Edit3 size={17} />检查转写文字</span><small>仅低置信度内容需要特别确认</small></summary><div>{transcript.segments.map((segment) => {
      const low = segment.confidence !== null && segment.confidence < transcript.low_confidence_threshold;
      return <article key={segment.id} className={low ? "low-confidence" : ""}><button onClick={() => void playRange(segment.id, segment.start_ms, segment.end_ms)} aria-label="试听这句"><Play size={14} /></button><div><small>{speakerNames[segment.speaker_key] ?? segment.speaker_key} · {clock(segment.start_ms)}{low ? " · 请确认" : ""}</small>{editing === segment.id ? <div className="story-inline-editor"><textarea value={draft} onChange={(event) => setDraft(event.target.value)} /><button disabled={saving} onClick={() => void saveText(segment)}><Save size={14} />保存</button></div> : <p>{segment.text}</p>}</div>{editing !== segment.id && <button onClick={() => { setEditing(segment.id); setDraft(segment.text); }} aria-label="修改文字"><Edit3 size={14} /></button>}</article>;
    })}</div></details>

    <section className="story-section story-moments"><div className="story-section-heading"><Sparkles size={20} /><div><h2>值得留下的时刻</h2><p>根据 {clock(transcript.duration_ms)} 素材动态推荐 {moments.length} 条，至少保留 1 条。</p></div><button className="story-refresh" onClick={() => void rebuildMoments(id).then(setMoments)}><RefreshCw size={14} />重新分析</button></div><div className="story-moment-grid">{moments.map((moment) => {
      const kept = moment.selection_state === "kept";
      return <article key={moment.id} className={kept ? "kept" : moment.selection_state}><div><span>{moment.theme}</span><time>{clock(moment.start_ms)}–{clock(moment.end_ms)}</time></div><h3>{moment.title}</h3><blockquote>“{moment.storyboard.highlight_quote}”</blockquote><footer><button onClick={() => void playRange(moment.id, moment.start_ms, moment.end_ms)}>{playing === moment.id ? <Pause size={14} /> : <Play size={14} />}试听</button><button className={kept ? "selected" : ""} onClick={() => void selectMoment(moment, !kept)}>{kept ? <><Check size={14} />已选</> : <><Sparkles size={14} />选入播客</>}</button><button className={savedHighlights.has(moment.id) ? "selected" : ""} disabled={savingHighlight === moment.id || savedHighlights.has(moment.id)} onClick={() => void saveHighlight(moment)}>{savingHighlight === moment.id ? <LoaderCircle className="spin" size={14} /> : <Save size={14} />}{savedHighlights.has(moment.id) ? "已存为高光" : "单独保存"}</button>{moment.selection_state === "dismissed" && <X size={14} />}</footer></article>;
    })}</div></section>

    <footer className="story-generate-bar"><div><strong>已选择 {keptCount} 个家庭时刻</strong><small>下一步会自动生成串讲、编排和试听音频</small></div><label>串讲语气<select value={style} onChange={(event) => setStyle(event.target.value as PodcastNarrativeStyle)}>{narrativeStyles.map((item) => <option key={item.value} value={item.value}>{item.label}</option>)}</select></label><button className="primary-button" disabled={!keptCount || generating} onClick={() => void generatePodcast()}>{generating ? <LoaderCircle className="spin" size={17} /> : <Headphones size={17} />}{generating ? "正在创作…" : `生成家庭播客`}</button></footer>
  </div>;
}
