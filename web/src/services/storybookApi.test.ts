import { afterEach, describe, expect, it, vi } from "vitest";
import {
  createOrRefreshStorybook,
  createStorybookAudioSession,
  createStorybookExperienceSession,
} from "./storybookApi";

afterEach(() => vi.unstubAllGlobals());

describe("storybook API", () => {
  it("normalizes the persisted manifest and its source versions", async () => {
    const fetchMock = vi.fn().mockResolvedValue(new Response(JSON.stringify({
      ok: true,
      data: {
        id: "book-1",
        comic_id: "comic-1",
        recording_id: "recording-1",
        title: "会飞的西红柿",
        status: "DRAFT",
        current_version: 2,
        schema_version: "storybook-manifest-v1",
        source_comic_version: 4,
        manifest: {
          schema_version: "storybook-manifest-v1",
          source_comic_id: "comic-1",
          source_comic_version: 4,
          title: "会飞的西红柿",
          page_count: 2,
          audio: {
            background_mode: "client-synthesized",
            page_turn_mode: "client-synthesized",
            narration_mode: "browser-speech",
            highlight_source: "recording-source-segments"
          },
          pages: [
            { index: 0, type: "cover", title: "封面", narration: "开始", panel_index: 1, panel_version: 3, clip: null },
            { index: 1, type: "ending", title: "封底", narration: "结束", panel_index: 1, panel_version: 3, clip: null }
          ]
        },
        created_at: "2026-09-20T00:00:00Z",
        updated_at: "2026-09-20T00:01:00Z"
      },
      meta: { request_id: "storybook-request", timestamp: "2026-09-20T00:01:00Z" }
    }), { status: 200, headers: { "Content-Type": "application/json" } }));
    vi.stubGlobal("fetch", fetchMock);

    const storybook = await createOrRefreshStorybook("comic-1");

    expect(storybook.currentVersion).toBe(2);
    expect(storybook.recordingId).toBe("recording-1");
    expect(storybook.sourceComicVersion).toBe(4);
    expect(storybook.manifest.pages[0].panelVersion).toBe(3);
    expect(String(fetchMock.mock.calls[0][0])).toMatch(/\/v1\/comics\/comic-1\/storybook$/);
    expect((fetchMock.mock.calls[0][1] as RequestInit).method).toBe("POST");
  });

  it("normalizes private page audio session URLs", async () => {
    const fetchMock = vi.fn().mockResolvedValue(new Response(JSON.stringify({
      ok: true,
      data: {
        storybook_id: "book-1",
        version: 2,
        source_recording_id: "recording-1",
        expires_at: 2000000000,
        clips: [{
          page_index: 2,
          source_segment_id: "segment-2",
          original_start_ms: 1200,
          original_end_ms: 4800,
          duration_ms: 3600,
          url: "http://127.0.0.1:8000/v1/playback/private-token"
        }]
      },
      meta: { request_id: "audio-request", timestamp: "2026-09-20T00:01:00Z" }
    }), { status: 200, headers: { "Content-Type": "application/json" } }));
    vi.stubGlobal("fetch", fetchMock);

    const session = await createStorybookAudioSession("book-1");

    expect(session.clips[0]).toMatchObject({ pageIndex: 2, durationMs: 3600 });
    expect(String(fetchMock.mock.calls[0][0])).toMatch(/\/v1\/storybooks\/book-1\/audio-session$/);
  });

  it("normalizes the continuous story timeline", async () => {
    const fetchMock = vi.fn().mockResolvedValue(new Response(JSON.stringify({
      ok: true,
      data: {
        storybook_id: "book-1", version: 1, source_recording_id: "recording-1",
        duration_ms: 12000, url: "http://127.0.0.1:8000/v1/playback/track",
        expires_at: 2000000000, storyline_schema_version: "storybook-storyline-v1",
        scenes: [{
          page_index: 1, type: "story", title: "第一幕", narration: "故事发生了。",
          quote: "真实原声", source_segment_id: "segment-1", image_prompt: "绘本第一幕",
          asset_url: "/assets/storybooks/tomato-v1/scene-02-setup.webp",
          audio_start_ms: 1000, audio_end_ms: 6000
        }],
        cues: [{
          segment_index: 1, kind: "narration", label: "故事解说", text: "故事发生了。",
          page_index: 1, start_ms: 1000, end_ms: 2500, source_segment_id: null
        }],
        narrator_provider: "volcengine-doubao", narrator_voice: "warm",
        music_source: "generated-two-tone-ambient"
      },
      meta: { request_id: "experience-request", timestamp: "2026-09-20T00:01:00Z" }
    }), { status: 200, headers: { "Content-Type": "application/json" } }));
    vi.stubGlobal("fetch", fetchMock);

    const experience = await createStorybookExperienceSession("book-1");

    expect(experience.scenes[0]).toMatchObject({
      pageIndex: 1,
      audioStartMs: 1000,
      assetUrl: "/assets/storybooks/tomato-v1/scene-02-setup.webp",
    });
    expect(experience.cues[0]).toMatchObject({ kind: "narration", endMs: 2500 });
    expect(String(fetchMock.mock.calls[0][0])).toMatch(/\/experience-session$/);
  });
});
