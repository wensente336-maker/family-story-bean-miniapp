import { afterEach, describe, expect, it, vi } from "vitest";
import { clearAccessToken, getAccessToken, saveAccessToken } from "./authStore";

class MemoryStorage {
  private values = new Map<string, string>();
  getItem(key: string) { return this.values.get(key) ?? null; }
  setItem(key: string, value: string) { this.values.set(key, value); }
  removeItem(key: string) { this.values.delete(key); }
}

afterEach(() => vi.unstubAllGlobals());

describe("auth token storage", () => {
  it("persists and clears the access token", () => {
    vi.stubGlobal("localStorage", new MemoryStorage());
    expect(getAccessToken()).toBeNull();
    saveAccessToken("signed-token");
    expect(getAccessToken()).toBe("signed-token");
    clearAccessToken();
    expect(getAccessToken()).toBeNull();
  });
});
