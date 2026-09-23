import { AlertTriangle, ArrowLeft, Check, Edit3, Headphones, LoaderCircle, Play, Save, Sparkles, UsersRound } from "lucide-react";
import { useEffect, useMemo, useRef, useState } from "react";
import { useNavigate, useParams } from "react-router-dom";
import {
  getPlaybackUrl,
  getTranscript,
  updateSpeakerMapping,
  updateTranscriptSegment,
  type Transcript,
  type TranscriptSegment
} from "../services/transcriptApi";
import { rebuildMoments } from "../services/momentApi";

function clock(milliseconds: number) {
  const total = Math.floor(milliseconds / 1000);
  return `${Math.floor(total / 60)}:${String(total % 60).padStart(2, "0")}`;
}

export function TranscriptPage() {
  const { id = "" } = useParams();
  const navigate = useNavigate();
  const audioRef = useRef<HTMLAudioElement>(null);
  const [transcript, setTranscript] = useState<Transcript | null>(null);
  const [audioUrl, setAudioUrl] = useState("");
  const [editing, setEditing] = useState<string | null>(null);
  const [draft, setDraft] = useState("");
  const [saving, setSaving] = useState(false);
  const [buildingMoments, setBuildingMoments] = useState(false);
  const [error, setError] = useState("");

  useEffect(() => {
    Promise.all([getTranscript(id), getPlaybackUrl(id)])
      .then(([nextTranscript, nextUrl]) => {
        setTranscript(nextTranscript);
        setAudioUrl(nextUrl);
      })
      .catch(() => setError("转写内容暂时无法读取，请稍后重试。"));
  }, [id]);

  const speakerNames = useMemo(() => Object.fromEntries(
    (transcript?.speakers ?? []).map((speaker) => [speaker.speaker_key, speaker.display_name])
  ), [transcript]);

  const playAt = async (segment: TranscriptSegment) => {
    if (!audioRef.current) return;
    audioRef.current.currentTime = segment.start_ms / 1000;
    await audioRef.current.play();
  };

  const saveText = async (segment: TranscriptSegment) => {
    if (!draft.trim()) return;
    setSaving(true);
    try {
      const updated = await updateTranscriptSegment(id, segment.id, { text: draft.trim() });
      setTranscript((current) => current ? {
        ...current,
        revision: current.revision + 1,
        segments: current.segments.map((item) => item.id === updated.id ? updated : item)
      } : current);
      setEditing(null);
    } catch {
      setError("修改未保存，请重试。");
    } finally {
      setSaving(false);
    }
  };

  const mapSpeaker = async (speakerKey: string, memberId: string) => {
    if (!transcript) return;
    const member = transcript.family_members.find((item) => item.id === memberId);
    const mapping = await updateSpeakerMapping(
      id, speakerKey, member?.id ?? null, member?.nickname ?? speakerNames[speakerKey]
    );
    setTranscript({
      ...transcript,
      revision: transcript.revision + 1,
      speakers: transcript.speakers.map((item) => item.speaker_key === speakerKey ? mapping : item),
      segments: transcript.segments.map((item) => item.speaker_key === speakerKey
        ? { ...item, family_member_id: mapping.family_member_id }
        : item)
    });
  };

  const changeSegmentSpeaker = async (segment: TranscriptSegment, speakerKey: string) => {
    const updated = await updateTranscriptSegment(id, segment.id, { speaker_key: speakerKey });
    setTranscript((current) => {
      if (!current) return current;
      const speakers = current.speakers.some((item) => item.speaker_key === speakerKey)
        ? current.speakers
        : [...current.speakers, {
            speaker_key: speakerKey,
            family_member_id: null,
            display_name: `说话人 ${speakerKey.slice(-1).toUpperCase()}`
          }];
      return {
        ...current,
        revision: current.revision + 1,
        speakers,
        segments: current.segments.map((item) => item.id === updated.id ? updated : item)
      };
    });
  };

  const openMoments = async () => {
    setBuildingMoments(true);
    setError("");
    try {
      await rebuildMoments(id);
      navigate(`/recordings/${id}/moments`);
    } catch {
      setError("高光重新整理失败，请稍后重试。");
      setBuildingMoments(false);
    }
  };

  if (!transcript) return <div className="transcript-page"><section className="progress-loading">
    {error ? <><AlertTriangle /><p>{error}</p></> : <><LoaderCircle className="spin" /><p>正在打开家庭对话…</p></>}
  </section></div>;

  return <div className="transcript-page">
    <button className="progress-back" onClick={() => navigate(`/recordings/${id}`)}><ArrowLeft size={17} />返回处理进度</button>
    <header className="transcript-header">
      <span className="section-kicker">FAMILY TRANSCRIPT</span>
      <h1>{transcript.title}</h1>
      <p>点击任意一句回到对应原声，低置信度内容会标出请你确认。</p>
    </header>

    <section className="transcript-player">
      <Headphones size={22} />
      <audio ref={audioRef} src={audioUrl} controls preload="metadata" />
      <small>{transcript.asr_provider} · {transcript.asr_model} · v{transcript.revision}</small>
    </section>

    {transcript.speakers.length > 0 && <section className="speaker-map-card">
      <div className="speaker-map-title"><UsersRound size={20} /><div><strong>这些声音是谁？</strong><small>无法确定时 AI 只使用 A/B/C，由你来确认。</small></div></div>
      <div className="speaker-map-grid">{transcript.speakers.map((speaker) => <label key={speaker.speaker_key}>
        <span>{speaker.display_name}</span>
        <select value={speaker.family_member_id ?? ""} onChange={(event) => void mapSpeaker(speaker.speaker_key, event.target.value)}>
          <option value="">暂不确定</option>
          {transcript.family_members.map((member) => <option value={member.id} key={member.id}>{member.nickname}</option>)}
        </select>
      </label>)}</div>
    </section>}

    <section className="transcript-list">
      {transcript.segments.length === 0 && <div className="empty-transcript"><Headphones /><strong>没有发现可靠的人声</strong><p>音频可能只包含环境声，系统没有将不确定内容写成家人原话。</p></div>}
      {transcript.segments.map((segment) => {
        const low = segment.confidence !== null && segment.confidence < transcript.low_confidence_threshold;
        return <article className={`transcript-row ${low ? "low-confidence" : ""}`} key={segment.id}>
          <button className="segment-play" onClick={() => void playAt(segment)} aria-label={`播放 ${clock(segment.start_ms)}`}><Play size={16} /></button>
          <div className="segment-body">
            <div className="segment-meta"><select aria-label="说话人" value={segment.speaker_key} onChange={(event) => void changeSegmentSpeaker(segment, event.target.value)}><option value="speaker_a">{speakerNames.speaker_a ?? "说话人 A"}</option><option value="speaker_b">{speakerNames.speaker_b ?? "说话人 B"}</option><option value="speaker_c">{speakerNames.speaker_c ?? "说话人 C"}</option></select><span>{clock(segment.start_ms)} – {clock(segment.end_ms)}</span>{low && <em><AlertTriangle size={12} />请确认</em>}{segment.edited_by_user && <em className="edited"><Check size={12} />已校正</em>}</div>
            {editing === segment.id ? <div className="segment-editor"><textarea value={draft} onChange={(event) => setDraft(event.target.value)} /><button disabled={saving} onClick={() => void saveText(segment)}><Save size={15} />保存</button></div> : <button className="segment-text" onClick={() => void playAt(segment)}>{segment.text}</button>}
          </div>
          {editing !== segment.id && <button className="segment-edit" onClick={() => { setEditing(segment.id); setDraft(segment.text); }} aria-label="修改转写"><Edit3 size={16} /></button>}
        </article>;
      })}
    </section>
    {error && <p className="transcript-error">{error}</p>}
    <section className="transcript-next"><div><Sparkles size={20} /><span><strong>转写和人物都确认好了吗？</strong><small>下一步会按当前修订重新整理三个家庭高光。</small></span></div><button className="primary-button" disabled={buildingMoments} onClick={() => void openMoments()}>{buildingMoments ? <LoaderCircle className="spin" size={16} /> : null}{buildingMoments ? "正在整理" : "查看家庭高光"}</button></section>
  </div>;
}
