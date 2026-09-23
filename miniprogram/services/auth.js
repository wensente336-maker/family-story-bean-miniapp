const api = require("./api");

const TOKEN_KEY = "storybean_access_token";
const SESSION_KEY = "storybean_session";

function wxLogin() {
  return new Promise((resolve, reject) => {
    wx.login({
      success(result) {
        if (result.code) resolve(result.code);
        else reject(new Error("WECHAT_CODE_MISSING"));
      },
      fail: reject
    });
  });
}

function saveAuth(authData) {
  wx.setStorageSync(TOKEN_KEY, authData.access_token);
  const session = { user_id: authData.user_id, family: authData.family };
  wx.setStorageSync(SESSION_KEY, session);
  return session;
}

async function login() {
  const code = await wxLogin();
  return saveAuth(await api.wechatLogin(code));
}

async function ensureSession() {
  const token = wx.getStorageSync(TOKEN_KEY);
  if (!token) return login();
  try {
    const session = await api.getSession();
    wx.setStorageSync(SESSION_KEY, session);
    return session;
  } catch (_error) {
    logout();
    return login();
  }
}

function updateFamily(family) {
  const session = wx.getStorageSync(SESSION_KEY) || {};
  const updated = { ...session, family };
  wx.setStorageSync(SESSION_KEY, updated);
  getApp().globalData.session = updated;
  return updated;
}

function logout() {
  wx.removeStorageSync(TOKEN_KEY);
  wx.removeStorageSync(SESSION_KEY);
  const app = getApp();
  if (app) app.globalData.session = null;
}

module.exports = { login, ensureSession, updateFamily, logout };
