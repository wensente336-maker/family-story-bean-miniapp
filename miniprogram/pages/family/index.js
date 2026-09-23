const api = require("../../services/api");
const auth = require("../../services/auth");

Page({
  data: {
    mode: "manage",
    family: null,
    familyName: "",
    ownerNickname: "",
    memberNickname: "",
    saving: false,
    error: ""
  },

  async onLoad(options) {
    try {
      const session = await auth.ensureSession();
      const mode = options.mode === "create" || !session.family ? "create" : "manage";
      this.setData({
        mode,
        family: session.family,
        familyName: session.family ? session.family.name : ""
      });
    } catch (_error) {
      wx.redirectTo({ url: "/pages/status/index?type=auth" });
    }
  },

  onFamilyName(event) {
    this.setData({ familyName: event.detail.value });
  },

  onOwnerNickname(event) {
    this.setData({ ownerNickname: event.detail.value });
  },

  onMemberNickname(event) {
    this.setData({ memberNickname: event.detail.value });
  },

  async saveFamily() {
    const name = this.data.familyName.trim();
    const owner = this.data.ownerNickname.trim();
    const creating = this.data.mode === "create";
    if (!name || (creating && !owner)) {
      this.setData({ error: "请填写家庭名称和你的家庭昵称" });
      return;
    }
    this.setData({ saving: true, error: "" });
    try {
      const family = creating
        ? await api.createFamily({ name, owner_nickname: owner })
        : await api.renameFamily(this.data.family.id, name);
      auth.updateFamily(family);
      this.setData({ family, mode: "manage", saving: false });
      wx.showToast({ title: "已保存", icon: "success" });
      if (creating) wx.reLaunch({ url: "/pages/home/index" });
    } catch (_error) {
      this.setData({ saving: false, error: "保存失败，请稍后重试" });
    }
  },

  async addMember() {
    const nickname = this.data.memberNickname.trim();
    if (!nickname) return;
    this.setData({ saving: true, error: "" });
    try {
      const member = await api.addFamilyMember(this.data.family.id, nickname);
      const family = { ...this.data.family, members: [...this.data.family.members, member] };
      auth.updateFamily(family);
      this.setData({ family, memberNickname: "", saving: false });
    } catch (_error) {
      this.setData({ saving: false, error: "添加成员失败" });
    }
  }
});
