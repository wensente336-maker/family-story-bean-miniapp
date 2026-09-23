import { env } from "../config/env";
import { apiRequest } from "./apiClient";

export type HighlightWork = {
  id: string; source_moment_id: string | null; recording_id: string;
  title: string; quote: string; share_allowed: boolean; start_ms: number; end_ms: number; duration_ms: number;
  audio_status: "PENDING" | "READY" | "UNAVAILABLE" | "FAILED";
  audio_url: string | null; member_ids: string[]; deleted_at: string | null;
  like_count: number; comment_count: number; liked_by_me: boolean; can_edit: boolean; can_comment: boolean;
  cover: null | { id: string; url: string; thumbnail_url: string; width: number; height: number; sha256: string; aspect_ratio: "1:1"|"3:4"; layout_version: number; focal_x: number; focal_y: number };
  created_at: string; updated_at: string;
};

export type HighlightShare = {
  id: string; highlight_work_id: string; title: string; url: string;
  expires_at: string; revoked_at: string | null; access_count: number; created_at: string;
};

export type PublicHighlight = {
  title: string; quote: string; duration_ms: number; audio_url: string;
  cover_url: string | null; expires_at: string;
};

export type HighlightComment = {
  id: string; highlight_work_id: string; author_name: string; body: string;
  can_edit: boolean; can_delete: boolean; created_at: string; updated_at: string;
};

export type HighlightCommentPage = { items: HighlightComment[]; next_cursor: string | null };

export const listHighlightWorks = (): Promise<HighlightWork[]> => apiRequest(env.apiBaseUrl, "/v1/highlight-works");
export const listHighlightTrash = (): Promise<HighlightWork[]> => apiRequest(env.apiBaseUrl, "/v1/highlight-works/trash");
export const getHighlightWork = (id: string): Promise<HighlightWork> => apiRequest(env.apiBaseUrl, `/v1/highlight-works/${id}`);
export const saveMomentAsHighlight = (momentId: string): Promise<HighlightWork> => apiRequest(env.apiBaseUrl, `/v1/moments/${momentId}/highlight-work`, { method: "POST" });
export const updateHighlightWork = (id: string, body: { title: string; quote: string }): Promise<HighlightWork> => apiRequest(env.apiBaseUrl, `/v1/highlight-works/${id}`, { method: "PATCH", body: JSON.stringify(body) });
export const uploadHighlightCover = (id: string, file: File, x = .5, y = .5): Promise<HighlightWork> => apiRequest(env.apiBaseUrl, `/v1/highlight-works/${id}/cover?focal_x=${x}&focal_y=${y}`, { method: "POST", body: file, headers: { "Content-Type": file.type } });
export const deleteHighlightCover = (id: string): Promise<{ deleted: boolean }> => apiRequest(env.apiBaseUrl, `/v1/highlight-works/${id}/cover`, { method: "DELETE" });
export const trashHighlightWork = (id: string): Promise<{ id: string; deleted_at: string }> => apiRequest(env.apiBaseUrl, `/v1/highlight-works/${id}`, { method: "DELETE" });
export const restoreHighlightWork = (id: string): Promise<{ id: string; deleted_at: null }> => apiRequest(env.apiBaseUrl, `/v1/highlight-works/${id}/restore`, { method: "POST" });
export const createHighlightShare = (id: string, hours: number): Promise<HighlightShare> => apiRequest(env.apiBaseUrl, `/v1/highlight-works/${id}/shares`, { method: "POST", body: JSON.stringify({ expires_in_hours: hours }) });
export const listHighlightShares = (id: string): Promise<HighlightShare[]> => apiRequest(env.apiBaseUrl, `/v1/highlight-works/${id}/shares`);
export const revokeHighlightShare = (id: string): Promise<HighlightShare> => apiRequest(env.apiBaseUrl, `/v1/highlight-shares/${id}`, { method: "DELETE" });
export const getPublicHighlight = (token: string): Promise<PublicHighlight> => apiRequest(env.apiBaseUrl, `/v1/public/highlight-shares/${encodeURIComponent(token)}`);
export const likeHighlight = (id: string): Promise<{highlight_work_id:string;liked:boolean;like_count:number}> => apiRequest(env.apiBaseUrl, `/v1/highlight-works/${id}/like`, {method:"POST"});
export const unlikeHighlight = (id: string): Promise<{highlight_work_id:string;liked:boolean;like_count:number}> => apiRequest(env.apiBaseUrl, `/v1/highlight-works/${id}/like`, {method:"DELETE"});
export const listHighlightComments = (id:string,cursor?:string):Promise<HighlightCommentPage> => apiRequest(env.apiBaseUrl, `/v1/highlight-works/${id}/comments${cursor?`?cursor=${encodeURIComponent(cursor)}`:""}`);
export const createHighlightComment = (id:string,body:string):Promise<HighlightComment> => apiRequest(env.apiBaseUrl, `/v1/highlight-works/${id}/comments`, {method:"POST",body:JSON.stringify({body})});
export const updateHighlightComment = (id:string,body:string):Promise<HighlightComment> => apiRequest(env.apiBaseUrl, `/v1/highlight-comments/${id}`, {method:"PATCH",body:JSON.stringify({body})});
export const deleteHighlightComment = (id:string):Promise<{id:string;deleted:boolean}> => apiRequest(env.apiBaseUrl, `/v1/highlight-comments/${id}`, {method:"DELETE"});
