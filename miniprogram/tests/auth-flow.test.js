const test = require("node:test");
const assert = require("node:assert/strict");

const storage = new Map();
global.wx = {
  login({ success }) {
    success({ code: "mock-wechat-code" });
  },
  getStorageSync(key) {
    return storage.get(key);
  },
  setStorageSync(key, value) {
    storage.set(key, value);
  },
  removeStorageSync(key) {
    storage.delete(key);
  }
};
const app = { globalData: { session: null } };
global.getApp = () => app;

const auth = require("../services/auth");

test("login persists and restores the mock family session", async () => {
  auth.logout();
  const session = await auth.ensureSession();
  assert.equal(session.family.name, "小满一家");
  assert.equal(storage.get("storybean_access_token"), "mock-access-token");

  const restored = await auth.ensureSession();
  assert.equal(restored.user_id, session.user_id);
  assert.equal(restored.family.id, session.family.id);
});

test("logout removes local credentials", async () => {
  await auth.ensureSession();
  auth.logout();
  assert.equal(storage.has("storybean_access_token"), false);
  assert.equal(storage.has("storybean_session"), false);
  assert.equal(app.globalData.session, null);
});
