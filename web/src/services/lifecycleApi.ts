import { env } from "../config/env";
import { apiRequest } from "./apiClient";

export type TimelineKind = "recording" | "moment" | "comic" | "podcast";

export type TimelineItem = {
  id: string; kind: TimelineKind; title: string; subtitle: string; status: string;
  created_at: string; recording_id: string | null; target_path: string; member_ids: string[];
};

export type PrivacySettings = {
  family_id: string; recording_retention_days: number; share_default_hours: number;
  sharing_enabled: boolean; updated_at: string;
};

export type Share = {
  id: string; creation_id: string; creation_type: "COMIC" | "PODCAST"; title: string;
  url: string; expires_at: string; revoked_at: string | null; access_count: number; created_at: string;
};

export type PublicShare = {
  creation_id: string; creation_type: "COMIC" | "PODCAST"; title: string;
  expires_at: string; media_url: string | null;
  panels: Array<{
    panel_index: number; narration: string; dialogue: string | null; asset_url: string;
    asset_variant: string; crop_x: number; crop_y: number;
  }>;
};

export type FamilyMetrics = {
  recordings_total: number; upload_success_rate: number | null;
  analysis_success_rate: number | null; generation_success_rate: number | null;
  processing_p95_seconds: number | null; deletion_success_rate: number | null;
  active_shares: number;
};

export function listTimeline(filters: {
  content_type?: TimelineKind | ""; member_id?: string; date_from?: string; date_to?: string;
} = {}): Promise<{ items: TimelineItem[]; total: number }> {
  const query = new URLSearchParams();
  if (filters.content_type) query.set("content_type", filters.content_type);
  if (filters.member_id) query.set("member_id", filters.member_id);
  if (filters.date_from) query.set("date_from", `${filters.date_from}T00:00:00+08:00`);
  if (filters.date_to) query.set("date_to", `${filters.date_to}T23:59:59+08:00`);
  return apiRequest(env.apiBaseUrl, `/v1/timeline${query.size ? `?${query}` : ""}`);
}

export function getPrivacySettings(): Promise<PrivacySettings> {
  return apiRequest(env.apiBaseUrl, "/v1/privacy");
}

export function updatePrivacySettings(body: Omit<PrivacySettings, "family_id" | "updated_at">): Promise<PrivacySettings> {
  return apiRequest(env.apiBaseUrl, "/v1/privacy", { method: "PUT", body: JSON.stringify(body) });
}

export function createShare(creationId: string, expiresInHours: number): Promise<Share> {
  return apiRequest(env.apiBaseUrl, `/v1/creations/${creationId}/shares`, {
    method: "POST", body: JSON.stringify({ expires_in_hours: expiresInHours })
  });
}

export function listShares(): Promise<Share[]> {
  return apiRequest(env.apiBaseUrl, "/v1/shares");
}

export function revokeShare(shareId: string): Promise<Share> {
  return apiRequest(env.apiBaseUrl, `/v1/shares/${shareId}`, { method: "DELETE" });
}

export function getPublicShare(token: string): Promise<PublicShare> {
  return apiRequest(env.apiBaseUrl, `/v1/public/shares/${token}`);
}

export function deleteFamilySpace(familyId: string) {
  return apiRequest(env.apiBaseUrl, `/v1/privacy/families/${familyId}`, { method: "DELETE" });
}

export function deleteCreation(creationId: string) {
  return apiRequest(env.apiBaseUrl, `/v1/privacy/creations/${creationId}`, { method: "DELETE" });
}

export function deleteRecording(recordingId: string) {
  return apiRequest(env.apiBaseUrl, `/v1/privacy/recordings/${recordingId}`, { method: "DELETE" });
}

export function getFamilyMetrics(): Promise<FamilyMetrics> {
  return apiRequest(env.apiBaseUrl, "/v1/ops/family-metrics");
}
