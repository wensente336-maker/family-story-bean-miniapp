import {
  Check, CheckCircle2, Film, Headphones, LoaderCircle, LockKeyhole,
  MessageSquareText, Music2, Sparkles, Volume2,
} from "lucide-react";
import { useEffect, useState } from "react";
import {
  createStoryPlanDraft,
  updateStoryPlan,
  type Storybook,
  type StoryPlan,
} from "../services/storybookApi";

function clock(milliseconds: number) {
  const total = Math.max(0, Math.floor(milliseconds / 1000));
  return `${Math.floor(total / 60)}:${String(total % 60).padStart(2, "0")}`;
}

const sceneLabels: Record<string, string> = {
  cover: "开场",
  setup: "建立环境",
  action: "事件发生",
  dialogue: "人物原声",
  reaction: "真实反应",
  ending: "故事收束",
};

export function SoundStoryDirector({
  storybook,
  onPlanChange,
}: {
  storybook: Storybook;
  onPlanChange: (plan: StoryPlan) => void;
}) {
  const [plan, setPlan] = useState<StoryPlan | null>(null);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState("");

  useEffect(() => {
    setPlan(null);
    setError("");
    createStoryPlanDraft(storybook.id)
      .then((next) => { setPlan(next); onPlanChange(next); })
      .catch(() => setError("声音故事线暂时无法生成，请刷新后重试。"));
  }, [onPlanChange, storybook.id]);

  const toggleClip = (sourceSegmentId: string) => {
    setPlan((current) => current ? {
      ...current,
      status: "DRAFT",
      clips: current.clips.map((clip) => clip.sourceSegmentId === sourceSegmentId
        ? { ...clip, included: !clip.included }
        : clip),
    } : current);
  };

  const confirm = async () => {
    if (!plan || !plan.clips.some((clip) => clip.included)) return;
    setSaving(true);
    setError("");
    try {
      const next = await updateStoryPlan(storybook.id, plan, "CONFIRMED");
      setPlan(next);
      onPlanChange(next);
    } catch {
      setError("声音故事线没有保存成功，请重试。至少需要保留一段家庭原声。");
    } finally {
      setSaving(false);
    }
  };

  return <section className="sound-story-director" aria-label="声音故事线导演台">
    <header className="sound-story-heading">
      <div><span><Headphones size={16} />SOUND-FIRST STORY</span><h2>先确认声音，再让 AI 画故事</h2><p>原声是事实，解说只补上下文；每一幕画面都从同一份声音故事线生成。</p></div>
      <em className={plan?.status === "CONFIRMED" ? "confirmed" : ""}>{plan?.status === "CONFIRMED" ? <><CheckCircle2 size={14} />故事线已确认</> : "等待确认"}</em>
    </header>

    <div className="sound-story-flow">
      <span className="active"><b>1</b><strong>原声事实</strong><small>人物、原话、时间边界</small></span>
      <i />
      <span className="active"><b>2</b><strong>导演分场</strong><small>画面、解说与声音策略</small></span>
      <i />
      <span className={plan?.status === "CONFIRMED" ? "active" : ""}><b>3</b><strong>统一生成</strong><small>一条主时间轴驱动绘本</small></span>
    </div>

    {!plan && !error && <div className="sound-story-loading"><LoaderCircle className="spin" /><span>正在从逐字稿整理声音事实…</span></div>}
    {error && <p className="sound-story-error">{error}</p>}
    {plan && <>
      <section className="sound-source-section">
        <div className="sound-story-section-title"><div><span>01 · SOURCE OF TRUTH</span><h3>人物原声故事线</h3></div><small><LockKeyhole size={12} />原话不可被 AI 改写</small></div>
        <div className="sound-source-list">{plan.clips.map((clip) => <label className={clip.included ? "included" : ""} key={clip.sourceSegmentId}>
          <input type="checkbox" checked={clip.included} onChange={() => toggleClip(clip.sourceSegmentId)} />
          <span className="sound-source-check">{clip.included && <Check size={14} />}</span>
          <span className="sound-source-speaker"><b>{clip.speakerName}</b><time>{clock(clip.startMs)}–{clock(clip.endMs)}</time></span>
          <q>{clip.text}</q>
          <em><Volume2 size={12} />原声</em>
        </label>)}</div>
      </section>

      <section className="director-scene-section">
        <div className="sound-story-section-title"><div><span>02 · DIRECTOR SCRIPT</span><h3>AI 场景导演脚本</h3></div><small>{plan.scenes.length} 幕 · 声音优先</small></div>
        <div className="director-scene-track">{plan.scenes.map((scene) => <article key={scene.sceneIndex}>
          <div className="director-scene-visual"><div className="director-scene-index">{String(scene.sceneIndex + 1).padStart(2, "0")}</div>{scene.assetUrl && <span className="director-scene-thumb" style={{ backgroundImage: `url(${scene.assetUrl})` }} />}</div>
          <div className="director-scene-copy">
            <span>{sceneLabels[scene.sceneKind] ?? scene.sceneKind} · {scene.storyPurpose}</span>
            <h4>{scene.title}</h4>
            <p><Film size={13} />{scene.visualDescription}</p>
            {scene.narration && <blockquote><MessageSquareText size={13} />解说：{scene.narration}</blockquote>}
            {scene.quote && <blockquote className="original"><Volume2 size={13} />{scene.speakerName}原声：“{scene.quote}”</blockquote>}
          </div>
          <div className="director-audio-stack">{scene.audioSequence.map((item, index) => <span className={item.kind} key={`${item.kind}-${index}`}>{item.kind === "original" ? <Volume2 size={11} /> : <MessageSquareText size={11} />}{item.kind === "original" ? "原声" : "解说"}</span>)}{scene.audioSequence.length === 0 && <span><Music2 size={11} />留白</span>}</div>
        </article>)}</div>
      </section>

      <footer className="sound-story-confirm">
        <div><Sparkles size={20} /><span><strong>{plan.status === "CONFIRMED" ? `第 ${plan.revision} 版声音故事线已锁定` : "确认后才会生成最终绘本"}</strong><small>任何修改都会重新编排受影响的画面、解说和混音时间轴。</small></span></div>
        <button onClick={() => void confirm()} disabled={saving || !plan.clips.some((clip) => clip.included)}>{saving ? <LoaderCircle className="spin" size={16} /> : <CheckCircle2 size={16} />}{saving ? "正在编排" : plan.status === "CONFIRMED" ? "重新确认并生成" : "确认声音故事线"}</button>
      </footer>
    </>}
  </section>;
}
