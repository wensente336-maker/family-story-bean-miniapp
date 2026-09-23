import { afterEach, describe, expect, it, vi } from "vitest";
import {
  createNarrationPreview, createPodcast, createPodcastMaterialDraft, createPodcastPlanDraft, getPodcast,
  getPodcastMaterialSet, getPodcastPlan, getPodcastPlayback, remixPodcast,
  updatePodcastMaterialSet, updatePodcastPlan, getPodcastProduct, updatePodcastProduct,
  uploadPodcastCover, deletePodcastCover, listPodcastProducts, createPodcastShare,
  listPodcastShares, revokePodcastShare, getPublicPodcastShare,
  listPodcastTrash, trashPodcastProduct, restorePodcastProduct,
} from "./podcastApi";

afterEach(() => vi.unstubAllGlobals());

describe("podcast API", () => {
  it("requires a confirmed soft delete and uses a separate restore route", async () => {
    const fetchMock = vi.fn().mockImplementation(async () => new Response(JSON.stringify({
      ok: true, data: {}, meta: { request_id: "trash", timestamp: "2026-09-22T00:00:00Z" }
    }), { status: 200, headers: { "Content-Type": "application/json" } }));
    vi.stubGlobal("fetch", fetchMock);
    await listPodcastTrash();
    await trashPodcastProduct("recording-1");
    await restorePodcastProduct("recording-1");
    expect(fetchMock.mock.calls[0][0]).toMatch(/\/v1\/podcast-products\/trash$/);
    expect(fetchMock.mock.calls[1]).toEqual([
      expect.stringMatching(/\/recordings\/recording-1\/podcast-product$/),
      expect.objectContaining({ method: "DELETE", body: JSON.stringify({ confirmed: true }) })
    ]);
    expect(fetchMock.mock.calls[2]).toEqual([
      expect.stringMatching(/\/podcast-product\/restore$/), expect.objectContaining({ method: "POST" })
    ]);
  });
  it("uses create, read, remix and playback routes", async () => {
    const fetchMock = vi.fn().mockImplementation(async () => new Response(JSON.stringify({
      ok: true, data: {}, meta: { request_id: "podcast", timestamp: "2026-09-20T00:00:00Z" }
    }), { status: 200, headers: { "Content-Type": "application/json" } }));
    vi.stubGlobal("fetch", fetchMock);

    await createPodcast(["moment-1"]);
    await getPodcast("podcast-1");
    await remixPodcast("podcast-1", { moment_ids: ["moment-1"], intro: "开场", outro: "片尾" });
    await getPodcastPlayback("podcast-1");
    await getPodcastMaterialSet("recording-1");
    await createPodcastMaterialDraft("recording-1");
    await updatePodcastMaterialSet("recording-1", "DRAFT", [{
      id: "material-1", family_member_id: null, speaker_label: "说话人 A",
      role: "highlight", position: 1, start_ms: 1000, end_ms: 3000,
      confirmed_text: "确认文本", share_allowed: true,
    }]);
    await getPodcastPlan("recording-1");
    await createPodcastPlanDraft("recording-1", "warm");
    const plan = {
      id: "plan-1", material_set_id: "set-1", status: "DRAFT" as const,
      revision: 1, schema_version: "podcast-plan-v1", title: "家庭播客",
      description: "", narrator_voice: "voice-1", music_style: "warm",
      narration_style: "warm" as const, generator_provider: "safe",
      prompt_version: "v1", model_version: "v1", external_share_allowed: true,
      safety_checks: {}, segments: [{ segment_index: 1, kind: "narration" as const,
        label: "开场", text: "开场解说", source_material_ids: ["material-1"] }],
    };
    await updatePodcastPlan("recording-1", "DRAFT", plan);
    await createNarrationPreview("recording-1", 1);
    await getPodcastProduct("recording-1");
    await updatePodcastProduct("recording-1", {
      title: "家庭播客", description: "简介", tags: ["家庭日常"]
    });
    await uploadPodcastCover(
      "recording-1", new File([new Uint8Array([1, 2])], "cover.jpg", { type: "image/jpeg" }), 0.4, 0.6
    );
    await deletePodcastCover("recording-1");
    await listPodcastProducts("家庭日常");
    await createPodcastShare("recording-1", 72);
    await listPodcastShares("recording-1");
    await revokePodcastShare("share-1");
    await getPublicPodcastShare("public-token");

    const requests = fetchMock.mock.calls.map(([url, options]) => ({
      url: String(url), method: (options as RequestInit).method ?? "GET"
    }));
    expect(requests).toEqual(expect.arrayContaining([
      expect.objectContaining({ method: "POST", url: expect.stringMatching(/\/v1\/podcasts$/) }),
      expect.objectContaining({ method: "GET", url: expect.stringMatching(/\/v1\/podcasts\/podcast-1$/) }),
      expect.objectContaining({ method: "PATCH", url: expect.stringMatching(/\/v1\/podcasts\/podcast-1$/) }),
      expect.objectContaining({ method: "POST", url: expect.stringMatching(/\/playback-url$/) }),
      expect.objectContaining({ method: "GET", url: expect.stringMatching(/\/podcast-material-set$/) }),
      expect.objectContaining({ method: "POST", url: expect.stringMatching(/\/podcast-material-set\/draft$/) }),
      expect.objectContaining({ method: "PUT", url: expect.stringMatching(/\/podcast-material-set$/) }),
      expect.objectContaining({ method: "GET", url: expect.stringMatching(/\/podcast-plan$/) }),
      expect.objectContaining({ method: "POST", url: expect.stringMatching(/\/podcast-plan\/draft$/) }),
      expect.objectContaining({ method: "PUT", url: expect.stringMatching(/\/podcast-plan$/) }),
      expect.objectContaining({ method: "POST", url: expect.stringMatching(/\/narration-preview$/) }),
      expect.objectContaining({ method: "GET", url: expect.stringMatching(/\/podcast-product$/) }),
      expect.objectContaining({ method: "PATCH", url: expect.stringMatching(/\/podcast-product$/) }),
      expect.objectContaining({ method: "POST", url: expect.stringMatching(/\/podcast-product\/cover\?focal_x=0.4&focal_y=0.6$/) }),
      expect.objectContaining({ method: "DELETE", url: expect.stringMatching(/\/podcast-product\/cover$/) }),
      expect.objectContaining({ method: "GET", url: expect.stringMatching(/\/podcast-products\?tag=/) }),
      expect.objectContaining({ method: "POST", url: expect.stringMatching(/\/recordings\/recording-1\/podcast-shares$/) }),
      expect.objectContaining({ method: "GET", url: expect.stringMatching(/\/podcast-shares\?recording_id=recording-1$/) }),
      expect.objectContaining({ method: "DELETE", url: expect.stringMatching(/\/podcast-shares\/share-1$/) }),
      expect.objectContaining({ method: "GET", url: expect.stringMatching(/\/public\/podcast-shares\/public-token$/) }),
    ]));
  });
});
