import { afterEach, describe, expect, it, vi } from "vitest";
import {
  createShare, getPublicShare, listTimeline, revokeShare, updatePrivacySettings,
} from "./lifecycleApi";

afterEach(() => vi.unstubAllGlobals());

function successfulFetch() {
  return vi.fn().mockImplementation(async () => new Response(JSON.stringify({
      ok: true,
      data: { items: [], total: 0 },
      meta: { request_id: "lifecycle-request", timestamp: "2026-09-20T00:00:00Z" },
    }), { status: 200, headers: { "Content-Type": "application/json" } }));
}

describe("timeline and privacy API", () => {
  it("serializes all timeline filters", async () => {
    const fetchMock = successfulFetch();
    vi.stubGlobal("fetch", fetchMock);

    await listTimeline({
      content_type: "podcast", member_id: "member-1",
      date_from: "2026-09-01", date_to: "2026-09-20",
    });

    const url = String(fetchMock.mock.calls[0][0]);
    expect(url).toContain("/v1/timeline?");
    expect(url).toContain("content_type=podcast");
    expect(url).toContain("member_id=member-1");
    expect(decodeURIComponent(url)).toContain("date_from=2026-09-01T00:00:00+08:00");
    expect(decodeURIComponent(url)).toContain("date_to=2026-09-20T23:59:59+08:00");
  });

  it("uses explicit methods for share and privacy mutations", async () => {
    const fetchMock = successfulFetch();
    vi.stubGlobal("fetch", fetchMock);

    await createShare("creation-1", 6);
    await revokeShare("share-1");
    await updatePrivacySettings({
      recording_retention_days: 7, share_default_hours: 6, sharing_enabled: true,
    });

    const requests = fetchMock.mock.calls.map(([url, options]) => ({
      url: String(url), method: (options as RequestInit).method,
      body: (options as RequestInit).body,
    }));
    expect(requests[0]).toMatchObject({ method: "POST", body: JSON.stringify({ expires_in_hours: 6 }) });
    expect(requests[1]).toMatchObject({ method: "DELETE" });
    expect(requests[2]).toMatchObject({ method: "PUT" });
  });

  it("reads a public share through the unauthenticated route", async () => {
    const fetchMock = successfulFetch();
    vi.stubGlobal("fetch", fetchMock);
    await getPublicShare("opaque-token");
    expect(String(fetchMock.mock.calls[0][0])).toMatch(/\/v1\/public\/shares\/opaque-token$/);
  });
});
