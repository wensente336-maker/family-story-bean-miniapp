export type ShareResult = "shared" | "copied";

type ShareNavigator = {
  share?: (data?: ShareData) => Promise<void>;
  clipboard?: { writeText: (value: string) => Promise<void> };
};

export async function shareOrCopy(
  data: ShareData,
  browser: ShareNavigator = navigator,
): Promise<ShareResult> {
  if (browser.share) {
    try {
      await browser.share(data);
      return "shared";
    } catch {
      // Cancellation and platform errors both fall back to a durable copy action.
    }
  }
  if (!browser.clipboard?.writeText || !data.url) {
    throw new Error("此浏览器无法分享或复制链接");
  }
  await browser.clipboard.writeText(data.url);
  return "copied";
}
