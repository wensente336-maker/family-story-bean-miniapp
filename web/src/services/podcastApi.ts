import { env } from "../config/env";
import { apiRequest } from "./apiClient";

export type PodcastVersionStatus = "DRAFT" | "CONFIRMED" | "GENERATING" | "COMPLETED" | "FAILED";

export type PodcastMaterial = {
  id: string; sourceRecordingId: string; sourceSegmentId: string;
  familyMemberId: string | null; speakerKey: string; speakerLabel: string;
  role: "setup" | "highlight" | "response" | "ending"; position: number;
  startMs: number; endMs: number; originalText: string; confirmedText: string;
  shareAllowed: boolean;
};

export type PodcastPlanSegment = {
  segmentIndex?: number; kind: "narration" | "original"; label: string; text: string;
  sourceMaterialIds: string[];
};

export type PodcastPlan = {
  id: string; materialSetId: string; status: "DRAFT" | "CONFIRMED";
  revision: number; schemaVersion: string; title: string; description: string;
  narratorVoice: string; musicStyle: string; segments: PodcastPlanSegment[];
};

export type CoverAsset = {
  id: string; objectKey: string; mediaType: "image/jpeg" | "image/png" | "image/webp";
  width: number; height: number; sha256: string;
};

export type PodcastTag = { id: string; name: string; kind: "system" | "custom" };

export type PodcastVersion = {
  id: string; projectId: string; version: number; status: PodcastVersionStatus;
  materials: PodcastMaterial[]; plan: PodcastPlan | null; cover: CoverAsset | null;
  tags: PodcastTag[]; objectKey: string | null; failureCode: string | null;
  createdAt: string; updatedAt: string;
};

export type PodcastMaterialItem = {
  id: string; source_moment_id: string | null; source_recording_id: string;
  source_segment_id: string; family_member_id: string | null;
  speaker_key: string; speaker_label: string;
  role: "setup" | "highlight" | "response" | "ending"; position: number;
  start_ms: number; end_ms: number; original_text: string; confirmed_text: string;
  share_allowed: boolean;
};

export type PodcastMaterialWorkspace = {
  id: string; project_id: string; podcast_version_id: string;
  recording_id: string; recording_title: string; recording_duration_ms: number;
  status: "DRAFT" | "CONFIRMED"; revision: number; schema_version: string;
  transcript_revision: number; materials: PodcastMaterialItem[];
  family_members: Array<{ id: string; nickname: string }>;
  created_at: string; updated_at: string;
};

export type PodcastNarrativeStyle = "warm" | "humorous" | "growth" | "documentary";

export type PodcastPlanItem = {
  segment_index: number; kind: "narration" | "original"; label: string;
  text: string; source_material_ids: string[];
};

export type PodcastPlanDraft = {
  id: string; material_set_id: string; status: "DRAFT" | "CONFIRMED";
  revision: number; schema_version: string; title: string; description: string;
  narrator_voice: string; music_style: string; narration_style: PodcastNarrativeStyle;
  generator_provider: string; prompt_version: string; model_version: string;
  external_share_allowed: boolean; safety_checks: Record<string, boolean>;
  segments: PodcastPlanItem[];
};

export type PodcastPlanWorkspace = {
  recording_id: string; recording_title: string; podcast_version_id: string;
  material_set_id: string; material_revision: number;
  materials: PodcastMaterialItem[]; plan: PodcastPlanDraft;
};

export type PodcastNarrationPreview = {
  url: string; expires_at: number; provider: string; voice: string;
};

export type PodcastRenderJob = {
  id: string; podcast_version_id: string;
  status: "CREATED" | "GENERATING" | "COMPLETED" | "FAILED";
  progress: number; retry_count: number; error_code: string | null;
  error_detail: { message?: string }; created_at: string; updated_at: string;
};

export type PodcastRenderResult = {
  job: PodcastRenderJob; podcast_version_id: string; object_key: string | null;
  render_metadata: Record<string, unknown>;
};

export type PodcastRenderPlayback = {
  url: string; download_url: string; expires_at: number;
  render_metadata: Record<string, unknown>;
};

export type PodcastProductTag = { id: string; name: string; kind: "system" | "custom" };
export type PodcastProduct = {
  podcast_version_id: string; recording_id: string; version: number; status: "COMPLETED";
  title: string; description: string; duration_ms: number;
  render_mode: "narrated" | "original_only"; audio_asset_fingerprint: string;
  cover: null | { id: string; url: string; thumbnail_url: string; media_type: "image/webp"; width: number; height: number; sha256: string; aspect_ratio: "1:1" | "3:4"; layout_version: number; focal_x: number; focal_y: number };
  tags: PodcastProductTag[]; available_tags: PodcastProductTag[];
  chapters: Array<{ segment_index: number; kind: "narration" | "original"; label: string; start_ms: number; end_ms: number; source_segment_id: string | null }>;
  sources: Array<{ material_id: string; source_segment_id: string; speaker_label: string; start_ms: number; end_ms: number; confirmed_text: string }>;
  created_at: string; updated_at: string; deleted_at?: string | null;
  like_count: number; comment_count: number; liked_by_me: boolean;
  can_edit: boolean; can_comment: boolean;
};

export type PodcastReaction = { podcast_version_id: string; liked: boolean; like_count: number };
export type PodcastComment = { id: string; podcast_version_id: string; author_name: string; body: string; can_edit: boolean; can_delete: boolean; created_at: string; updated_at: string };
export type PodcastCommentPage = { items: PodcastComment[]; next_cursor: string | null };

export type PodcastShare = {
  id: string; podcast_version_id: string; recording_id: string; title: string;
  url: string; expires_at: string; revoked_at: string | null;
  access_count: number; created_at: string;
};

export type PublicPodcastShare = {
  title: string; description: string; tags: string[];
  cover_url: string | null; cover_download_url: string | null;
  media_url: string; expires_at: string; duration_ms: number;
  render_mode: "narrated" | "original_only";
};

export type UpdatePodcastMaterial = Pick<PodcastMaterialItem,
  "id" | "family_member_id" | "speaker_label" | "role" | "position" |
  "start_ms" | "end_ms" | "confirmed_text" | "share_allowed"
>;

export type PodcastMoment = {
  id: string; title: string; theme: string | null; position: number;
  start_ms: number; end_ms: number;
};

export type PodcastSegment = {
  id: string; segment_index: number; kind: "narration" | "original";
  label: string; text: string; source_moment_id: string | null;
  source_segment_id: string | null; start_ms: number | null; end_ms: number | null;
};

export type Podcast = {
  id: string; recording_id: string; title: string; status: string; version: number;
  pipeline_version: string;
  metadata: {
    intro?: string; outro?: string; duration_ms?: number;
    render_mode?: "narrated" | "original_only" | "failed";
    tts_provider?: string | null; voice_clone?: boolean;
    tts_voice?: string | null; tts_quality?: "neural-natural" | "system-basic" | null;
    tts_fallback_used?: boolean; narration_segments?: number;
    music_source?: string; original_audio_traceable?: boolean;
  };
  moments: PodcastMoment[]; segments: PodcastSegment[];
  created_at: string; updated_at: string;
};

export type PodcastPlayback = { url: string; download_url: string; expires_at: number };

export function createPodcast(momentIds: string[]): Promise<Podcast> {
  return apiRequest(env.apiBaseUrl, "/v1/podcasts", {
    method: "POST", body: JSON.stringify({ moment_ids: momentIds })
  });
}

export function getPodcast(podcastId: string): Promise<Podcast> {
  return apiRequest(env.apiBaseUrl, `/v1/podcasts/${podcastId}`);
}

export function remixPodcast(
  podcastId: string, body: { moment_ids: string[]; intro: string; outro: string }
): Promise<Podcast> {
  return apiRequest(env.apiBaseUrl, `/v1/podcasts/${podcastId}`, {
    method: "PATCH", body: JSON.stringify(body)
  });
}

export function getPodcastPlayback(podcastId: string): Promise<PodcastPlayback> {
  return apiRequest(env.apiBaseUrl, `/v1/podcasts/${podcastId}/playback-url`, { method: "POST" });
}

export function getPodcastMaterialSet(recordingId: string): Promise<PodcastMaterialWorkspace> {
  return apiRequest(env.apiBaseUrl, `/v1/recordings/${recordingId}/podcast-material-set`);
}

export function createPodcastMaterialDraft(recordingId: string): Promise<PodcastMaterialWorkspace> {
  return apiRequest(env.apiBaseUrl, `/v1/recordings/${recordingId}/podcast-material-set/draft`, {
    method: "POST"
  });
}

export function updatePodcastMaterialSet(
  recordingId: string,
  status: "DRAFT" | "CONFIRMED",
  materials: UpdatePodcastMaterial[]
): Promise<PodcastMaterialWorkspace> {
  return apiRequest(env.apiBaseUrl, `/v1/recordings/${recordingId}/podcast-material-set`, {
    method: "PUT", body: JSON.stringify({ status, materials })
  });
}

export function getPodcastPlan(recordingId: string): Promise<PodcastPlanWorkspace> {
  return apiRequest(env.apiBaseUrl, `/v1/recordings/${recordingId}/podcast-plan`);
}

export function createPodcastPlanDraft(
  recordingId: string,
  narrationStyle: PodcastNarrativeStyle
): Promise<PodcastPlanWorkspace> {
  return apiRequest(env.apiBaseUrl, `/v1/recordings/${recordingId}/podcast-plan/draft`, {
    method: "POST", body: JSON.stringify({ narration_style: narrationStyle })
  });
}

export function updatePodcastPlan(
  recordingId: string,
  status: "DRAFT" | "CONFIRMED",
  plan: PodcastPlanDraft
): Promise<PodcastPlanWorkspace> {
  return apiRequest(env.apiBaseUrl, `/v1/recordings/${recordingId}/podcast-plan`, {
    method: "PUT",
    body: JSON.stringify({
      status, title: plan.title, description: plan.description,
      narrator_voice: plan.narrator_voice, music_style: plan.music_style,
      segments: plan.segments,
    })
  });
}

export function createNarrationPreview(
  recordingId: string,
  segmentIndex: number
): Promise<PodcastNarrationPreview> {
  return apiRequest(env.apiBaseUrl, `/v1/recordings/${recordingId}/podcast-plan/narration-preview`, {
    method: "POST", body: JSON.stringify({ segment_index: segmentIndex })
  });
}

export function createPodcastRenderJob(recordingId: string): Promise<PodcastRenderResult> {
  return apiRequest(env.apiBaseUrl, `/v1/recordings/${recordingId}/podcast-render-jobs`, {
    method: "POST"
  });
}

export function getPodcastRenderJob(jobId: string): Promise<PodcastRenderResult> {
  return apiRequest(env.apiBaseUrl, `/v1/podcast-render-jobs/${jobId}`);
}

export function getRecordingPodcastRenderJob(recordingId: string): Promise<PodcastRenderResult> {
  return apiRequest(env.apiBaseUrl, `/v1/recordings/${recordingId}/podcast-render-job`);
}

export function retryPodcastRenderJob(jobId: string): Promise<PodcastRenderResult> {
  return apiRequest(env.apiBaseUrl, `/v1/podcast-render-jobs/${jobId}/retry`, { method: "POST" });
}

export function getPodcastRenderPlayback(jobId: string): Promise<PodcastRenderPlayback> {
  return apiRequest(env.apiBaseUrl, `/v1/podcast-render-jobs/${jobId}/playback-url`, {
    method: "POST"
  });
}

export function getPodcastProduct(recordingId: string): Promise<PodcastProduct> {
  return apiRequest(env.apiBaseUrl, `/v1/recordings/${recordingId}/podcast-product`);
}

export function updatePodcastProduct(
  recordingId: string, body: { title: string; description: string; tags: string[] }
): Promise<PodcastProduct> {
  return apiRequest(env.apiBaseUrl, `/v1/recordings/${recordingId}/podcast-product`, {
    method: "PATCH", body: JSON.stringify(body)
  });
}

export function uploadPodcastCover(
  recordingId: string, file: File, focalX: number, focalY: number
): Promise<PodcastProduct> {
  return apiRequest(
    env.apiBaseUrl,
    `/v1/recordings/${recordingId}/podcast-product/cover?focal_x=${focalX}&focal_y=${focalY}`,
    { method: "POST", body: file, headers: { "Content-Type": file.type } }
  );
}

export function deletePodcastCover(recordingId: string): Promise<{ deleted: boolean }> {
  return apiRequest(env.apiBaseUrl, `/v1/recordings/${recordingId}/podcast-product/cover`, {
    method: "DELETE"
  });
}

export function listPodcastProducts(tag?: string): Promise<PodcastProduct[]> {
  return apiRequest(env.apiBaseUrl, `/v1/podcast-products${tag ? `?tag=${encodeURIComponent(tag)}` : ""}`);
}

export function listPodcastTrash(): Promise<PodcastProduct[]> {
  return apiRequest(env.apiBaseUrl, "/v1/podcast-products/trash");
}

export function trashPodcastProduct(recordingId: string): Promise<{ recording_id: string; deleted_at: string }> {
  return apiRequest(env.apiBaseUrl, `/v1/recordings/${recordingId}/podcast-product`, {
    method: "DELETE", body: JSON.stringify({ confirmed: true })
  });
}

export function restorePodcastProduct(recordingId: string): Promise<{ recording_id: string; deleted_at: null }> {
  return apiRequest(env.apiBaseUrl, `/v1/recordings/${recordingId}/podcast-product/restore`, { method: "POST" });
}

export function likePodcastProduct(versionId: string): Promise<PodcastReaction> {
  return apiRequest(env.apiBaseUrl, `/v1/podcast-products/${versionId}/like`, { method: "POST" });
}

export function unlikePodcastProduct(versionId: string): Promise<PodcastReaction> {
  return apiRequest(env.apiBaseUrl, `/v1/podcast-products/${versionId}/like`, { method: "DELETE" });
}

export function listPodcastComments(versionId: string, cursor?: string): Promise<PodcastCommentPage> {
  return apiRequest(env.apiBaseUrl, `/v1/podcast-products/${versionId}/comments${cursor ? `?cursor=${cursor}` : ""}`);
}

export function createPodcastComment(versionId: string, body: string): Promise<PodcastComment> {
  return apiRequest(env.apiBaseUrl, `/v1/podcast-products/${versionId}/comments`, { method: "POST", body: JSON.stringify({ body }) });
}

export function updatePodcastComment(commentId: string, body: string): Promise<PodcastComment> {
  return apiRequest(env.apiBaseUrl, `/v1/podcast-comments/${commentId}`, { method: "PATCH", body: JSON.stringify({ body }) });
}

export function deletePodcastComment(commentId: string): Promise<{ id: string; deleted: boolean }> {
  return apiRequest(env.apiBaseUrl, `/v1/podcast-comments/${commentId}`, { method: "DELETE" });
}

export function createPodcastShare(recordingId: string, expiresInHours = 24): Promise<PodcastShare> {
  return apiRequest(env.apiBaseUrl, `/v1/recordings/${recordingId}/podcast-shares`, {
    method: "POST", body: JSON.stringify({ expires_in_hours: expiresInHours })
  });
}

export function listPodcastShares(recordingId?: string): Promise<PodcastShare[]> {
  return apiRequest(
    env.apiBaseUrl,
    `/v1/podcast-shares${recordingId ? `?recording_id=${encodeURIComponent(recordingId)}` : ""}`
  );
}

export function revokePodcastShare(shareId: string): Promise<PodcastShare> {
  return apiRequest(env.apiBaseUrl, `/v1/podcast-shares/${shareId}`, { method: "DELETE" });
}

export function getPublicPodcastShare(token: string): Promise<PublicPodcastShare> {
  return apiRequest(env.apiBaseUrl, `/v1/public/podcast-shares/${encodeURIComponent(token)}`);
}
