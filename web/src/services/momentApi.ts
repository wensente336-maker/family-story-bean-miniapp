import { env } from "../config/env";
import { apiRequest } from "./apiClient";

export type SourceSegment = {
  transcript_segment_id: string;
  start_ms: number;
  end_ms: number;
  quote: string | null;
};

export type Storyboard = {
  schema_version: "1.0";
  pipeline_version: string;
  title: string;
  scene: string;
  story_type: string;
  characters: Array<{ family_member_id: string | null; speaker_key: string; display_name: string }>;
  setup: string;
  turning_point: string;
  ending: string;
  highlight_quote: string | null;
  emotion_curve: string[];
  source_segments: SourceSegment[];
  sensitive_flags: string[];
  confidence: number;
};

export type Moment = {
  id: string;
  recording_id: string;
  title: string;
  theme: string | null;
  score: number;
  rank: number;
  start_ms: number;
  end_ms: number;
  selection_state: "candidate" | "kept" | "dismissed";
  score_breakdown: Record<string, number>;
  storyboard: Storyboard;
  transcript_revision: number;
  edited_by_user: boolean;
  pipeline_version: string;
  created_at: string;
  updated_at: string;
};

export async function listMoments(recordingId: string): Promise<Moment[]> {
  const result = await apiRequest<{ recording_id: string; moments: Moment[] }>(
    env.apiBaseUrl, `/v1/recordings/${recordingId}/moments`
  );
  return result.moments;
}

export async function rebuildMoments(recordingId: string): Promise<Moment[]> {
  const result = await apiRequest<{ recording_id: string; moments: Moment[] }>(
    env.apiBaseUrl, `/v1/recordings/${recordingId}/moments/rebuild`, { method: "POST" }
  );
  return result.moments;
}

export function getMoment(momentId: string): Promise<Moment> {
  return apiRequest(env.apiBaseUrl, `/v1/moments/${momentId}`);
}

export function updateMoment(
  momentId: string,
  changes: { selection_state?: Moment["selection_state"]; start_ms?: number; end_ms?: number }
): Promise<Moment> {
  return apiRequest(env.apiBaseUrl, `/v1/moments/${momentId}`, {
    method: "PATCH",
    body: JSON.stringify(changes)
  });
}
