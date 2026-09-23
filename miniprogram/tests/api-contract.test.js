const test = require("node:test");
const assert = require("node:assert/strict");

const { formatDuration, normalizeHomeData } = require("../services/api");

test("normalizes backend snake_case fields for the home page", () => {
  const normalized = normalizeHomeData({
    family: {
      id: "family_demo_001",
      name: "豆豆一家",
      member_labels: ["爸爸", "妈妈", "豆豆"]
    },
    processing: {
      recording_id: "recording_demo_002",
      job_id: "job_demo_001",
      title: "周末动物园",
      detail: "AI 正在发现高光",
      stage: "highlighting",
      progress: 60
    },
    moments: [
      {
        id: "moment_demo_001",
        recording_id: "recording_demo_001",
        theme: "晚餐",
        duration_ms: 195000,
        title: "会飞的胡萝卜",
        quote: "原来胡萝卜也想去旅行。",
        color: "orange"
      }
    ]
  });

  assert.deepEqual(normalized.family.memberLabels, ["爸爸", "妈妈", "豆豆"]);
  assert.equal(normalized.processing.recordingId, "recording_demo_002");
  assert.equal(normalized.processing.jobId, "job_demo_001");
  assert.equal(normalized.moments[0].recordingId, "recording_demo_001");
  assert.equal(normalized.moments[0].duration, "03:15");
});

test("formats durations using mm:ss", () => {
  assert.equal(formatDuration(0), "00:00");
  assert.equal(formatDuration(899000), "14:59");
});

