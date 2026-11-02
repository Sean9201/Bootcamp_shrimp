// 차트(SVG·Recharts)용 색. styles.css 의 :root 토큰과 같은 값을 쓴다.
export const COLOR = {
  text: "#0f1f1e",
  muted: "#4f6361",
  hue: "#0f6b78",        // 이번 급이 곡선 — 화면에서 유일한 데이터 색
  neg: "#c8283a",        // 경보
  warn: "#8a5a00",       // 주의
  ok: "#22735a",         // 정상
  band: "#cfe3e5",       // 정상 범위
  mean: "#6f8d90",       // 정상 평균
  grid: "#e3ecea",
  axis: "#9ab0ae",
  surface: "#fbfdfc",
  raised: "#d8e6e3",
  // 어두운 판정 칸 위
  onDark: "#eef5f4",
  onDarkMuted: "#a9bdbb",
  onDarkLine: "#2b403e",
  onDarkNeg: "#ff8a96",
  onDarkWarn: "#e7bf5f",
};

export const FONT = {
  display: '"Black Han Sans", "Gothic A1", sans-serif',
  body: '"Gothic A1", system-ui, sans-serif',
};
