// 분석 진행 이벤트(SSE) → 화면 상태. 이벤트 형식은 docs/interfaces.md 2·3절.
import { useEffect, useReducer } from "react";
import { eventsUrl } from "./api.js";
import { maxGrade } from "./format.js";

// 서버 재시작 후 snapshot 에는 기준값이 없으므로 백엔드 AnomalyConfig 기본값을 쓴다
const DEFAULT_THRESHOLDS = { watch: 1.25, alert: 2.0, onset_sd_floor_min: 0.7 };

export const initialState = {
  status: "connecting",   // connecting | running | finalizing | done | failed
  meta: null,
  minutes: {},            // minute → {cpm, mu, lo, hi}
  scores: [],
  alerts: [],
  clicks: [],             // 급이 기준 초
  tSec: null,             // 처리 위치(급이 기준 초)
  final: null,
  insight: null,
  insightPending: false,
  maxGrade: "normal",
  error: null,
};

/** 서버 재시작 등으로 이벤트 기록이 없을 때 받는 상세 응답 → 같은 화면 상태 */
function fromSnapshot(d) {
  const minutes = {};
  for (const p of d.minutes ?? []) minutes[p.minute] = p;
  const last = d.scores?.[d.scores.length - 1] ?? null;
  return {
    ...initialState,
    status: d.status === "failed" ? "failed" : "done",
    meta: {
      analysis_id: d.id, tank_id: d.tank_id, noise_condition: d.noise_condition, speed: d.speed,
      duration_sec: d.duration_sec, feeding_offset_sec: d.feeding_offset_sec, pre_min: 10, post_min: 30,
      thresholds: DEFAULT_THRESHOLDS, baseline: d.baseline, classifier: true,
    },
    minutes,
    scores: d.scores ?? [],
    alerts: d.alerts ?? [],
    tSec: (d.duration_sec ?? 0) - (d.feeding_offset_sec ?? 0),
    final: d.metrics ? { metrics: d.metrics, comparison: d.comparison, score: last, max_grade: d.max_grade } : null,
    insight: d.insight ? { content: d.insight, source: d.insight.source, model: d.insight.model } : null,
    maxGrade: d.max_grade ?? "normal",
    error: d.error,
  };
}

export function reduce(state, e) {
  switch (e.type) {
    case "meta": return { ...initialState, status: "running", meta: e };   // 재연결 시 처음부터 다시 받으므로 초기화
    case "progress": return { ...state, tSec: e.t_sec };
    case "clicks": return { ...state, clicks: state.clicks.concat(e.t) };
    case "minute": return { ...state, minutes: { ...state.minutes, [e.minute]: e } };
    case "score": return { ...state, scores: [...state.scores, e], maxGrade: maxGrade(state.maxGrade, e.grade) };
    case "alert": return { ...state, alerts: [...state.alerts, e] };
    case "final": return { ...state, final: e, status: "finalizing" };
    case "insight_pending": return { ...state, insightPending: true };
    case "insight": return { ...state, insight: e, insightPending: false };
    case "done": return { ...state, status: "done" };
    case "error": return { ...state, status: "failed", error: e.message, insightPending: false };
    case "snapshot": return fromSnapshot(e);
    default: return state;
  }
}

export const reduceAll = (state, events) => events.reduce(reduce, state);

const TERMINAL = new Set(["done", "error", "snapshot"]);
const FLUSH_MS = 80;   // 40배속이면 초당 수십 개 이벤트 → 모아서 한 번에 그린다

/** 분석 하나의 이벤트를 받아 상태로 만든다. 끝나면 연결을 닫는다(자동 재접속으로 다시 받지 않게). */
export function useAnalysisStream(id) {
  const [state, dispatch] = useReducer((s, evs) => (evs === null ? initialState : reduceAll(s, evs)), initialState);
  useEffect(() => {
    if (!id) return undefined;
    dispatch(null);
    let buf = [];
    let closed = false;
    const es = new EventSource(eventsUrl(id));
    const timer = setInterval(() => {
      if (buf.length) { dispatch(buf); buf = []; }
    }, FLUSH_MS);
    es.onmessage = (m) => {
      const e = JSON.parse(m.data);
      buf.push(e);
      if (TERMINAL.has(e.type)) { closed = true; es.close(); dispatch(buf); buf = []; }
    };
    es.onerror = () => {
      if (!closed) buf.push({ type: "connection_lost" });
    };
    return () => { closed = true; es.close(); clearInterval(timer); };
  }, [id]);
  return state;
}

const SIMILAR_PCT = 15;   // 정상 평균 대비 ±15% 안이면 "평소와 비슷"

/**
 * 판정 칸 제목 문장: 급이 후 지금까지(끝난 분) 누적 클릭을 같은 분들의 정상 평균 합과 비교.
 * 등급(점수)과는 별개인 설명 문장이다.
 */
export function feedingSummary(state) {
  const b = state.meta?.baseline;
  const pre = state.meta?.pre_min ?? 10;
  if (!b) return { text: "정상 기준이 없어 활동량만 기록합니다", sub: null, pct: null };
  let obs = 0;
  let exp = 0;
  let n = 0;
  for (const [k, p] of Object.entries(state.minutes)) {
    const m = Number(k);
    if (m < 0) continue;
    obs += p.cpm;
    exp += b.mu[m + pre];
    n += 1;
  }
  if (!n) return { text: "급이 전 배경 소리를 듣는 중입니다", sub: null, pct: null };
  const change = exp ? ((obs - exp) / exp) * 100 : 0;
  const r = Math.round(Math.abs(change));
  const done = state.status === "done" || state.status === "finalizing";
  const text = Math.abs(change) < SIMILAR_PCT ? `평소와 비슷하게 ${done ? "먹었습니다" : "먹고 있습니다"}`
    : change < 0 ? `평소보다 ${r}% 덜 ${done ? "먹었습니다" : "먹고 있습니다"}`
    : `평소보다 ${r}% 더 ${done ? "먹었습니다" : "먹고 있습니다"}`;
  return { text, sub: `급이 후 ${n}분 누적 ${obs.toLocaleString()}회 · 같은 시간 정상 평균 ${exp.toFixed(1)}회`, pct: change };
}

/** 차트용 행: 분 구간 가운데(x = 분 + 0.5)에 정상 범위·평균·현재 값 */
export function chartRows(state) {
  const pre = state.meta?.pre_min ?? 10;
  const post = state.meta?.post_min ?? 30;
  const b = state.meta?.baseline;
  const rows = [];
  for (let m = -pre; m < post; m++) {
    const i = m + pre;
    const p = state.minutes[m];
    rows.push({
      x: m + 0.5,
      minute: m,
      band: b ? [b.lo[i], b.hi[i]] : null,
      mu: b ? b.mu[i] : null,
      cpm: p ? p.cpm : null,
    });
  }
  return rows;
}
