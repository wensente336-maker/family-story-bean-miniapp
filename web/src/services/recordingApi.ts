import { env } from "../config/env";
import { apiRequest } from "./apiClient";

export type Recording = {
  id: string;
  family_id: string;
  title: string;
  original_file_name: string;
  media_type: string | null;
  file_size: number | null;
  duration_ms: number | null;
  sha256: string | null;
  source_type: RecordingSourceType;
  status: "CREATED" | "UPLOADING" | "UPLOADED" | "PREPROCESSING" | "TRANSCRIBING" | "ANALYZING" | "READY_FOR_SELECTION" | "FAILED";
  error_code: string | null;
  delete_at: string | null;
  created_at: string;
  updated_at: string;
};

type UploadTarget = {
  method: "PUT";
  url: string;
  expires_at: number;
  headers: Record<string, string>;
};

export type UploadSession = { recording: Recording; upload: UploadTarget };

export type RecordingSourceType = "audio_upload" | "video_upload" | "mobile_recording" | "recording_bean";

export const supportedAudioExtensions = ["mp3", "m4a", "wav", "aac", "webm"];
export const supportedVideoExtensions = ["mp4", "mov", "m4v", "webm"];
export const supportedExtensions = supportedAudioExtensions;
export const maxAudioBytes = 100 * 1024 * 1024;
export const maxVideoBytes = 500 * 1024 * 1024;
export const maxAudioDurationSeconds = 15 * 60;

export function inferSourceType(file: File, preferred?: RecordingSourceType): RecordingSourceType {
  if (preferred === "mobile_recording" || preferred === "recording_bean") return preferred;
  const extension = file.name.split(".").pop()?.toLowerCase() ?? "";
  return file.type.startsWith("video/") || ["mp4", "mov", "m4v"].includes(extension)
    ? "video_upload" : "audio_upload";
}

export function validateMediaSelection(file: File, preferred?: RecordingSourceType): string | null {
  const extension = file.name.split(".").pop()?.toLowerCase() ?? "";
  const sourceType = inferSourceType(file, preferred);
  const allowed = sourceType === "video_upload" ? supportedVideoExtensions : supportedAudioExtensions;
  if (!allowed.includes(extension)) return sourceType === "video_upload"
    ? "请选择 MP4、MOV、M4V 或 WebM 视频"
    : "请选择 MP3、M4A、WAV、AAC 或 WebM 音频";
  if (file.size === 0) return "媒体文件为空";
  if (sourceType === "video_upload" && file.size > maxVideoBytes) return "视频文件不能超过 500 MB";
  if (sourceType !== "video_upload" && file.size > maxAudioBytes) return "音频文件不能超过 100 MB";
  return null;
}

export const validateAudioSelection = (file: File) => validateMediaSelection(file, "audio_upload");

export async function readMediaDuration(file: File): Promise<number> {
  return new Promise((resolve, reject) => {
    const media = document.createElement(inferSourceType(file) === "video_upload" ? "video" : "audio");
    const url = URL.createObjectURL(file);
    const cleanup = () => {
      URL.revokeObjectURL(url);
      media.removeAttribute("src");
    };
    const timer = window.setTimeout(() => {
      cleanup();
      reject(new Error("读取音频超时"));
    }, 10000);
    media.preload = "metadata";
    media.onloadedmetadata = () => {
      window.clearTimeout(timer);
      const duration = media.duration;
      cleanup();
      if (!Number.isFinite(duration) || duration <= 0) reject(new Error("无法读取音频时长"));
      else resolve(duration);
    };
    media.onerror = () => {
      window.clearTimeout(timer);
      cleanup();
      reject(new Error("媒体文件无法解析、已经损坏或视频不含音轨"));
    };
    media.src = url;
  });
}

export const readAudioDuration = readMediaDuration;

export async function sha256(file: File): Promise<string> {
  const digest = await crypto.subtle.digest("SHA-256", await file.arrayBuffer());
  return Array.from(new Uint8Array(digest), (byte) => byte.toString(16).padStart(2, "0")).join("");
}

export async function createUploadSession(
  file: File, title: string, digest: string, preferredSourceType?: RecordingSourceType
): Promise<UploadSession> {
  return apiRequest<UploadSession>(env.apiBaseUrl, "/v1/recordings", {
    method: "POST",
    body: JSON.stringify({
      title,
      original_file_name: file.name,
      declared_media_type: file.type || null,
      declared_size: file.size,
      sha256: digest,
      source_type: inferSourceType(file, preferredSourceType)
    })
  });
}

export function putAudio(
  target: UploadTarget,
  file: File,
  onProgress: (percent: number) => void
): { promise: Promise<void>; cancel: () => void } {
  const request = new XMLHttpRequest();
  const promise = new Promise<void>((resolve, reject) => {
    request.open(target.method, target.url);
    Object.entries(target.headers).forEach(([name, value]) => request.setRequestHeader(name, value));
    request.upload.onprogress = (event) => {
      if (event.lengthComputable) onProgress(Math.round(event.loaded / event.total * 100));
    };
    request.onload = () => {
      if (request.status >= 200 && request.status < 300) resolve();
      else reject(new Error(`上传失败（${request.status}）`));
    };
    request.onerror = () => reject(new Error("网络中断，录音尚未上传完成"));
    request.onabort = () => reject(new DOMException("上传已取消", "AbortError"));
    request.send(file);
  });
  return { promise, cancel: () => request.abort() };
}

export const putMedia = putAudio;

export type Job = {
  id: string;
  recording_id: string;
  stage: "CREATED" | "PREPROCESSING" | "TRANSCRIBING" | "ANALYZING" | "READY_FOR_SELECTION" | "FAILED";
  progress: number;
  retry_count: number;
  pipeline_version: string;
  error_code: string | null;
  error_detail: Record<string, unknown>;
  heartbeat_at: string | null;
  started_at: string | null;
  completed_at: string | null;
  dead_lettered_at: string | null;
};

export type CompleteUploadResult = { recording: Recording; job: Job };

export function completeUpload(recordingId: string, digest: string): Promise<CompleteUploadResult> {
  return apiRequest<CompleteUploadResult>(env.apiBaseUrl, `/v1/recordings/${recordingId}/upload-complete`, {
    method: "POST",
    body: JSON.stringify({ sha256: digest })
  });
}

export function listRecordings(): Promise<Recording[]> {
  return apiRequest<Recording[]>(env.apiBaseUrl, "/v1/recordings");
}

export function getRecording(recordingId: string): Promise<Recording> {
  return apiRequest<Recording>(env.apiBaseUrl, `/v1/recordings/${recordingId}`);
}

export function getRecordingJob(recordingId: string): Promise<Job> {
  return apiRequest<Job>(env.apiBaseUrl, `/v1/recordings/${recordingId}/job`);
}

export function retryJob(jobId: string): Promise<Job> {
  return apiRequest<Job>(env.apiBaseUrl, `/v1/jobs/${jobId}/retry`, { method: "POST" });
}

export function deleteRecordingDraft(recordingId: string): Promise<{ id: string; deleted: true }> {
  return apiRequest(env.apiBaseUrl, `/v1/recordings/${recordingId}`, { method: "DELETE" });
}
