import { describe, expect, it } from "vitest";
import {
  inferSourceType, maxAudioBytes, maxVideoBytes, validateAudioSelection,
  validateMediaSelection
} from "./recordingApi";

describe("validateAudioSelection", () => {
  it("accepts the four MVP extensions", () => {
    for (const extension of ["mp3", "m4a", "wav", "aac"]) {
      expect(validateAudioSelection(new File(["audio"], `story.${extension}`))).toBeNull();
    }
  });

  it("accepts mobile audio and recording bean WebM", () => {
    expect(validateMediaSelection(new File(["audio"], "phone.webm", { type: "audio/webm" }), "mobile_recording")).toBeNull();
    expect(validateMediaSelection(new File(["audio"], "bean.m4a"), "recording_bean")).toBeNull();
  });

  it("accepts video sources and applies the video size limit", () => {
    const video = new File(["video"], "family.mov", { type: "video/quicktime" });
    expect(inferSourceType(video)).toBe("video_upload");
    expect(validateMediaSelection(video)).toBeNull();
    Object.defineProperty(video, "size", { value: maxVideoBytes + 1 });
    expect(validateMediaSelection(video)).toContain("500 MB");
  });

  it("rejects unsupported, empty and oversized files", () => {
    expect(validateAudioSelection(new File(["x"], "story.txt"))).toContain("MP3");
    expect(validateAudioSelection(new File([], "story.wav"))).toContain("为空");
    const oversized = new File([new Uint8Array(1)], "story.wav");
    Object.defineProperty(oversized, "size", { value: maxAudioBytes + 1 });
    expect(validateAudioSelection(oversized)).toContain("100 MB");
  });
});
