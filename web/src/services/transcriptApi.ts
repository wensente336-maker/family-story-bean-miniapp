import { env } from "../config/env";
import { apiRequest } from "./apiClient";

export type TranscriptWord = {
  text: string;
  start_ms: number;
  end_ms: number;
  confidence: number | null;
};

export type TranscriptSegment = {
  id: string;
  recording_id: string;
  family_member_id: string | null;
  speaker_key: string;
  start_ms: number;
  end_ms: number;
  text: string;
  original_text: string;
  confidence: number | null;
  words: TranscriptWord[];
  edited_by_user: boolean;
  pipeline_version: string;
  created_at: string;
  updated_at: string;
};

export type SpeakerMapping = {
  speaker_key: string;
  family_member_id: string | null;
  display_name: string;
};

export type Transcript = {
  recording_id: string;
  title: string;
  duration_ms: number;
  language: string | null;
  asr_provider: string | null;
  asr_model: string | null;
  revision: number;
  low_confidence_threshold: number;
  speakers: SpeakerMapping[];
  family_members: Array<{ id: string; nickname: string }>;
  segments: TranscriptSegment[];
};

export function getTranscript(recordingId: string): Promise<Transcript> {
  return apiRequest(env.apiBaseUrl, `/v1/recordings/${recordingId}/transcript`);
}

export function updateTranscriptSegment(
  recordingId: string,
  segmentId: string,
  changes: { text?: string; speaker_key?: string }
): Promise<TranscriptSegment> {
  return apiRequest(env.apiBaseUrl, `/v1/recordings/${recordingId}/transcript/segments/${segmentId}`, {
    method: "PATCH",
    body: JSON.stringify(changes)
  });
}

export function updateSpeakerMapping(
  recordingId: string,
  speakerKey: string,
  familyMemberId: string | null,
  displayName: string
): Promise<SpeakerMapping> {
  return apiRequest(env.apiBaseUrl, `/v1/recordings/${recordingId}/speakers/${speakerKey}`, {
    method: "PUT",
    body: JSON.stringify({ family_member_id: familyMemberId, display_name: displayName })
  });
}

export async function getPlaybackUrl(recordingId: string): Promise<string> {
  const result = await apiRequest<{ url: string; expires_at: number }>(
    env.apiBaseUrl,
    `/v1/recordings/${recordingId}/playback-url`,
    { method: "POST" }
  );
  return result.url;
}
