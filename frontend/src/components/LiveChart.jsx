import { useEffect, useRef } from "react";
import {
  Area, CartesianGrid, ComposedChart, Line, ReferenceDot, ReferenceLine, ResponsiveContainer, Tooltip, XAxis, YAxis,
} from "recharts";
import { chartRows } from "../stream.js";
import { COLOR } from "../theme.js";

// 차트 그림 영역과 아래 클릭 줄의 가로 위치를 맞추기 위한 여백(px)
const PAD_L = 48;
const PAD_R = 16;
const RECENT_SEC = 60;   // 클릭 줄에서 진하게 보일 최근 구간(녹음 시간)

function niceMax(rows) {
  let m = 20;
  for (const r of rows) m = Math.max(m, r.cpm ?? 0, r.band?.[1] ?? 0);
  return Math.ceil((m * 1.15) / 35) * 35;
}

function ChartTooltip({ active, payload }) {
  if (!active || !payload?.length) return null;
  const r = payload[0].payload;
  return (
    <div className="tip">
      <b>{r.minute < 0 ? `급이 전 ${-r.minute}분` : `급이 후 ${r.minute}–${r.minute + 1}분`}</b>
      <div>이번 급이: {r.cpm ?? "—"} 회/분</div>
      {r.band && <div>정상 범위: {r.band[0].toFixed(0)}–{r.band[1].toFixed(0)} (평균 {r.mu.toFixed(0)})</div>}
    </div>
  );
}

/** 카드 머리에 두는 범례(각 견본이 곧 그 표시) */
export function ChartLegend() {
  return (
    <div className="legend">
      <span><i className="sw line" />이번 급이</span>
      <span><i className="sw band" />정상 범위 (±1σ)</span>
      <span><i className="sw dash" />정상 평균</span>
    </div>
  );
}

/** G(t): 급이 기준 분당 클릭 수 + 정상 범위(μ±σ) + 경보 표시 + 현재 위치 + 아래 클릭 줄 */
export function LiveChart({ state, height = 340 }) {
  const rows = chartRows(state);
  const pre = state.meta?.pre_min ?? 10;
  const post = state.meta?.post_min ?? 30;
  const nowMin = state.tSec === null ? null : Math.min(state.tSec / 60, post);
  const yMax = niceMax(rows);
  const yTicks = Array.from({ length: yMax / 35 + 1 }, (_, i) => i * 35);
  const firstAlert = state.alerts[0];
  const alertColor = firstAlert?.level === "alert" ? COLOR.neg : COLOR.warn;
  return (
    <div className="chart">
      <ResponsiveContainer width="100%" height={height}>
        <ComposedChart data={rows} margin={{ top: 22, right: PAD_R, left: 0, bottom: 2 }}>
          <CartesianGrid stroke={COLOR.grid} vertical={false} />
          <XAxis dataKey="x" type="number" domain={[-pre, post]} ticks={[-10, -5, 0, 5, 10, 15, 20, 25, 30]}
                 tick={{ fontSize: 12, fill: COLOR.muted }} axisLine={{ stroke: COLOR.axis }} tickLine={false} />
          <YAxis width={PAD_L} domain={[0, yMax]} ticks={yTicks} tick={{ fontSize: 12, fill: COLOR.muted }}
                 axisLine={false} tickLine={false} />
          <Tooltip content={<ChartTooltip />} />
          <Area dataKey="band" stroke="none" fill={COLOR.band} fillOpacity={1} isAnimationActive={false} connectNulls />
          <Line dataKey="mu" stroke={COLOR.mean} strokeDasharray="4 3" dot={false} strokeWidth={1.5} isAnimationActive={false} />
          <Line dataKey="cpm" stroke={COLOR.hue} strokeWidth={2.5} dot={false} isAnimationActive={false} connectNulls={false} />
          <ReferenceLine x={0} stroke={COLOR.text} strokeWidth={1}
                         label={{ value: "급이", position: "top", fontSize: 12, fill: COLOR.muted, offset: 8 }} />
          {nowMin !== null && state.status !== "done" && <ReferenceLine x={nowMin} stroke={COLOR.axis} strokeDasharray="2 4" />}
          {firstAlert && (
            <ReferenceLine x={firstAlert.minute + 1} stroke={alertColor} strokeWidth={1.5}
                           label={{ value: `${firstAlert.level === "alert" ? "경보" : "주의"} · 급이 후 ${firstAlert.minute + 1}분`,
                                    position: "insideTopLeft", fontSize: 12, fontWeight: 700, fill: alertColor, dy: -20, dx: 4 }} />
          )}
          {state.alerts.map((a) => {
            const p = state.minutes[a.minute];
            return p ? (
              <ReferenceDot key={`${a.minute}-${a.level}`} x={a.minute + 0.5} y={p.cpm} r={6}
                            fill={a.level === "alert" ? COLOR.neg : COLOR.warn} stroke={COLOR.surface} strokeWidth={2} />
            ) : null;
          })}
        </ComposedChart>
      </ResponsiveContainer>
      <ClickStrip clicks={state.clicks} pre={pre} post={post} nowMin={nowMin} alertMin={firstAlert ? firstAlert.minute + 1 : null} />
    </div>
  );
}

/** 하이드로폰 클릭 줄: AI 가 확정한 클릭 하나 = 세로 1px. 최근 1분은 진하게. */
function ClickStrip({ clicks, pre, post, nowMin, alertMin }) {
  const ref = useRef(null);
  useEffect(() => {
    const c = ref.current;
    if (!c) return undefined;
    const draw = () => {
      const w = c.clientWidth;
      const h = c.clientHeight;
      const dpr = window.devicePixelRatio || 1;
      c.width = w * dpr;
      c.height = h * dpr;
      const g = c.getContext("2d");
      g.scale(dpr, dpr);
      g.clearRect(0, 0, w, h);
      const x0 = PAD_L;
      const span = w - PAD_L - PAD_R;
      const X = (sec) => x0 + ((sec / 60 + pre) / (pre + post)) * span;
      g.fillStyle = "#eef4f2";
      g.fillRect(x0, 0, span, h);
      const now = nowMin === null ? null : nowMin * 60;
      for (const t of clicks) {
        const recent = now !== null && now - t < RECENT_SEC;
        g.fillStyle = recent ? COLOR.hue : "rgba(15,31,30,0.62)";
        g.fillRect(Math.round(X(t)), 3, recent ? 2 : 1, h - 6);
      }
      g.fillStyle = COLOR.text;
      g.fillRect(Math.round(X(0)), 0, 1, h);
      if (alertMin !== null) { g.fillStyle = COLOR.neg; g.fillRect(Math.round(X(alertMin * 60)), 0, 1, h); }
      if (now !== null) { g.fillStyle = COLOR.axis; g.fillRect(Math.round(X(now)), 0, 1, h); }
    };
    draw();
    const ro = new ResizeObserver(draw);
    ro.observe(c);
    return () => ro.disconnect();
  }, [clicks, pre, post, nowMin, alertMin]);
  return (
    <div className="strip">
      <span className="strip-label">하이드로폰 클릭 {clicks.length.toLocaleString()}개 · 한 줄이 AI 가 확정한 클릭 하나</span>
      <canvas ref={ref} className="strip-canvas" aria-label={`검출된 클릭 ${clicks.length}개`} />
    </div>
  );
}
