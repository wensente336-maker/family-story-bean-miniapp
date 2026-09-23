const env = require("../config/env");
const mockApi = require("./mock-api");

function request(path, options = {}) {
  return new Promise((resolve, reject) => {
    const token = wx.getStorageSync("storybean_access_token");
    wx.request({
      url: `${env.apiBaseUrl}${path}`,
      method: options.method || "GET",
      data: options.data,
      header: {
        "Content-Type": "application/json",
        "X-Request-Id": `miniapp-${Date.now()}`,
        ...(token ? { Authorization: `Bearer ${token}` } : {})
      },
      success(response) {
        if (response.statusCode >= 200 && response.statusCode < 300 && response.data.ok) {
          resolve(response.data.data);
          return;
        }
        reject(response.data && response.data.error ? response.data.error : new Error("REQUEST_FAILED"));
      },
      fail: reject
    });
  });
}

function normalizeHomeData(data) {
  return {
    family: {
      id: data.family.id,
      name: data.family.name,
      memberLabels: data.family.member_labels || data.family.memberLabels
    },
    processing: data.processing
      ? {
          recordingId: data.processing.recording_id || data.processing.recordingId,
          jobId: data.processing.job_id || data.processing.jobId,
          title: data.processing.title,
          detail: data.processing.detail,
          stage: data.processing.stage,
          progress: data.processing.progress
        }
      : null,
    moments: data.moments.map((moment) => ({
      id: moment.id,
      recordingId: moment.recording_id || moment.recordingId,
      theme: moment.theme,
      durationMs: moment.duration_ms || moment.durationMs,
      duration: moment.duration || formatDuration(moment.duration_ms || moment.durationMs),
      title: moment.title,
      quote: moment.quote,
      color: moment.color
    }))
  };
}

function formatDuration(durationMs) {
  const totalSeconds = Math.floor(durationMs / 1000);
  const minutes = String(Math.floor(totalSeconds / 60)).padStart(2, "0");
  const seconds = String(totalSeconds % 60).padStart(2, "0");
  return `${minutes}:${seconds}`;
}

async function getHomeData() {
  const data = env.useMockApi ? await mockApi.getHomeData() : await request("/v1/mock/home");
  return normalizeHomeData(data);
}

async function wechatLogin(code) {
  return env.useMockApi ? mockApi.wechatLogin(code) : request("/v1/auth/wechat", {
    method: "POST",
    data: { code }
  });
}

async function getSession() {
  return env.useMockApi ? mockApi.getSession() : request("/v1/session");
}

async function createFamily(input) {
  return env.useMockApi ? mockApi.createFamily(input) : request("/v1/families", {
    method: "POST",
    data: input
  });
}

async function renameFamily(familyId, name) {
  return env.useMockApi ? mockApi.renameFamily(familyId, name) : request(`/v1/families/${familyId}`, {
    method: "PATCH",
    data: { name }
  });
}

async function addFamilyMember(familyId, nickname) {
  return env.useMockApi
    ? mockApi.addFamilyMember(familyId, nickname)
    : request(`/v1/families/${familyId}/members`, {
        method: "POST",
        data: { nickname }
      });
}

module.exports = {
  request,
  getHomeData,
  normalizeHomeData,
  formatDuration,
  wechatLogin,
  getSession,
  createFamily,
  renameFamily,
  addFamilyMember
};
