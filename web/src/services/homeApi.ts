import { env } from "../config/env";
import type { HomeData } from "../types";
import { apiRequest } from "./apiClient";
import { getHomeData as getMockHomeData } from "./mockApi";

type ApiHomeData = {
  family: {
    id: string;
    name: string;
    member_labels: string[];
  };
  processing: {
    recording_id: string;
    job_id: string;
    title: string;
    detail: string;
    stage: string;
    progress: number;
  } | null;
  moments: Array<{
    id: string;
    recording_id: string;
    theme: string;
    duration_ms: number;
    title: string;
    quote: string;
    color: "sun" | "coral" | "mint";
  }>;
};

export function formatDuration(durationMs: number): string {
  const totalSeconds = Math.floor(durationMs / 1000);
  return `${String(Math.floor(totalSeconds / 60)).padStart(2, "0")}:${String(totalSeconds % 60).padStart(2, "0")}`;
}

export function normalizeHomeData(data: ApiHomeData): HomeData {
  return {
    family: { name: data.family.name, members: data.family.member_labels },
    processing: data.processing
      ? {
          recordingId: data.processing.recording_id,
          jobId: data.processing.job_id,
          title: data.processing.title,
          detail: data.processing.detail,
          progress: data.processing.progress,
          stage: data.processing.stage
        }
      : { title: "暂无处理任务", detail: "上传一段录音开始记录", progress: 0, stage: "EMPTY" },
    moments: data.moments.map((moment) => ({
      id: moment.id,
      recordingId: moment.recording_id,
      theme: moment.theme,
      duration: formatDuration(moment.duration_ms),
      title: moment.title,
      quote: moment.quote,
      tone: moment.color === "coral" ? "coral" : "honey"
    }))
  };
}

export async function getHomeData(): Promise<HomeData> {
  if (env.dataSource === "mock") return getMockHomeData();
  return normalizeHomeData(await apiRequest<ApiHomeData>(env.apiBaseUrl, "/v1/home"));
}
