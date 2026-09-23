import type { HomeData } from "../types";

const homeFixture: HomeData = {
  family: { name: "小满一家", members: ["爸", "妈", "满"] },
  processing: {
    title: "周日晚餐",
    detail: "正在发现值得留下的时刻",
    progress: 68
  },
  moments: [
    {
      id: "moon-night-light",
      recordingId: "22222222-2222-4222-8222-222222222222",
      theme: "童言童语",
      duration: "00:48",
      title: "月亮是天空的夜灯",
      quote: "那星星就是忘记关掉的小灯吗？",
      tone: "honey",
      image: "/assets/family-dinner.png"
    },
    {
      id: "salt-cake",
      recordingId: "22222222-2222-4222-8222-222222222222",
      theme: "家庭趣事",
      duration: "01:12",
      title: "爸爸的海水蛋糕",
      quote: "爸爸，你是不是把盐当成糖啦？",
      tone: "coral"
    }
  ]
};

export async function getHomeData(): Promise<HomeData> {
  await new Promise((resolve) => window.setTimeout(resolve, 360));
  return structuredClone(homeFixture);
}
