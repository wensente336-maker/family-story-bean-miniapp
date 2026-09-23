import { env } from "../config/env";
import { apiRequest } from "./apiClient";

export type FamilyMember = {
  id: string;
  nickname: string;
  character_profile: Record<string, unknown>;
  voice_consent: boolean;
  created_at: string;
  updated_at: string;
};

export type Family = {
  id: string;
  owner_user_id: string;
  name: string;
  members: FamilyMember[];
  created_at: string;
  updated_at: string;
};

export type AuthData = {
  access_token: string;
  token_type: "Bearer";
  expires_at: number;
  user_id: string;
  family: Family | null;
};

export type SessionData = {
  user_id: string;
  family: Family | null;
};

export function requestOtp(phone: string) {
  return apiRequest<{ expires_in: number; resend_after: number; delivery_hint: string | null }>(
    env.apiBaseUrl,
    "/v1/auth/otp/request",
    { method: "POST", body: JSON.stringify({ phone }) }
  );
}

export function verifyOtp(phone: string, code: string) {
  return apiRequest<AuthData>(env.apiBaseUrl, "/v1/auth/otp/verify", {
    method: "POST",
    body: JSON.stringify({ phone, code })
  });
}

export function getSession() {
  return apiRequest<SessionData>(env.apiBaseUrl, "/v1/session");
}

export function createFamily(name: string, ownerNickname: string) {
  return apiRequest<Family>(env.apiBaseUrl, "/v1/families", {
    method: "POST",
    body: JSON.stringify({ name, owner_nickname: ownerNickname })
  });
}

export function renameFamily(familyId: string, name: string) {
  return apiRequest<Family>(env.apiBaseUrl, `/v1/families/${familyId}`, {
    method: "PATCH",
    body: JSON.stringify({ name })
  });
}

export function addFamilyMember(familyId: string, nickname: string) {
  return apiRequest<FamilyMember>(env.apiBaseUrl, `/v1/families/${familyId}/members`, {
    method: "POST",
    body: JSON.stringify({ nickname })
  });
}

export function renameFamilyMember(familyId: string, memberId: string, nickname: string) {
  return apiRequest<FamilyMember>(env.apiBaseUrl, `/v1/families/${familyId}/members/${memberId}`, {
    method: "PATCH",
    body: JSON.stringify({ nickname })
  });
}

export function deleteFamilyMember(familyId: string, memberId: string) {
  return apiRequest<Family>(env.apiBaseUrl, `/v1/families/${familyId}/members/${memberId}`, {
    method: "DELETE"
  });
}
