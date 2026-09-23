import {
  AlertTriangle, ArrowLeft, CheckCircle2, Download, FileAudio2, LoaderCircle,
  Music2, RefreshCw, ShieldCheck, Volume2, WandSparkles
} from "lucide-react";
import { useCallback, useEffect, useMemo, useState } from "react";
import { useNavigate, useParams } from "react-router-dom";
import { ApiClientError } from "../services/apiClient";
import { CreationStepNav } from "../components/CreationStepNav";
import {
  createPodcastRenderJob, getPodcastRenderJob, getPodcastRenderPlayback,
  getRecordingPodcastRenderJob, retryPodcastRenderJob,
  type PodcastRenderPlayback, type PodcastRenderResult
} from "../services/podcastApi";

const progressCopy = [
  { at: 0, label: "准备音轨与声音素材" },
  { at: 18, label: "合成第三人称 AI 解说" },
  { at: 35, label: "裁剪并串联家庭原声" },
  { at: 70, label: "混入背景音乐并自动压低音量" },
  { at: 92, label: "导出 MP3 与播放清单" },
];

function metadataText(value: unknown, fallback = "—") {
  return typeof value === "string" || typeof value === "number" ? String(value) : fallback;
}

export function PodcastRenderPage() {
  const { id = "" } = useParams();
  const navigate = useNavigate();
  const [result, setResult] = useState<PodcastRenderResult | null>(null);
  const [playback, setPlayback] = useState<PodcastRenderPlayback | null>(null);
  const [loading, setLoading] = useState(true);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");

  const loadPlayback = useCallback(async (jobId: string) => {
    try { setPlayback(await getPodcastRenderPlayback(jobId)); }
    catch { setError("音频已完成，但播放地址暂时无法签发。"); }
  }, []);

  useEffect(() => {
    let active = true;
    getRecordingPodcastRenderJob(id).then((next) => {
      if (!active) return;
      setResult(next);
      if (next.job.status === "COMPLETED") void loadPlayback(next.job.id);
    }).catch(async (reason: unknown) => {
      if (reason instanceof ApiClientError && reason.code === "PODCAST_RENDER_NOT_FOUND") {
        try { if (active) setResult(await createPodcastRenderJob(id)); }
        catch { if (active) setError("播客制作没有自动启动，请重试。"); }
      } else {
        setError("制作任务暂时无法读取。");
      }
    }).finally(() => active && setLoading(false));
    return () => { active = false; };
  }, [id, loadPlayback]);

  useEffect(() => {
    if (!result || !["CREATED", "GENERATING"].includes(result.job.status)) return;
    const timer = window.setInterval(async () => {
      try {
        const next = await getPodcastRenderJob(result.job.id);
        setResult(next);
        if (next.job.status === "COMPLETED") {
          window.clearInterval(timer);
          await loadPlayback(next.job.id);
        }
      } catch { setError("进度更新中断，正在等待下次查询。"); }
    }, 1800);
    return () => window.clearInterval(timer);
  }, [result?.job.id, result?.job.status, loadPlayback]);

  useEffect(() => {
    if (result?.job.status !== "COMPLETED" || !playback) return;
    const timer = window.setTimeout(() => navigate(`/recordings/${id}/podcast`, { replace: true }), 900);
    return () => window.clearTimeout(timer);
  }, [id, navigate, playback, result?.job.status]);

  const start = async () => {
    setBusy(true); setError("");
    try { setResult(await createPodcastRenderJob(id)); }
    catch (reason) { setError(reason instanceof ApiClientError ? reason.message : "播客制作没有启动成功。"); }
    finally { setBusy(false); }
  };

  const retry = async () => {
    if (!result) return;
    setBusy(true); setError(""); setPlayback(null);
    try { setResult(await retryPodcastRenderJob(result.job.id)); }
    catch (reason) { setError(reason instanceof ApiClientError ? reason.message : "重试没有启动成功。"); }
    finally { setBusy(false); }
  };

  const activeStep = useMemo(() => {
    const progress = result?.job.progress ?? 0;
    return [...progressCopy].reverse().find((item) => progress >= item.at) ?? progressCopy[0];
  }, [result?.job.progress]);

  if (loading) return <div className="render-page"><section className="progress-loading"><LoaderCircle className="spin" /><p>正在查找已有的播客制作任务…</p></section></div>;

  const status = result?.job.status;
  const metadata = playback?.render_metadata ?? result?.render_metadata ?? {};
  const fallback = metadata.render_mode === "original_only";
  return <div className="render-page">
    <CreationStepNav current={3} recordingId={id} processing={status !== "COMPLETED"} />
    <button className="progress-back" onClick={() => navigate(`/recordings/${id}/story`)}><ArrowLeft size={17} />返回确认故事</button>
    <header className="render-header"><span className="section-kicker">PODCAST MIX STUDIO</span><h1>生成家庭有声播客</h1><p>把已锁定的家人原声、AI 第三人称解说和轻背景音混成一条连贯故事线。</p></header>
    {error && <p className="moment-review-error"><AlertTriangle size={15} />{error}</p>}

    {!result && <section className="render-empty"><WandSparkles size={38} /><h2>正在启动家庭播客制作</h2><p>系统正在自动完成串讲、原声编排与混音。</p>{error && <button className="primary-button" disabled={busy} onClick={() => void start()}>{busy ? <LoaderCircle className="spin" size={16} /> : <Music2 size={16} />}重新启动</button>}</section>}

    {result && status !== "COMPLETED" && <section className={`render-progress ${status === "FAILED" ? "failed" : ""}`}>
      <div className="render-progress-head">{status === "FAILED" ? <AlertTriangle size={27} /> : <LoaderCircle className="spin" size={27} />}<div><strong>{status === "FAILED" ? "本次制作没有完成" : activeStep.label}</strong><small>{status === "FAILED" ? (result.job.error_detail.message ?? "可以保留已确认策划后重试") : "页面可以暂时离开，任务会在后台继续"}</small></div><b>{result.job.progress}%</b></div>
      <div className="render-meter"><i style={{ width: `${result.job.progress}%` }} /></div>
      <ol>{progressCopy.map((step) => <li key={step.at} className={result.job.progress >= step.at ? "done" : ""}><CheckCircle2 size={14} />{step.label}</li>)}</ol>
      {status === "FAILED" && <button className="primary-button" disabled={busy} onClick={() => void retry()}><RefreshCw size={16} />保留策划并重试</button>}
    </section>}

    {status === "COMPLETED" && <section className="render-complete">
      <div className="render-disc"><Volume2 size={36} /><span>MP3</span></div>
      <div className="render-player"><span><CheckCircle2 size={15} />家庭播客已完成</span><h2>{fallback ? "纯原声纪念版" : "家人原声 × AI 第三人称串讲"}</h2>{fallback && <p className="render-fallback"><AlertTriangle size={14} />AI 解说服务暂时不可用，本次已自动保留为完整的纯原声版。</p>}{playback ? <><audio controls preload="metadata" src={playback.url} /><p>正在进入试听与发布…</p><div className="render-finish-actions"><button className="primary-button" onClick={() => navigate(`/recordings/${id}/podcast`)}><FileAudio2 size={16} />立即试听</button><a className="secondary-button" href={playback.download_url}><Download size={16} />下载 MP3</a></div></> : <p>正在准备私密播放地址…</p>}</div>
      <div className="render-proof"><span><ShieldCheck size={15} />原声来源可追溯</span><span><Music2 size={15} />人声出现时背景音自动压低</span><span><FileAudio2 size={15} />{metadataText(metadata.duration_ms, "已生成")} {typeof metadata.duration_ms === "number" ? "ms" : ""}</span><small>合成模式：{metadataText(metadata.render_mode)} · 解说：{metadataText(metadata.tts_provider, "原声版")}</small></div>
    </section>}
  </div>;
}
