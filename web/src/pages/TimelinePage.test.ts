import { describe, expect, it } from "vitest";
import type { PodcastProduct } from "../services/podcastApi";
import { podcastProductTimelineItem } from "./TimelinePage";

describe("podcast product timeline mapping", () => {
  it("keeps the recording route and marks the saved product as non-legacy", () => {
    const product = {
      podcast_version_id: "version-1", recording_id: "recording-1", version: 1,
      status: "COMPLETED", title: "会飞的西红柿", description: "家庭晚餐",
      tags: [{ id: "tag-1", name: "欢乐瞬间", kind: "system" }],
      created_at: "2026-09-21T05:53:28Z",
    } as PodcastProduct;

    expect(podcastProductTimelineItem(product)).toMatchObject({
      id: "version-1", kind: "podcast", status: "product-v2",
      recording_id: "recording-1", target_path: "/recordings/recording-1/podcast",
      subtitle: "家庭晚餐 · #欢乐瞬间",
    });
  });
});
