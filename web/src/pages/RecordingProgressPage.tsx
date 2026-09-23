import { AlertTriangle, ArrowLeft, Check, Clock3, FileAudio, LoaderCircle, RotateCcw, Sparkles } from "lucide-react";
import { useCallback, useEffect, useState } from "react";
import { useNavigate, useParams } from "react-router-dom";
import { getRecording, getRecordingJob, retryJob, type Job, type Recording } from "../services/recordingApi";
import { CreationStepNav } from "../components/CreationStepNav";

const stages = [
  { key: "PREPROCESSING", label: "整理音频", detail: "检查音频结构并准备处理" },
  { key: "TRANSCRIBING", label: "识别对话", detail: "生成逐句、逐词时间戳和置信度" },
  { key: "ANALYZING", label: "发现高光", detail: "从原话中寻找温暖、欢乐和成长时刻" },
  { key: "READY_FOR_SELECTION", label: "等待确认", detail: "转写、原声和动态推荐高光已准备好" }
] as const;

const stageOrder = ["CREATED", "PREPROCESSING", "TRANSCRIBING", "ANALYZING", "READY_FOR_SELECTION"];
const terminalStages = new Set(["READY_FOR_SELECTION", "FAILED"]);

function stageCopy(job: Job) {
  if (job.stage === "FAILED") return job.dead_lettered_at ? "自动重试已用完，需要手动重跑" : "处理遇到问题，系统正在准备重试";
  return {
    CREATED: "等待 Worker 接收任务",
    PREPROCESSING: "正在读取和整理音频",
    TRANSCRIBING: "正在准备对话识别",
    ANALYZING: "正在发现值得留下的时刻",
    READY_FOR_SELECTION: "处理流程已经完成",
  }[job.stage];
}

export function RecordingProgressPage() {
  const { id = "" } = useParams();
  const navigate = useNavigate();
  const [recording, setRecording] = useState<Recording | null>(null);
  const [job, setJob] = useState<Job | null>(null);
  const [error, setError] = useState("");
  const [retrying, setRetrying] = useState(false);

  const refresh = useCallback(async () => {
    try {
      const [nextRecording, nextJob] = await Promise.all([getRecording(id), getRecordingJob(id)]);
      setRecording(nextRecording);
      setJob(nextJob);
      setError("");
    } catch {
      setError("处理状态暂时无法读取，请稍后重试。");
    }
  }, [id]);

  useEffect(() => {
    void refresh();
    const timer = window.setInterval(() => {
      if (document.visibilityState === "visible" && (!job || !terminalStages.has(job.stage))) {
        void refresh();
      }
    }, 2000);
    const onVisibility = () => {
      if (document.visibilityState === "visible") void refresh();
    };
    document.addEventListener("visibilitychange", onVisibility);
    return () => {
      window.clearInterval(timer);
      document.removeEventListener("visibilitychange", onVisibility);
    };
  }, [refresh, job?.stage]);

  useEffect(() => {
    if (job?.stage !== "READY_FOR_SELECTION") return;
    const timer = window.setTimeout(() => navigate(`/recordings/${id}/story`, { replace: true }), 700);
    return () => window.clearTimeout(timer);
  }, [id, job?.stage, navigate]);

  const retry = async () => {
    if (!job) return;
    setRetrying(true);
    setError("");
    try {
      setJob(await retryJob(job.id));
    } catch {
      setError("任务暂时无法重跑，请稍后再试。");
    } finally {
      setRetrying(false);
    }
  };

  if (!recording || !job) return <div className="progress-page"><section className="progress-loading">{error ? <><AlertTriangle /><p>{error}</p><button className="primary-button" onClick={refresh}>重新加载</button></> : <><LoaderCircle className="spin" /><p>正在恢复处理状态…</p></>}</section></div>;

  const currentIndex = stageOrder.indexOf(job.stage);
  const isReady = job.stage === "READY_FOR_SELECTION";
  const isFailed = job.stage === "FAILED";

  return <div className="progress-page">
    <CreationStepNav current={1} recordingId={id} processing={!isReady && !isFailed} />
    <button className="progress-back" onClick={() => navigate("/")}><ArrowLeft size={17} />返回首页</button>
    <header className="progress-header">
      <span className="section-kicker">PROCESSING JOURNEY</span>
      <h1>{recording.title}</h1>
      <p>{stageCopy(job)}</p>
    </header>

    <section className={`progress-hero ${isFailed ? "failed" : isReady ? "ready" : ""}`}>
      <div className="progress-hero-icon">{isFailed ? <AlertTriangle /> : isReady ? <Check /> : <Sparkles />}</div>
      <div><span>{isFailed ? "处理失败" : isReady ? "已经准备好" : "AI 正在工作"}</span><strong>{job.progress}%</strong></div>
      <div className="progress-track"><span style={{ width: `${job.progress}%` }} /></div>
      <small><Clock3 size={13} />页面关闭后任务仍会继续，再次打开自动恢复</small>
    </section>

    <section className="journey-card">
      {stages.map((stage, index) => {
        const done = isReady || currentIndex > stageOrder.indexOf(stage.key);
        const active = !isFailed && job.stage === stage.key;
        return <div className={`journey-step ${done ? "done" : ""} ${active ? "active" : ""}`} key={stage.key}>
          <span>{done ? <Check size={15} /> : active ? <LoaderCircle className="spin" size={15} /> : index + 1}</span>
          <div><strong>{stage.label}</strong><small>{stage.detail}</small></div>
        </div>;
      })}
    </section>

    <section className="job-meta-card">
      <div><FileAudio size={20} /><span><small>文件</small><strong>{recording.original_file_name}</strong></span></div>
      <div><RotateCcw size={20} /><span><small>自动重试</small><strong>{job.retry_count} / 2</strong></span></div>
      <div><Clock3 size={20} /><span><small>最近心跳</small><strong>{job.heartbeat_at ? new Date(job.heartbeat_at).toLocaleTimeString("zh-CN") : "等待中"}</strong></span></div>
    </section>

    {isFailed && <section className="job-error-card">
      <div><AlertTriangle size={20} /><span><strong>{job.error_code ?? "PROCESSING_FAILED"}</strong><small>{String(job.error_detail.message ?? "任务处理失败")}</small></span></div>
      <button className="primary-button" disabled={retrying} onClick={retry}>{retrying ? <LoaderCircle className="spin" size={17} /> : <RotateCcw size={17} />}手动重跑</button>
    </section>}

    {isReady && <section className="ready-note"><Check size={20} /><div><strong>故事素材已准备好</strong><small>正在进入第 2 步，确认人物与值得留下的时刻。</small></div><button className="primary-button" onClick={() => navigate(`/recordings/${id}/story`)}>立即进入</button></section>}
  </div>;
}
