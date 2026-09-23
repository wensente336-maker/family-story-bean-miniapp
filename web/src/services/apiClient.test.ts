import { afterEach, describe, expect, it, vi } from "vitest";
import { ApiClientError, apiRequest } from "./apiClient";
import { saveAccessToken } from "./authStore";

afterEach(() => vi.unstubAllGlobals());

describe("API client", () => {
  it("returns data and attaches a request id", async () => {
    const fetchMock = vi.fn().mockResolvedValue(new Response(JSON.stringify({
      ok: true,
      data: { family: "小满一家" },
      meta: { request_id: "server-request", timestamp: "2026-09-19T00:00:00Z" }
    }), { status: 200, headers: { "Content-Type": "application/json" } }));
    vi.stubGlobal("fetch", fetchMock);

    await expect(apiRequest<{ family: string }>("http://api.local", "/v1/home"))
      .resolves.toEqual({ family: "小满一家" });

    const requestOptions = fetchMock.mock.calls[0][1] as RequestInit;
    expect(new Headers(requestOptions.headers).get("X-Request-Id")).toBeTruthy();
  });

  it("preserves the standard backend error contract", async () => {
    vi.stubGlobal("fetch", vi.fn().mockResolvedValue(new Response(JSON.stringify({
      ok: false,
      error: { code: "FAMILY_NOT_FOUND", message: "家庭不存在", retryable: false, details: {} },
      meta: { request_id: "error-request", timestamp: "2026-09-19T00:00:00Z" }
    }), { status: 404, headers: { "Content-Type": "application/json" } })));

    const error = await apiRequest("http://api.local", "/v1/home").catch((reason) => reason);
    expect(error).toBeInstanceOf(ApiClientError);
    expect(error).toMatchObject({ code: "FAMILY_NOT_FOUND", status: 404, requestId: "error-request" });
  });

  it("adds the saved bearer token to authenticated requests", async () => {
    const values = new Map<string, string>();
    vi.stubGlobal("localStorage", {
      getItem: (key: string) => values.get(key) ?? null,
      setItem: (key: string, value: string) => values.set(key, value),
      removeItem: (key: string) => values.delete(key)
    });
    saveAccessToken("signed-token");
    const fetchMock = vi.fn().mockResolvedValue(new Response(JSON.stringify({
      ok: true,
      data: {},
      meta: { request_id: "auth-request", timestamp: "2026-09-19T00:00:00Z" }
    }), { status: 200, headers: { "Content-Type": "application/json" } }));
    vi.stubGlobal("fetch", fetchMock);

    await apiRequest("http://api.local", "/v1/session");
    const requestOptions = fetchMock.mock.calls[0][1] as RequestInit;
    expect(new Headers(requestOptions.headers).get("Authorization")).toBe("Bearer signed-token");
  });
});
