Page({
  data: { title: "暂时无法进入", detail: "登录状态已失效，请重新进入小程序。" },
  onLoad(options) {
    if (options.type === "permission") {
      this.setData({ title: "没有访问权限", detail: "这个家庭内容不属于当前账号。" });
    }
  },
  retry() {
    wx.reLaunch({ url: "/pages/home/index" });
  }
});
