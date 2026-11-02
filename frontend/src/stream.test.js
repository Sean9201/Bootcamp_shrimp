import { describe, expect, it } from "vitest";
import { feedClock, kst, maxGrade } from "./format.js";
import { liveMetrics } from "./pages/AnalysisView.jsx";
import { chartRows, initialState, reduceAll } from "./stream.js";

const BASE = {
  tank: "B1", n_sessions: 4, minutes: [...Array(40)].map((_, i) => i - 10),
  mu: Array(40).fill(50), lo: Array(40).fill(40), hi: Array(40).fill(60),
  metrics: { peak_cpm: { mean: 100 }, auc10: { mean: 600 } },
};
const META = { type: "meta", analysis_id: 1, tank_id: "B1", pre_min: 10, post_min: 30, baseline: BASE,
  thresholds: { watch: 1.25, alert: 2 } };

describe("이벤트 → 화면 상태", () => {
  it("분·클릭·점수·경보·인사이트를 쌓는다", () => {
    const s = reduceAll(initialState, [
      META,
      { type: "clicks", t: [-30.5, 12.1] },
      { type: "minute", minute: -10, cpm: 8 },
      { type: "minute", minute: 0, cpm: 20 },
      { type: "minute", minute: 1, cpm: 90 },
      { type: "score", minute: 2, score: 2.4, grade: "alert", stage: "provisional" },
      { type: "score", minute: 3, score: 1.0, grade: "watch", stage: "provisional" },
      { type: "alert", minute: 2, level: "alert", score: 2.4 },
      { type: "progress", t_sec: 200 },
      { type: "final", metrics: {}, comparison: [] },
      { type: "insight_pending" },
      { type: "insight", source: "gemini", content: { summary: "s", bullets: [], recommendation: "r" } },
      { type: "done" },
    ]);
    expect(s.status).toBe("done");
    expect(s.clicks).toEqual([-30.5, 12.1]);
    expect(s.maxGrade).toBe("alert");          // 등급은 내려가도 최고 등급 유지
    expect(s.alerts).toHaveLength(1);
    expect(s.insight.source).toBe("gemini");
    expect(s.insightPending).toBe(false);
    expect(s.tSec).toBe(200);
  });

  it("meta 를 다시 받으면(재연결) 처음부터 다시 쌓는다", () => {
    const s = reduceAll(initialState, [META, { type: "clicks", t: [1, 2] }, META, { type: "clicks", t: [3] }]);
    expect(s.clicks).toEqual([3]);
  });

  it("snapshot(서버 재시작 후)도 같은 상태로 바꾼다", () => {
    const s = reduceAll(initialState, [{
      type: "snapshot", id: 7, tank_id: "B1", status: "done", speed: 40, duration_sec: 2400, feeding_offset_sec: 600,
      baseline: BASE, minutes: [{ minute: 0, cpm: 30 }], scores: [{ minute: 0, score: 0, grade: "normal" }],
      alerts: [], metrics: { peak_cpm: 30 }, comparison: [], max_grade: "normal",
      insight: { source: "template", summary: "a", bullets: [], recommendation: "b" },
    }]);
    expect(s.status).toBe("done");
    expect(s.minutes[0].cpm).toBe(30);
    expect(s.insight.content.summary).toBe("a");
    expect(s.tSec).toBe(1800);
  });

  it("차트 행은 분 구간 가운데에 정상 범위와 현재 값", () => {
    const s = reduceAll(initialState, [META, { type: "minute", minute: 0, cpm: 20 }]);
    const rows = chartRows(s);
    expect(rows).toHaveLength(40);
    const r0 = rows.find((r) => r.minute === 0);
    expect(r0).toMatchObject({ x: 0.5, cpm: 20, band: [40, 60], mu: 50 });
    expect(rows.find((r) => r.minute === 1).cpm).toBeNull();
  });

  it("진행 중 지표: 끝난 분까지의 Peak·초기 10분 AUC", () => {
    const s = reduceAll(initialState, [META, { type: "minute", minute: -1, cpm: 99 },
      { type: "minute", minute: 0, cpm: 20 }, { type: "minute", minute: 1, cpm: 70 }]);
    expect(liveMetrics(s)).toMatchObject({ peak: 70, auc10: 90, n10: 2, peakRef: 100, aucRef: 600 });
  });
});

describe("표시 형식", () => {
  it("UTC 시각을 한국 시각으로", () => {
    expect(kst("2026-10-28T00:00:00+00:00")).toBe("2026-10-28 09:00");
    expect(kst(null)).toBe("—");
  });
  it("급이 기준 시각", () => {
    expect(feedClock(-300)).toBe("급이 전 5분");
    expect(feedClock(200)).toBe("급이 후 3분 20초");
  });
  it("등급 비교", () => {
    expect(maxGrade("watch", "normal")).toBe("watch");
    expect(maxGrade("watch", "alert")).toBe("alert");
  });
});
