// 화면 표시용 이름·색·시각 형식

export const GRADES = {
  normal: { label: "정상", tone: "ok" },
  watch: { label: "주의", tone: "warn" },
  alert: { label: "경보", tone: "danger" },
};
export const gradeLabel = (g) => GRADES[g]?.label ?? "기준 없음";
export const gradeTone = (g) => GRADES[g]?.tone ?? "muted";
const ORDER = ["normal", "watch", "alert"];
export const maxGrade = (a, b) => (ORDER.indexOf(b) > ORDER.indexOf(a) ? b : a);

export const CONDITIONS = { blocked: "소음 차단", operating: "운영 소음" };
export const conditionLabel = (c) => CONDITIONS[c] ?? c ?? "";

export const STATUS = { queued: "대기", running: "분석 중", done: "완료", failed: "실패" };

export const METRICS = {
  peak_cpm: { label: "Peak (최고 분당 클릭)", unit: "회" },
  auc10: { label: "초기 10분 AUC", unit: "회" },
  auc30: { label: "30분 누적 클릭", unit: "회" },
  onset_min: { label: "반응 시작", unit: "분" },
  peak_min: { label: "최고점 도달", unit: "분" },
};

/** 시간대 포함 ISO 문자열 → 한국 시각 "2026-10-28 09:00" */
export function kst(iso) {
  if (!iso) return "—";
  const d = new Date(iso);
  if (Number.isNaN(d.getTime())) return "—";
  const p = new Intl.DateTimeFormat("ko-KR", {
    timeZone: "Asia/Seoul", year: "numeric", month: "2-digit", day: "2-digit", hour: "2-digit", minute: "2-digit",
    hour12: false,
  }).formatToParts(d);
  const g = (t) => p.find((x) => x.type === t)?.value ?? "";
  return `${g("year")}-${g("month")}-${g("day")} ${g("hour")}:${g("minute")}`;
}

/** 급이 기준 초 → "급이 후 3분 20초" / "급이 전 5분" */
export function feedClock(tSec) {
  if (tSec === null || tSec === undefined) return "—";
  const a = Math.abs(tSec);
  const m = Math.floor(a / 60);
  const s = Math.floor(a % 60);
  const txt = s ? `${m}분 ${s}초` : `${m}분`;
  return tSec < 0 ? `급이 전 ${txt}` : `급이 후 ${txt}`;
}

export function pct(v) {
  if (v === null || v === undefined) return "—";
  return `${v > 0 ? "+" : ""}${Number(v).toFixed(1)}%`;
}

export const num = (v, d = 0) => (v === null || v === undefined ? "—" : Number(v).toFixed(d));
export const speedLabel = (s) => (!s ? "최대 속도" : `${s}배속`);
