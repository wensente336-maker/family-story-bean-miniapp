const api = require("../../services/api");
const auth = require("../../services/auth");

Page({
  data: {
    familyName: "小满一家",
    processing: {
      title: "周日晚餐",
      detail: "正在发现值得留下的时刻",
      progress: 68
    },
    moments: [
      {
        id: "moment-1",
        theme: "童言童语",
        duration: "00:48",
        title: "月亮是天空的夜灯",
        quote: "那星星就是忘记关掉的小灯吗？",
        color: "sun"
      },
      {
        id: "moment-2",
        theme: "家庭趣事",
        duration: "01:12",
        title: "爸爸的海水蛋糕",
        quote: "爸爸，你是不是把盐当成糖啦？",
        color: "coral"
      }
    ],
    loading: true,
    loadError: ""
  },

  async onLoad() {
    try {
      const session = await auth.ensureSession();
      getApp().globalData.session = session;
      if (!session.family) {
        wx.redirectTo({ url: "/pages/family/index?mode=create" });
        return;
      }
      await this.loadHome();
    } catch (_error) {
      wx.redirectTo({ url: "/pages/status/index?type=auth" });
    }
  },

  async loadHome() {
    try {
      const home = await api.getHomeData();
      this.setData({
        familyName: home.family.name,
        processing: home.processing,
        moments: home.moments,
        loading: false,
        loadError: ""
      });
    } catch (_error) {
      this.setData({ loading: false, loadError: "首页内容加载失败，请稍后重试" });
    }
  },

  chooseAudio() {
    wx.chooseMessageFile({
      count: 1,
      type: "file",
      extension: ["mp3", "m4a", "wav", "aac"],
      success: (result) => {
        const file = result.tempFiles && result.tempFiles[0];
        wx.showToast({
          title: file ? "已选择录音" : "选择成功",
          icon: "success"
        });
      },
      fail: (error) => {
        if (error && /cancel/i.test(error.errMsg || "")) return;
        wx.showToast({ title: "暂时无法选择文件", icon: "none" });
      }
    });
  },

  openMoment(event) {
    const id = event.currentTarget.dataset.id;
    const moment = this.data.moments.find((item) => item.id === id);
    wx.showToast({
      title: moment ? moment.title : "打开家庭时刻",
      icon: "none",
      duration: 1800
    });
  },

  openCreation(event) {
    const type = event.currentTarget.dataset.type;
    wx.showToast({
      title: type === "comic" ? "选择故事生成漫画" : "选择故事生成播客",
      icon: "none"
    });
  },

  openTimeline() {
    wx.showToast({ title: "成长时间线即将开放", icon: "none" });
  },

  openFamily() {
    wx.navigateTo({ url: "/pages/family/index" });
  }
});
