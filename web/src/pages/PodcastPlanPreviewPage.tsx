import {
  AlertTriangle, ArrowDown, ArrowLeft, ArrowUp, CheckCircle2, FileAudio, LoaderCircle,
  LockKeyhole, MessageCircleMore, Play, RefreshCw, Save, ShieldCheck,
  Sparkles, Volume2, Music2
} from "lucide-react";
import { useEffect, useMemo, useRef, useState } from "react";
import { useNavigate, useParams } from "react-router-dom";
import { ApiClientError } from "../services/apiClient";
import {
  createNarrationPreview, createPodcastPlanDraft, getPodcastPlan,
  updatePodcastPlan, type PodcastNarrativeStyle, type PodcastPlanWorkspace
} from "../services/podcastApi";
import { getPlaybackUrl } from "../services/transcriptApi";

const styles: Array<{ value: PodcastNarrativeStyle; label: string; note: string }> = [
  { value: "warm", label: "温暖陪伴", note: "柔和、自然，适合多数家庭日常" },
  { value: "humorous", label: "轻松有趣", note: "俏皮串场，保留原声里的笑点" },
  { value: "growth", label: "成长记录", note: "突出时间感与陪伴感" },
  { value: "documentary", label: "家庭纪实", note: "克制客观，按时间讲述" },
];

const voiceOptions = [
  { value: "zh_female_xiaohe_uranus_bigtts", label: "小荷 · 温柔自然" },
  { value: "zh_female_tianmeixiaoyuan_moon_bigtts", label: "甜美小媛 · 轻快" },
  { value: "zh_male_chunhou_moon_bigtts", label: "醇厚男声 · 沉稳" },
];

const musicOptions = [
  { value: "warm-acoustic-light", label: "温暖木吉他" },
  { value: "playful-ukulele-light", label: "轻快尤克里里" },
  { value: "gentle-piano-light", label: "柔和钢琴" },
  { value: "minimal-documentary-light", label: "克制纪实" },
];

export function PodcastPlanPreviewPage() {
  const { id = "" } = useParams();
  const navigate = useNavigate();
  const originalAudioRef = useRef<HTMLAudioElement>(null);
  const previewAudioRef = useRef<HTMLAudioElement | null>(null);
  const stopAtRef = useRef<number | null>(null);
  const [workspace, setWorkspace] = useState<PodcastPlanWorkspace | null>(null);
  const [style, setStyle] = useState<PodcastNarrativeStyle>("warm");
  const [sourceAudioUrl, setSourceAudioUrl] = useState("");
  const [loading, setLoading] = useState(true);
  const [busy, setBusy] = useState(false);
  const [previewing, setPreviewing] = useState<number | null>(null);
  const [needsConfirmation, setNeedsConfirmation] = useState(false);
  const [notice, setNotice] = useState("");
  const [error, setError] = useState("");

  useEffect(() => {
    getPodcastPlan(id).then((next) => {
      setWorkspace(next); setStyle(next.plan.narration_style);
    }).catch((reason: unknown) => {
      if (reason instanceof ApiClientError && reason.code === "PODCAST_MATERIALS_NOT_CONFIRMED") {
        setNeedsConfirmation(true);
      } else if (!(reason instanceof ApiClientError && reason.code === "PODCAST_PLAN_NOT_FOUND")) {
        setError("串讲草案暂时无法读取，请稍后重试。");
      }
    }).finally(() => setLoading(false));
    getPlaybackUrl(id).then(setSourceAudioUrl).catch(() => undefined);
  }, [id]);

  useEffect(() => {
    const audio = originalAudioRef.current;
    if (!audio) return;
    const onTime = () => {
      if (stopAtRef.current !== null && audio.currentTime >= stopAtRef.current) {
        audio.pause(); stopAtRef.current = null;
      }
    };
    audio.addEventListener("timeupdate", onTime);
    return () => audio.removeEventListener("timeupdate", onTime);
  }, [sourceAudioUrl]);

  const generate = async () => {
    setBusy(true); setError(""); setNotice("");
    try { setWorkspace(await createPodcastPlanDraft(id, style)); }
    catch (reason) {
      if (reason instanceof ApiClientError && reason.code === "PODCAST_MATERIALS_NOT_CONFIRMED") {
        setNeedsConfirmation(true);
      } else setError("串讲草案没有生成成功，请重试。");
    } finally { setBusy(false); }
  };

  const patchPlan = (changes: Partial<PodcastPlanWorkspace["plan"]>) => {
    setWorkspace((current) => current ? { ...current, plan: { ...current.plan, ...changes } } : current);
  };

  const patchNarration = (segmentIndex: number, text: string) => {
    if (!workspace) return;
    patchPlan({ segments: workspace.plan.segments.map((segment) =>
      segment.segment_index === segmentIndex ? { ...segment, text } : segment
    ) });
  };

  const moveSegment = (index: number, direction: -1 | 1) => {
    if (!workspace) return;
    const target = index + direction;
    if (target < 0 || target >= workspace.plan.segments.length) return;
    const next = [...workspace.plan.segments];
    [next[index], next[target]] = [next[target], next[index]];
    patchPlan({ segments: next.map((segment, itemIndex) => ({
      ...segment, segment_index: itemIndex + 1,
    })) });
  };

  const persist = async (status: "DRAFT" | "CONFIRMED") => {
    if (!workspace) return;
    setBusy(true); setError(""); setNotice("");
    try {
      const next = await updatePodcastPlan(id, status, workspace.plan);
      setWorkspace(next);
      setNotice(status === "CONFIRMED"
        ? "策划已经锁定。正式音频尚未生成，将在下一阶段进入混音。"
        : "串讲草案已保存并重新通过事实校验。");
    } catch (reason) {
      setError(reason instanceof ApiClientError ? reason.message : "策划没有保存成功，请重试。");
    } finally { setBusy(false); }
  };

  const previewNarration = async (segmentIndex: number) => {
    if (!workspace) return;
    setPreviewing(segmentIndex); setError("");
    try {
      if (workspace.plan.status === "DRAFT") {
        setWorkspace(await updatePodcastPlan(id, "DRAFT", workspace.plan));
      }
      const result = await createNarrationPreview(id, segmentIndex);
      previewAudioRef.current?.pause();
      previewAudioRef.current = new Audio(result.url);
      await previewAudioRef.current.play();
      setNotice(`正在试听 AI 解说 · ${result.provider}`);
    } catch (reason) {
      setError(reason instanceof ApiClientError ? reason.message : "解说试听暂时不可用。");
    } finally { setPreviewing(null); }
  };

  const playOriginal = async (sourceId: string) => {
    const source = workspace?.materials.find((item) => item.id === sourceId);
    const audio = originalAudioRef.current;
    if (!source || !audio) return;
    previewAudioRef.current?.pause();
    audio.currentTime = source.start_ms / 1000;
    stopAtRef.current = source.end_ms / 1000;
    await audio.play();
    setNotice(`正在试听家庭原声 · ${source.speaker_label}`);
  };

  const materials = useMemo(() => new Map(
    workspace?.materials.map((item) => [item.id, item]) ?? []
  ), [workspace]);

  if (loading) return <div className="plan-page"><section className="progress-loading"><LoaderCircle className="spin" /><p>正在核对声音事实与串讲草案…</p></section></div>;

  if (needsConfirmation) return <div className="plan-page"><button className="progress-back" onClick={() => navigate(`/recordings/${id}/materials`)}><ArrowLeft size={17} />返回声音素材</button><section className="plan-blocked"><LockKeyhole size={32} /><h1>先确认声音素材</h1><p>串讲只能基于已锁定的家人原声生成。当前草稿仍可修改，因此系统没有提前创作。</p><button className="primary-button" onClick={() => navigate(`/recordings/${id}/materials`)}>去确认声音素材</button></section></div>;

  const locked = workspace?.plan.status === "CONFIRMED";
  return <div className="plan-page">
    <button className="progress-back" onClick={() => navigate(`/recordings/${id}/materials`)}><ArrowLeft size={17} />返回声音素材</button>
    <header className="plan-header"><span className="section-kicker">PODCAST REVIEW DESK</span><h1>{workspace?.plan.title ?? "生成第三人称串讲"}</h1><p>从头到尾检查最终播放顺序。AI 解说可以修改，家人原声保持锁定并可随时回听。</p></header>
    <audio ref={originalAudioRef} src={sourceAudioUrl} preload="metadata" />
    {error && <p className="moment-review-error"><AlertTriangle size={15} />{error}</p>}
    {notice && <p className="plan-notice"><CheckCircle2 size={15} />{notice}</p>}

    <section className="plan-generator">
      <div>{locked ? <LockKeyhole size={22} /> : <Sparkles size={22} />}<div><strong>{workspace ? `${locked ? "已锁定" : "草案"}第 ${workspace.plan.revision} 版` : "选择一种串讲语气"}</strong><small>{locked ? "该版本不会被后续编辑覆盖" : "重新生成会保留声音事实，只改变第三人称解说"}</small></div></div>
      <label>第三人称风格<select disabled={locked} value={style} onChange={(event) => setStyle(event.target.value as PodcastNarrativeStyle)}>{styles.map((item) => <option key={item.value} value={item.value}>{item.label} · {item.note}</option>)}</select></label>
      {!locked && <button className="primary-button" disabled={busy} onClick={() => void generate()}>{busy ? <LoaderCircle className="spin" size={16} /> : workspace ? <RefreshCw size={16} /> : <Sparkles size={16} />}{workspace ? "按此风格重新生成" : "生成串讲草案"}</button>}
    </section>

    {workspace && <>
      <section className="plan-meta-editor">
        <label>播客标题<input disabled={locked} value={workspace.plan.title} maxLength={120} onChange={(event) => patchPlan({ title: event.target.value })} /></label>
        <label>播客简介<textarea disabled={locked} value={workspace.plan.description} maxLength={500} onChange={(event) => patchPlan({ description: event.target.value })} /></label>
        <label>AI 解说音色<select disabled={locked} value={workspace.plan.narrator_voice} onChange={(event) => patchPlan({ narrator_voice: event.target.value })}>{voiceOptions.map((item) => <option key={item.value} value={item.value}>{item.label}</option>)}</select></label>
        <label>背景音乐风格<select disabled={locked} value={workspace.plan.music_style} onChange={(event) => patchPlan({ music_style: event.target.value })}>{musicOptions.map((item) => <option key={item.value} value={item.value}>{item.label}</option>)}</select></label>
      </section>
      <section className="plan-assurances">
        <span><ShieldCheck size={16} />{Object.values(workspace.plan.safety_checks).every(Boolean) ? "事实与引用校验通过" : "等待重新校验"}</span>
        <span><FileAudio size={16} />{workspace.materials.length} 段原声逐字锁定</span>
        <span><LockKeyhole size={16} />{workspace.plan.external_share_allowed ? "可进入后续分享审核" : "仅家庭内部使用"}</span>
      </section>
      <section className="plan-storyline">
        <div className="plan-storyline-head"><div><span className="section-kicker">FINAL PLAY ORDER</span><h2>最终播放顺序</h2></div><small>{workspace.plan.generator_provider} · {workspace.plan.model_version}</small></div>
        {workspace.plan.segments.map((segment, index) => <article key={`${segment.kind}-${segment.source_material_ids.join("-")}-${segment.label}`} className={segment.kind}>
          <div className="plan-segment-order"><div className="plan-segment-index">{String(segment.segment_index).padStart(2, "0")}</div>{!locked && <><button disabled={index === 0 || (segment.kind === "original" && workspace.plan.segments[index - 1]?.kind === "original")} onClick={() => moveSegment(index, -1)} aria-label="上移段落"><ArrowUp size={13} /></button><button disabled={index === workspace.plan.segments.length - 1 || (segment.kind === "original" && workspace.plan.segments[index + 1]?.kind === "original")} onClick={() => moveSegment(index, 1)} aria-label="下移段落"><ArrowDown size={13} /></button></>}</div>
          <div className="plan-segment-copy"><span>{segment.kind === "original" ? <FileAudio size={14} /> : <MessageCircleMore size={14} />}{segment.kind === "original" ? "家庭原声 · 不可改写" : "AI 第三人称解说"} · {segment.label}</span>
            {segment.kind === "narration" ? <textarea disabled={locked} value={segment.text} maxLength={2000} onChange={(event) => patchNarration(segment.segment_index, event.target.value)} /> : <p>{segment.text}</p>}
            <div className="plan-segment-tools">{segment.source_material_ids.map((sourceId) => {
              const source = materials.get(sourceId);
              return <small key={sourceId}><CheckCircle2 size={12} />{source ? `来源 ${source.position} · ${source.speaker_label} · ${(source.start_ms / 1000).toFixed(1)}–${(source.end_ms / 1000).toFixed(1)} 秒` : "来源已锁定"}</small>;
            })}<button disabled={previewing !== null} onClick={() => segment.kind === "narration" ? void previewNarration(segment.segment_index) : void playOriginal(segment.source_material_ids[0])}>{previewing === segment.segment_index ? <LoaderCircle className="spin" size={13} /> : segment.kind === "narration" ? <Volume2 size={13} /> : <Play size={13} />}{segment.kind === "narration" ? "试听 AI 解说" : "试听家庭原声"}</button></div>
          </div>
        </article>)}
      </section>
      {!locked ? <footer className="plan-review-actions"><div><strong>确认前仍可继续修改</strong><small>确认后锁定本版本，但不会在本阶段提前生成完整音频。</small></div><button className="secondary-button" disabled={busy} onClick={() => void persist("DRAFT")}><Save size={16} />保存草稿</button><button className="primary-button" disabled={busy} onClick={() => void persist("CONFIRMED")}><CheckCircle2 size={16} />确认并锁定策划</button></footer> : <section className="plan-stage-note"><CheckCircle2 size={21} /><div><strong>策划版本已锁定</strong><small>标题、解说、原声顺序、音色和音乐风格已准备好，可进入后台混音。</small></div><button className="primary-button" onClick={() => navigate(`/recordings/${id}/render`)}><Music2 size={16} />进入音频制作</button></section>}
    </>}
  </div>;
}
