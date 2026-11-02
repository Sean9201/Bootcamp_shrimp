import { cleanup, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it } from "vitest";
import { ComparisonTable } from "./Bits.jsx";

afterEach(cleanup);   // vitest 전역 설정이 없어 자동 정리가 안 됨

const ROWS = [
  { metric: "peak_cpm", normal_mean: 99.5, normal_sd: 10.4, current: 39, change_pct: -60.8 },
  { metric: "onset_min", normal_mean: 2.0, normal_sd: 0.0, current: 4, change_pct: 100.0 },
];

describe("지표 비교표", () => {
  it("± 가 날짜별 차이임을 표 머리에 밝힌다", () => {
    render(<ComparisonTable rows={ROWS} onsetFloor={0.7} />);
    expect(screen.getByText("정상 4일 평균 ± 날짜별 차이")).toBeTruthy();
  });

  it("반응 시작 차이가 하한보다 작으면 점수 계산 기준을 덧붙인다", () => {
    render(<ComparisonTable rows={ROWS} onsetFloor={0.7} />);
    expect(screen.getAllByText("점수 계산엔 최소 ±0.7분 차이로 봄")).toHaveLength(1);
  });

  it("차이가 하한 이상이면 덧붙이지 않는다", () => {
    render(<ComparisonTable rows={[{ ...ROWS[1], normal_sd: 1.2 }]} onsetFloor={0.7} />);
    expect(screen.queryByText(/점수 계산엔/)).toBeNull();
  });
});
