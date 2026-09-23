import {
  AlertTriangle, ArrowDown, ArrowLeft, ArrowUp, CheckCircle2, Clock3,
  EyeOff, Headphones, LoaderCircle, LockKeyhole, Play, Save, Trash2, UserRound
} from "lucide-react";
import { useEffect, useRef, useState } from "react";
import { useNavigate, useParams } from "react-router-dom";
import {
  createPodcastMaterialDraft,
  getPodcastMaterialSet,
  updatePodcastMaterialSet,
  type PodcastMaterialItem,
  type PodcastMaterialWorkspace,
  type UpdatePodcastMaterial,
} from "../services/podcastApi";
import { getPlaybackUrl } from "../services/transcriptApi";

const roleOptions = [
  { value: "setup", label: "故事铺垫" },
  { value: "highlight", label: "核心高光" },
  { value: "response", label: "家人回应" },
  { value: "ending", label: "原声收尾" },
] as const;

function clock(milliseconds: number) {
  const seconds = Math.max(0, Math.floor(milliseconds / 1000));
  return `${Math.floor(seconds / 60)}:${String(seconds % 60).padStart(2, "0")}`;
}

function toPayload(materials: PodcastMaterialItem[]): UpdatePodcastMaterial[] {
  return materials.map((item, index) => ({
    id: item.id,
    family_member_id: item.family_member_id,
    speaker_label: item.speaker_label,
    role: item.role,
    position: index + 1,
    start_ms: item.start_ms,
    end_ms: item.end_ms,
    confirmed_text: item.confirmed_text.trim(),
    share_allowed: item.share_allowed,
  }));
}

export function PodcastMaterialPage() {
  const { id = "" } = useParams();
  const navigate = useNavigate();
  const audioRef = useRef<HTMLAudioElement>(null);
  const stopAtRef = useRef<number | null>(null);
  const [workspace, setWorkspace] = useState<PodcastMaterialWorkspace | null>(null);
  const [materials, setMaterials] = useState<PodcastMaterialItem[]>([]);
  const [audioUrl, setAudioUrl] = useState("");
  const [playing, setPlaying] = useState<string | null>(null);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState("");

  const useWorkspace = (next: PodcastMaterialWorkspace) => {
    setWorkspace(next);
    setMaterials([...next.materials].sort((a, b) => a.position - b.position));
  };

  useEffect(() => {
    Promise.all([
      getPodcastMaterialSet(id).catch(() => createPodcastMaterialDraft(id)),
      getPlaybackUrl(id),
    ]).then(([nextWorkspace, nextAudioUrl]) => {
      useWorkspace(nextWorkspace);
      setAudioUrl(nextAudioUrl);
    }).catch(() => setError("声音素材暂时无法读取，请返回高光页后重试。"));
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

  const patch = (materialId: string, changes: Partial<PodcastMaterialItem>) => {
    setMaterials((current) => current.map((item) => item.id === materialId
      ? { ...item, ...changes }
      : item));
  };

  const move = (index: number, direction: -1 | 1) => {
    const target = index + direction;
    if (target < 0 || target >= materials.length) return;
    setMaterials((current) => {
      const next = [...current];
      [next[index], next[target]] = [next[target], next[index]];
      return next.map((item, itemIndex) => ({ ...item, position: itemIndex + 1 }));
    });
  };

  const remove = (materialId: string) => {
    if (materials.length <= 1) {
      setError("至少保留一段家庭原声。");
      return;
    }
    setMaterials((current) => current
      .filter((item) => item.id !== materialId)
      .map((item, index) => ({ ...item, position: index + 1 })));
  };

  const play = async (material: PodcastMaterialItem) => {
    const audio = audioRef.current;
    if (!audio) return;
    if (playing === material.id) {
      audio.pause(); setPlaying(null); return;
    }
    audio.currentTime = material.start_ms / 1000;
    stopAtRef.current = material.end_ms / 1000;
    await audio.play();
    setPlaying(material.id);
  };

  const validate = (status: "DRAFT" | "CONFIRMED") => {
    if (!materials.length || materials.length > 3) return "声音素材必须保留 1～3 段。";
    for (const item of materials) {
      if (!item.confirmed_text.trim()) return "每段声音都需要确认逐字稿。";
      if (item.end_ms <= item.start_ms || item.end_ms > (workspace?.recording_duration_ms ?? 0)) {
        return "声音片段边界无效或超出录音时长。";
      }
      if (status === "CONFIRMED" && !item.family_member_id) return "确认前需要为每段声音选择家庭成员。";
    }
    return "";
  };

  const persist = async (status: "DRAFT" | "CONFIRMED") => {
    const problem = validate(status);
    if (problem) { setError(problem); return; }
    setSaving(true); setError("");
    try {
      const next = await updatePodcastMaterialSet(id, status, toPayload(materials));
      useWorkspace(next);
    } catch {
      setError(status === "CONFIRMED" ? "声音素材没有确认成功，请检查人物与时间边界。" : "草稿没有保存成功，请重试。");
    } finally { setSaving(false); }
  };

  const revise = async () => {
    setSaving(true); setError("");
    try { useWorkspace(await createPodcastMaterialDraft(id)); }
    catch { setError("新修订版本没有创建成功，请重试。"); }
    finally { setSaving(false); }
  };

  if (!workspace) return <div className="material-page"><section className="progress-loading">
    {error ? <><AlertTriangle /><p>{error}</p></> : <><LoaderCircle className="spin" /><p>正在准备声音素材确认台…</p></>}
  </section></div>;

  const locked = workspace.status === "CONFIRMED";
  return <div className="material-page">
    <button className="progress-back" onClick={() => navigate(`/recordings/${id}/moments`)}><ArrowLeft size={17} />返回高光选择</button>
    <header className="material-header">
      <span className="section-kicker">SOUND MATERIAL DESK</span>
      <h1>确认声音故事的真实素材</h1>
      <p>先确认谁在说、原话是什么、从哪里开始和结束。AI 只能围绕这些已确认事实创作。</p>
      <div className={`material-state ${locked ? "confirmed" : "draft"}`}>{locked ? <CheckCircle2 size={16} /> : <Headphones size={16} />}{locked ? `第 ${workspace.revision} 版已确认并锁定` : `草稿第 ${workspace.revision} 版 · 转写 v${workspace.transcript_revision}`}</div>
    </header>

    <audio ref={audioRef} src={audioUrl} preload="metadata" />
    {error && <p className="moment-review-error"><AlertTriangle size={15} />{error}</p>}

    <section className="material-truth-note"><LockKeyhole size={21} /><div><strong>原始转写永不覆盖</strong><small>你可以修订播客采用的文字，但系统始终保留 ASR 原文和对应录音时间戳。</small></div></section>

    <section className="material-list">{materials.map((material, index) => <article className="material-card" key={material.id}>
      <div className="material-order"><strong>{index + 1}</strong><button disabled={locked || index === 0} onClick={() => move(index, -1)} aria-label="上移"><ArrowUp size={15} /></button><button disabled={locked || index === materials.length - 1} onClick={() => move(index, 1)} aria-label="下移"><ArrowDown size={15} /></button></div>
      <div className="material-main">
        <div className="material-card-head"><span><Clock3 size={14} />{clock(material.start_ms)}–{clock(material.end_ms)}</span><button onClick={() => void play(material)}><Play size={14} />{playing === material.id ? "暂停" : "试听这一段"}</button></div>
        <div className="material-fields">
          <label><span><UserRound size={14} />这是谁的声音</span><select disabled={locked} value={material.family_member_id ?? ""} onChange={(event) => {
            const member = workspace.family_members.find((item) => item.id === event.target.value);
            patch(material.id, { family_member_id: member?.id ?? null, speaker_label: member?.nickname ?? material.speaker_key });
          }}><option value="">请选择家庭成员</option>{workspace.family_members.map((member) => <option key={member.id} value={member.id}>{member.nickname}</option>)}</select></label>
          <label><span>在故事中的作用</span><select disabled={locked} value={material.role} onChange={(event) => patch(material.id, { role: event.target.value as PodcastMaterialItem["role"] })}>{roleOptions.map((option) => <option key={option.value} value={option.value}>{option.label}</option>)}</select></label>
        </div>
        <div className="material-original"><span>ASR 原始转写</span><p>{material.original_text}</p></div>
        <label className="material-confirmed-text"><span>播客采用的确认文本</span><textarea disabled={locked} value={material.confirmed_text} onChange={(event) => patch(material.id, { confirmed_text: event.target.value })} /></label>
        <div className="material-range"><label>开始<input disabled={locked} type="number" min="0" max={workspace.recording_duration_ms / 1000} step="0.1" value={(material.start_ms / 1000).toFixed(1)} onChange={(event) => patch(material.id, { start_ms: Math.round(Number(event.target.value) * 1000) })} />秒</label><label>结束<input disabled={locked} type="number" min="0.1" max={workspace.recording_duration_ms / 1000} step="0.1" value={(material.end_ms / 1000).toFixed(1)} onChange={(event) => patch(material.id, { end_ms: Math.round(Number(event.target.value) * 1000) })} />秒</label><small>片段时长 {((material.end_ms - material.start_ms) / 1000).toFixed(1)} 秒</small></div>
        <label className="material-privacy"><input disabled={locked} type="checkbox" checked={!material.share_allowed} onChange={(event) => patch(material.id, { share_allowed: !event.target.checked })} /><EyeOff size={15} /><span><strong>仅家庭内部使用</strong><small>包含这段原声的播客不能创建外部分享链接</small></span></label>
      </div>
      {!locked && <button className="material-delete" disabled={materials.length === 1} onClick={() => remove(material.id)} aria-label="删除声音片段"><Trash2 size={16} /></button>}
    </article>)}</section>

    <footer className="material-actions">
      <div><strong>{materials.length} 段家庭原声 · 共 {(materials.reduce((sum, item) => sum + item.end_ms - item.start_ms, 0) / 1000).toFixed(1)} 秒</strong><small>{locked ? "确认版本不会被后续修改覆盖" : "保存草稿不会触发 AI 创作或音频生成"}</small></div>
      {locked ? <button className="secondary-button" disabled={saving} onClick={() => void revise()}>{saving ? <LoaderCircle className="spin" size={16} /> : null}创建新修订</button> : <><button className="secondary-button" disabled={saving} onClick={() => void persist("DRAFT")}><Save size={16} />保存草稿</button><button className="primary-button" disabled={saving} onClick={() => void persist("CONFIRMED")}>{saving ? <LoaderCircle className="spin" size={16} /> : <CheckCircle2 size={16} />}确认声音素材</button></>}
    </footer>
    {locked && <section className="material-next-stage"><CheckCircle2 size={22} /><div><strong>声音事实已经准备好</strong><small>现在可以基于这份锁定版本生成第三人称串讲草案。</small></div><button className="primary-button" onClick={() => navigate(`/recordings/${id}/plan`)}>进入串讲创作</button></section>}
  </div>;
}
