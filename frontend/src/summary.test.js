import { describe, expect, it } from "vitest";
import { tileFromDetail } from "./components/TankPlan.jsx";
import { feedingSummary, initialState, reduceAll } from "./stream.js";

const BASE = { mu: Array(40).fill(50), lo: Array(40).fill(40), hi: Array(40).fill(60), metrics: {} };
const META = { type: "meta", pre_min: 10, post_min: 30, baseline: BASE, tank_id: "B1" };

describe("판정 칸 제목 문장", () => {
  it("급이 전에는 배경을 듣는 중", () => {
    const s = reduceAll(initialState, [META, { type: "minute", minute: -3, cpm: 9 }]);
    expect(feedingSummary(s).text).toBe("급이 전 배경 소리를 듣는 중입니다");
  });
  it("누적이 정상보다 적으면 몇 % 덜 먹고 있는지 (진행형 → 완료형)", () => {
    const evs = [META, { type: "minute", minute: 0, cpm: 20 }, { type: "minute", minute: 1, cpm: 30 }];
    const s = reduceAll(initialState, evs);
    expect(feedingSummary(s).text).toBe("평소보다 50% 덜 먹고 있습니다");
    expect(feedingSummary(s).sub).toBe("급이 후 2분 누적 50회 · 같은 시간 정상 평균 100.0회");
    expect(feedingSummary(reduceAll(s, [{ type: "done" }])).text).toBe("평소보다 50% 덜 먹었습니다");
  });
  it("±15% 안이면 평소와 비슷, 넘으면 더 먹음", () => {
    const near = reduceAll(initialState, [META, { type: "minute", minute: 0, cpm: 55 }]);
    expect(feedingSummary(near).text).toBe("평소와 비슷하게 먹고 있습니다");
    const more = reduceAll(initialState, [META, { type: "minute", minute: 0, cpm: 80 }]);
    expect(feedingSummary(more).text).toBe("평소보다 60% 더 먹고 있습니다");
  });
  it("정상 기준이 없으면 활동량만", () => {
    const s = reduceAll(initialState, [{ ...META, baseline: null }, { type: "minute", minute: 0, cpm: 5 }]);
    expect(feedingSummary(s).text).toBe("정상 기준이 없어 활동량만 기록합니다");
  });
});

describe("평면도 수조 칸", () => {
  it("분석 상세에서 곡선·판정·첫 10분 변화율을 뽑는다", () => {
    const t = tileFromDetail({
      id: 7, max_grade: "alert", minutes: [{ minute: -10, cpm: 3 }, { minute: 0, cpm: 20 }], baseline: { mu: BASE.mu },
      metrics: { auc10: 201 }, comparison: [{ metric: "auc10", change_pct: -64.1 }],
    });
    expect(t).toMatchObject({ analysisId: 7, grade: "alert", auc10: 201, auc10Pct: -64.1, live: false });
    expect(t.cpm[0]).toBe(3);
    expect(t.cpm[10]).toBe(20);
    expect(t.cpm[11]).toBeNull();
  });
});
