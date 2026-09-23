import { describe, expect, it } from "vitest";
import { formatDuration, normalizeHomeData } from "./homeApi";

describe("home API contract", () => {
  it("normalizes backend snake_case data for the React view", () => {
    const result = normalizeHomeData({
      family: { id: "family-1", name: "豆豆一家", member_labels: ["爸", "妈", "豆"] },
      processing: {
        recording_id: "recording-1",
        job_id: "job-1",
        title: "周末出游",
        detail: "正在发现高光",
        stage: "ANALYZING",
        progress: 62
      },
      moments: [{
        id: "moment-1",
        recording_id: "recording-1",
        theme: "童言童语",
        duration_ms: 195000,
        title: "会飞的胡萝卜",
        quote: "胡萝卜也想去旅行。",
        color: "sun"
      }]
    });

    expect(result.family.members).toEqual(["爸", "妈", "豆"]);
    expect(result.processing.progress).toBe(62);
    expect(result.moments[0].duration).toBe("03:15");
    expect(result.moments[0].recordingId).toBe("recording-1");
    expect(result.moments[0].tone).toBe("honey");
    expect(result.moments[0].image).toBeUndefined();
  });

  it("formats the 15 minute boundary", () => {
    expect(formatDuration(0)).toBe("00:00");
    expect(formatDuration(900000)).toBe("15:00");
  });
});
