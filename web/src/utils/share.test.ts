import { describe, expect, it, vi } from "vitest";
import { shareOrCopy } from "./share";

describe("shareOrCopy", () => {
  it("uses Web Share when it is available", async () => {
    const share = vi.fn().mockResolvedValue(undefined);
    const writeText = vi.fn();
    await expect(shareOrCopy({ url: "https://example.test/s" }, {
      share, clipboard: { writeText },
    })).resolves.toBe("shared");
    expect(writeText).not.toHaveBeenCalled();
  });

  it("copies the link when Web Share is unavailable", async () => {
    const writeText = vi.fn().mockResolvedValue(undefined);
    await expect(shareOrCopy({ url: "https://example.test/s" }, {
      clipboard: { writeText },
    })).resolves.toBe("copied");
    expect(writeText).toHaveBeenCalledWith("https://example.test/s");
  });

  it("copies the link when Web Share rejects", async () => {
    const writeText = vi.fn().mockResolvedValue(undefined);
    await expect(shareOrCopy({ url: "https://example.test/s" }, {
      share: vi.fn().mockRejectedValue(new Error("unsupported")),
      clipboard: { writeText },
    })).resolves.toBe("copied");
    expect(writeText).toHaveBeenCalledOnce();
  });
});
