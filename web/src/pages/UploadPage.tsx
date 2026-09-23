import {
  Check, ChevronLeft, FileAudio, FileVideo, LoaderCircle, Mic, Pause, Play,
  Radio, RotateCcw, ShieldCheck, Square, Upload, X
} from "lucide-react";
import { useEffect, useRef, useState } from "react";
import { useLocation, useNavigate } from "react-router-dom";
import { ApiClientError } from "../services/apiClient";
import { CreationStepNav } from "../components/CreationStepNav";
import {
  completeUpload, createUploadSession, inferSourceType, maxAudioDurationSeconds,
  putMedia, readMediaDuration, sha256, validateMediaSelection,
  type Recording, type RecordingSourceType, type UploadSession
} from "../services/recordingApi";

type UploadState = "ready" | "checking" | "uploading" | "verifying" | "success" | "error" | "cancelled";

const sourceLabels: Record<RecordingSourceType, string> = {
  audio_upload: "本地音频", video_upload: "本地视频",
  mobile_recording: "手机直接录音", recording_bean: "录音豆导入"
};

function durationLabel(seconds: number | null) {
  if (seconds === null) return "读取中";
  const rounded = Math.round(seconds);
  return `${Math.floor(rounded / 60)}:${String(rounded % 60).padStart(2, "0")}`;
}

function supportedRecorderMimeType() {
  if (typeof MediaRecorder === "undefined") return "";
  return ["audio/mp4", "audio/webm;codecs=opus", "audio/webm"]
    .find((type) => MediaRecorder.isTypeSupported(type)) ?? "";
}

export function UploadPage() {
  const location = useLocation();
  const navigate = useNavigate();
  const fileInputRef = useRef<HTMLInputElement>(null);
  const beanInputRef = useRef<HTMLInputElement>(null);
  const cancelRef = useRef<(() => void) | null>(null);
  const recorderRef = useRef<MediaRecorder | null>(null);
  const streamRef = useRef<MediaStream | null>(null);
  const chunksRef = useRef<Blob[]>([]);
  const timerRef = useRef<number | null>(null);
  const discardRecordingRef = useRef(false);
  const initialFile = (location.state as { file?: File } | null)?.file ?? null;
  const [mode, setMode] = useState<RecordingSourceType | null>(initialFile ? inferSourceType(initialFile) : null);
  const [file, setFile] = useState<File | null>(initialFile);
  const [title, setTitle] = useState(initialFile?.name.replace(/\.[^.]+$/, "") ?? "");
  const [duration, setDuration] = useState<number | null>(null);
  const [state, setState] = useState<UploadState>("ready");
  const [progress, setProgress] = useState(0);
  const [message, setMessage] = useState("");
  const [session, setSession] = useState<UploadSession | null>(null);
  const [digest, setDigest] = useState("");
  const [completed, setCompleted] = useState<Recording | null>(null);
  const [recorderState, setRecorderState] = useState<"idle" | "recording" | "paused">("idle");
  const [recordingSeconds, setRecordingSeconds] = useState(0);
  const [previewUrl, setPreviewUrl] = useState("");

  useEffect(() => {
    if (!file) return;
    setDuration(null); setMessage("");
    const url = URL.createObjectURL(file);
    setPreviewUrl(url);
    readMediaDuration(file).then((seconds) => {
      setDuration(seconds);
      if (seconds > maxAudioDurationSeconds) setMessage("这段内容超过 15 分钟，请裁剪后重试");
    }).catch((error: Error) => setMessage(error.message));
    return () => URL.revokeObjectURL(url);
  }, [file]);

  useEffect(() => () => {
    if (timerRef.current !== null) window.clearInterval(timerRef.current);
    streamRef.current?.getTracks().forEach((track) => track.stop());
  }, []);

  const resetUpload = () => {
    setSession(null); setDigest(""); setCompleted(null);
    setProgress(0); setState("ready");
  };

  const choose = (next: File | null, preferred?: RecordingSourceType) => {
    if (!next) return;
    const nextSource = inferSourceType(next, preferred);
    const error = validateMediaSelection(next, nextSource);
    if (error) { setMessage(error); return; }
    setMode(nextSource); setFile(next); setTitle(next.name.replace(/\.[^.]+$/, ""));
    setMessage(""); resetUpload();
  };

  const stopRecorderResources = () => {
    if (timerRef.current !== null) window.clearInterval(timerRef.current);
    timerRef.current = null;
    streamRef.current?.getTracks().forEach((track) => track.stop());
    streamRef.current = null;
  };

  const startRecording = async () => {
    setMessage("");
    if (!window.isSecureContext || !navigator.mediaDevices?.getUserMedia) {
      setMessage("手机直接录音需要 HTTPS 安全连接和麦克风权限；本机 localhost 可直接使用");
      return;
    }
    try {
      const stream = await navigator.mediaDevices.getUserMedia({ audio: { echoCancellation: true, noiseSuppression: true } });
      const mimeType = supportedRecorderMimeType();
      const recorder = mimeType ? new MediaRecorder(stream, { mimeType }) : new MediaRecorder(stream);
      streamRef.current = stream; recorderRef.current = recorder; chunksRef.current = [];
      discardRecordingRef.current = false; setRecordingSeconds(0);
      recorder.ondataavailable = (event) => { if (event.data.size > 0) chunksRef.current.push(event.data); };
      recorder.onstop = () => {
        stopRecorderResources(); setRecorderState("idle");
        if (discardRecordingRef.current || chunksRef.current.length === 0) return;
        const type = recorder.mimeType || "audio/webm";
        const extension = type.includes("mp4") ? "m4a" : "webm";
        const blob = new Blob(chunksRef.current, { type });
        choose(new File([blob], `家庭录音-${new Date().toISOString().slice(0, 19).replace(/[:T]/g, "-")}.${extension}`, { type }), "mobile_recording");
      };
      recorder.start(1000); setRecorderState("recording");
      timerRef.current = window.setInterval(() => {
        if (recorder.state !== "recording") return;
        setRecordingSeconds((current) => {
          const next = current + 1;
          if (next >= maxAudioDurationSeconds && recorder.state !== "inactive") recorder.stop();
          return next;
        });
      }, 1000);
    } catch (error) {
      stopRecorderResources();
      setMessage(error instanceof Error && error.name === "NotAllowedError" ? "未获得麦克风权限，请在浏览器设置中允许后重试" : "无法启动麦克风，请检查系统权限");
    }
  };

  const togglePause = () => {
    const recorder = recorderRef.current;
    if (!recorder) return;
    if (recorder.state === "recording") { recorder.pause(); setRecorderState("paused"); }
    else if (recorder.state === "paused") { recorder.resume(); setRecorderState("recording"); }
  };

  const finishRecording = (discard = false) => {
    discardRecordingRef.current = discard;
    const recorder = recorderRef.current;
    if (recorder && recorder.state !== "inactive") recorder.stop();
    else stopRecorderResources();
  };

  const runUpload = async () => {
    if (!file || !mode || !title.trim() || (duration !== null && duration > maxAudioDurationSeconds)) return;
    setMessage("");
    try {
      let activeDigest = digest;
      let activeSession = session;
      if (!activeSession || activeSession.upload.expires_at <= Date.now() / 1000) {
        setState("checking"); activeDigest = await sha256(file);
        activeSession = await createUploadSession(file, title.trim(), activeDigest, mode);
        setDigest(activeDigest); setSession(activeSession);
      }
      setState("uploading");
      const transfer = putMedia(activeSession.upload, file, setProgress);
      cancelRef.current = transfer.cancel; await transfer.promise; cancelRef.current = null;
      setState("verifying");
      const result = await completeUpload(activeSession.recording.id, activeDigest);
      setCompleted(result.recording);
      setProgress(100); setState("success");
      navigate(`/recordings/${result.recording.id}`, {
        replace: true, state: { jobId: result.job.id },
      });
    } catch (error) {
      cancelRef.current = null;
      if (error instanceof DOMException && error.name === "AbortError") {
        setState("cancelled"); setMessage("上传已取消，文件仍保留在本页，可直接重试");
      } else {
        setState("error");
        setMessage(error instanceof ApiClientError || error instanceof Error ? error.message : "上传失败，请重试");
      }
    }
  };

  const isBusy = ["checking", "uploading", "verifying"].includes(state);
  const chooseMode = (next: RecordingSourceType) => {
    setMode(next); setFile(null); setMessage(""); resetUpload();
    if (next === "audio_upload") window.setTimeout(() => fileInputRef.current?.click());
    if (next === "recording_bean") window.setTimeout(() => beanInputRef.current?.click());
  };

  return <div className="upload-page capture-page">
    <CreationStepNav current={1} processing={isBusy} />
    <header className="upload-page-header"><span className="section-kicker">MOBILE CAPTURE</span><h1>今天想从哪里留下声音？</h1><p>三种入口最终都会安全转换成音频，进入同一套真实转写和播客创作流程。</p></header>
    <input ref={fileInputRef} hidden type="file" accept="audio/*,video/mp4,video/quicktime,video/webm,.mp3,.m4a,.wav,.aac,.mp4,.mov,.m4v,.webm" onChange={(event) => choose(event.target.files?.[0] ?? null)} />
    <input ref={beanInputRef} hidden type="file" accept="audio/*,.mp3,.m4a,.wav,.aac,.webm" onChange={(event) => choose(event.target.files?.[0] ?? null, "recording_bean")} />

    {!mode && <section className="capture-mode-grid" aria-label="选择声音来源">
      <button onClick={() => chooseMode("audio_upload")}><span><Upload size={25} /></span><strong>上传音频或视频</strong><small>视频会自动提取音轨<br />MP3、M4A、MP4、MOV 等</small></button>
      <button onClick={() => chooseMode("mobile_recording")}><span><Mic size={25} /></span><strong>手机直接录音</strong><small>无需切换应用<br />最长连续录制 15 分钟</small></button>
      <button onClick={() => chooseMode("recording_bean")}><span><Radio size={25} /></span><strong>从录音豆导入</strong><small>选择录音豆导出的文件<br />云端同步接口已预留</small></button>
    </section>}

    {mode && <div className="upload-layout capture-layout">
      <section className="upload-card">
        <button className="capture-back" disabled={isBusy || recorderState !== "idle"} onClick={() => { setMode(null); setFile(null); setMessage(""); }}><ChevronLeft size={16} />更换采集方式</button>
        <div className="capture-current"><span>{mode === "video_upload" ? <FileVideo size={19} /> : mode === "mobile_recording" ? <Mic size={19} /> : mode === "recording_bean" ? <Radio size={19} /> : <FileAudio size={19} />}</span><div><small>当前方式</small><strong>{sourceLabels[mode]}</strong></div></div>

        {mode === "mobile_recording" && !file && <div className={`mobile-recorder ${recorderState}`}>
          <div className="recording-pulse"><Mic size={30} /></div><strong>{recorderState === "idle" ? "准备好后，轻点开始" : recorderState === "paused" ? "录音已暂停" : "正在记录家人的声音"}</strong><time>{durationLabel(recordingSeconds)}</time>
          <div className="recorder-bars" aria-hidden="true">{[3,7,5,9,4,8,6,10,5,7,3,8].map((height, index) => <i key={index} style={{ height: `${height * 4}px` }} />)}</div>
          {recorderState === "idle" ? <button className="record-start" onClick={startRecording}><Mic size={19} />开始录音</button> : <div className="recorder-actions"><button onClick={togglePause}>{recorderState === "paused" ? <Play size={18} /> : <Pause size={18} />}{recorderState === "paused" ? "继续" : "暂停"}</button><button className="record-finish" onClick={() => finishRecording()}><Square size={16} fill="currentColor" />完成</button><button onClick={() => finishRecording(true)}><X size={18} />取消</button></div>}
        </div>}

        {!file && mode !== "mobile_recording" && <button className="upload-dropzone" onClick={() => (mode === "recording_bean" ? beanInputRef : fileInputRef).current?.click()}><span>{mode === "recording_bean" ? <Radio size={28} /> : <Upload size={28} />}</span><strong>{mode === "recording_bean" ? "选择录音豆文件" : "选择音频或视频"}</strong><small>{mode === "recording_bean" ? "MP3 / M4A / WAV / AAC / WebM" : "音频最大 100 MB · 视频最大 500 MB · 最长 15 分钟"}</small></button>}

        {file && <>
          <div className="selected-audio"><span>{mode === "video_upload" ? <FileVideo size={27} /> : <FileAudio size={27} />}</span><div><strong>{file.name}</strong><small>{(file.size / 1024 / 1024).toFixed(1)} MB · {durationLabel(duration)} · {sourceLabels[mode]}</small></div>{!isBusy && state !== "success" && mode !== "mobile_recording" && <button onClick={() => (mode === "recording_bean" ? beanInputRef : fileInputRef).current?.click()}>更换</button>}</div>
          {mode === "mobile_recording" && previewUrl && <audio className="recording-preview" controls src={previewUrl} />}
          {mode === "video_upload" && <p className="media-normalize-note"><FileAudio size={16} />上传完成后，系统会提取视频音轨，再进行转写。</p>}
          <label className="upload-title"><span>故事标题</span><input maxLength={120} value={title} onChange={(event) => setTitle(event.target.value)} disabled={isBusy || state === "success"} /></label>
          {isBusy && <div className="upload-progress" aria-live="polite"><div><span>{state === "checking" ? "正在计算文件摘要" : state === "verifying" ? "服务端正在验证媒体和音轨" : "正在安全上传"}</span><b>{state === "uploading" ? `${progress}%` : "···"}</b></div><div className="progress-track"><span style={{ width: `${state === "verifying" ? 100 : progress}%` }} /></div></div>}
          {message && <p className={`upload-message ${state === "error" ? "error" : ""}`}>{message}</p>}
          {state === "success" && completed ? <div className="upload-success"><Check size={22} /><div><strong>声音素材上传完成</strong><small>服务端确认 {durationLabel((completed.duration_ms ?? 0) / 1000)} · {completed.media_type}</small></div></div> : <div className="upload-actions">{state === "uploading" && <button className="secondary-button" onClick={() => cancelRef.current?.()}><X size={17} />取消</button>}<button className="primary-button" disabled={isBusy || !title.trim() || duration === null || duration > maxAudioDurationSeconds} onClick={runUpload}>{isBusy ? <LoaderCircle className="spin" size={18} /> : state === "error" || state === "cancelled" ? <RotateCcw size={18} /> : <Upload size={18} />}{state === "error" || state === "cancelled" ? "使用原文件重试" : "开始创作"}</button></div>}
          {state === "success" && <p className="upload-message">正在进入素材处理…</p>}
        </>}
        {!file && message && <p className="upload-message error">{message}</p>}
      </section>

      <aside className="upload-assurance"><ShieldCheck size={27} /><h2>一条统一创作链路</h2><ol><li><b>安全采集</b><span>记录来源、格式、大小和文件摘要</span></li><li><b>提取声音</b><span>视频自动提取音轨，所有来源统一成标准音频</span></li><li><b>进入创作</b><span>真实 ASR 转写后再确认人物、原话和播客素材</span></li></ol><small>录音豆 MVP 采用导出文件导入；设备云同步和蓝牙直连将在获得开放协议后接入。</small></aside>
    </div>}
  </div>;
}
