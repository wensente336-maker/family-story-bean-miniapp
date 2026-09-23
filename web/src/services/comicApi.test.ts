import { afterEach, describe, expect, it, vi } from "vitest";
import { createComic, getComic, regenerateComicPanel } from "./comicApi";

afterEach(() => vi.unstubAllGlobals());

describe("comic API", () => {
  it("uses the create, read and single-panel regeneration routes", async () => {
    const fetchMock = vi.fn().mockImplementation(async () => new Response(JSON.stringify({
      ok: true,
      data: {},
      meta: { request_id: "comic-request", timestamp: "2026-09-20T00:00:00Z" }
    }), { status: 200, headers: { "Content-Type": "application/json" } }));
    vi.stubGlobal("fetch", fetchMock);

    await createComic("moment-1");
    await getComic("comic-1");
    await regenerateComicPanel("comic-1", 2);

    const requests = fetchMock.mock.calls.map(([url, options]) => ({
      url: String(url), method: (options as RequestInit).method ?? "GET"
    }));
    expect(requests[0]).toMatchObject({ method: "POST" });
    expect(requests[0].url).toMatch(/\/v1\/moments\/moment-1\/comics$/);
    expect(requests[1]).toMatchObject({ method: "GET" });
    expect(requests[1].url).toMatch(/\/v1\/comics\/comic-1$/);
    expect(requests[2]).toMatchObject({ method: "POST" });
    expect(requests[2].url).toMatch(/\/v1\/comics\/comic-1\/panels\/2\/regenerate$/);
  });
});
