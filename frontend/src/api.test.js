import { afterEach, describe, expect, it, vi } from "vitest";
import { request } from "./api.js";

describe("request", () => {
  afterEach(() => vi.unstubAllGlobals());

  it("통일 에러 메시지를 꺼낸다", async () => {
    vi.stubGlobal("fetch", vi.fn(async () => new Response(
      JSON.stringify({ error: { code: "not_found", message: "분석을 찾을 수 없습니다" } }), { status: 404 })));
    await expect(request("/x")).rejects.toThrow("분석을 찾을 수 없습니다");
  });

  it("서버 미응답", async () => {
    vi.stubGlobal("fetch", vi.fn(async () => { throw new TypeError("Failed to fetch"); }));
    await expect(request("/x")).rejects.toThrow("서버에 연결할 수 없습니다");
  });
});
