import { describe, expect, it } from "vitest";
import { createPrototypeBookManifest } from "./bookManifest";
import type { Comic } from "../../services/comicApi";

function comic(): Comic {
  return {
    id: "comic-1",
    moment_id: "moment-1",
    title: "家庭时刻",
    status: "COMPLETED",
    version: 3,
    pipeline_version: "v1",
    metadata: {},
    panels: Array.from({ length: 4 }, (_, index) => ({
      id: `panel-${index + 1}`,
      panel_index: index + 1,
      narration: `解说 ${index + 1}`,
      dialogue: index === 0 ? "西红柿飞到奶奶家了" : `对白 ${index + 1}`,
      source_segment_id: `segment-${index + 1}`,
      asset_url: "/panel.png",
      asset_variant: "v1",
      crop_x: index % 2,
      crop_y: Math.floor(index / 2),
      prompt: "prompt",
      version: 1,
      created_at: "2026-09-20T00:00:00Z",
      updated_at: "2026-09-20T00:00:00Z",
    })),
    created_at: "2026-09-20T00:00:00Z",
    updated_at: "2026-09-20T00:00:00Z",
  };
}

describe("storybook manifest", () => {
  it("builds a versioned six-page book with bounded highlight clips", () => {
    const manifest = createPrototypeBookManifest(comic());
    expect(manifest).toMatchObject({
      schemaVersion: "storybook-manifest-v1",
      sourceComicId: "comic-1",
      sourceComicVersion: 3,
      title: "会飞的西红柿",
      pageCount: 6,
    });
    expect(manifest.pages.map((page) => page.type)).toEqual([
      "cover", "story", "story", "story", "story", "ending",
    ]);
    expect(manifest.pages[1].clip).toEqual({ startMs: 33_000, endMs: 37_500 });
    expect(manifest.pages[4].clip).toBeNull();
  });
});
