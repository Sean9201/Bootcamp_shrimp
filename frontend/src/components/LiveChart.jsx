import { useEffect, useRef } from "react";
import {
  Area, CartesianGrid, ComposedChart, Line, ReferenceDot, ReferenceLine, ResponsiveContainer, Tooltip, XAxis, YAxis,
} from "recharts";
import { chartRows } from "../stream.js";

// 차트 그림 영역과 아래 클릭 띠의 가로 위치를 맞추기 위한 여백(px)
const PAD_L = 48;
const PAD_R = 16;
const COLORS = { line: "#1f6feb", band: "#9ec5fe", mu: "#5b7fb9", alert: "#d1242f", watch: "#bf8700", now: "#8c959f" };

function niceMax(rows) {
  let m = 20;
  for (const r of rows) m = Math.max(m, r.cpm ?? 0, r.band?.[1] ?? 0);
  return Math.ceil((m * 1.15) / 20) * 20;
}

function ChartTooltip({ active, payload }) {
  if (!active || !payload?.length) return null;
  const r = payload[0].payload;
  return (
    <div className="tip">
      <b>{r.minute < 0 ? `급이 전 ${-r.minute}분` : `급이 후 ${r.minute}–${r.minute + 1}분`}</b>
      <div>현재: {r.cpm ?? "—"} 회/분</div>
      {r.band && <div>정상 범위: {r.band[0].toFixed(0)}–{r.band[1].toFixed(0)} (평균 {r.mu.toFixed(0)})</div>}
    </div>
  );
}

/** G(t): 급이 기준 분당 클릭 수 + 정상 범위(μ±σ) + 경보 표시 + 현재 위치 */
export function LiveChart({ state, height = 320 }) {
  const rows = chartRows(state);
  const pre = state.meta?.pre_min ?? 10;
  const post = state.meta?.post_min ?? 30;
  const nowMin = state.tSec === null ? null : Math.min(state.tSec / 60, post);
  const yMax = niceMax(rows);
  const firstAlert = state.alerts[0];
  return (
    <div className="chart">
      <ResponsiveContainer width="100%" height={height}>
        <ComposedChart data={rows} margin={{ top: 12, right: PAD_R, left: 0, bottom: 4 }}>
          <CartesianGrid stroke="#eaeef2" vertical={false} />
          <XAxis dataKey="x" type="number" domain={[-pre, post]} ticks={[-10, -5, 0, 5, 10, 15, 20, 25, 30]}
                 tickFormatter={(v) => `${v}`} tick={{ fontSize: 12 }} />
          <YAxis width={PAD_L} domain={[0, yMax]} tick={{ fontSize: 12 }}
                 label={{ value: "분당 클릭 수", angle: -90, position: "insideLeft", offset: 12, fontSize: 12 }} />
          <Tooltip content={<ChartTooltip />} />
          <Area dataKey="band" stroke="none" fill={COLORS.band} fillOpacity={0.45} isAnimationActive={false}
                name="정상 범위" connectNulls />
          <Line dataKey="mu" stroke={COLORS.mu} strokeDasharray="5 4" dot={false} strokeWidth={1.5}
                isAnimationActive={false} name="정상 평균" />
          <Line dataKey="cpm" stroke={COLORS.line} strokeWidth={2.6} dot={{ r: 2.5 }} isAnimationActive={false}
                connectNulls={false} name="현재" />
          <ReferenceLine x={0} stroke="#57606a" strokeDasharray="3 3"
                         label={{ value: "급이", position: "insideTopLeft", fontSize: 12, fill: "#57606a" }} />
          {nowMin !== null && state.status !== "done" && (
            <ReferenceLine x={nowMin} stroke={COLORS.now} strokeDasharray="2 4" />
          )}
          {state.alerts.map((a) => {
            const p = state.minutes[a.minute];
            return p ? (
              <ReferenceDot key={`${a.minute}-${a.level}`} x={a.minute + 0.5} y={p.cpm} r={7}
                            fill={a.level === "alert" ? COLORS.alert : COLORS.watch} stroke="#fff" strokeWidth={2} />
            ) : null;
          })}
          {firstAlert && (
            <ReferenceLine x={firstAlert.minute + 1} stroke={firstAlert.level === "alert" ? COLORS.alert : COLORS.watch}
                           strokeWidth={1.5}
                           label={{ value: firstAlert.level === "alert" ? "경보" : "주의", position: "top", fontSize: 12,
                                    fill: firstAlert.level === "alert" ? COLORS.alert : COLORS.watch }} />
          )}
        </ComposedChart>
      </ResponsiveContainer>
      <ClickStrip clicks={state.clicks} pre={pre} post={post} nowMin={nowMin} />
      <div className="legend">
        <span><i className="sw" style={{ background: COLORS.line }} />현재 측정 G(t)</span>
        <span><i className="sw dash" style={{ borderColor: COLORS.mu }} />정상 평균</span>
        <span><i className="sw" style={{ background: COLORS.band, opacity: 0.6 }} />정상 범위 (±1σ)</span>
        <span><i className="sw tick" />AI 가 검출한 클릭</span>
      </div>
    </div>
  );
}

/** 검출된 클릭을 시간축에 눈금으로 찍는다. 최근 클릭일수록 진하게. */
function ClickStrip({ clicks, pre, post, nowMin }) {
  const ref = useRef(null);
  useEffect(() => {
    const c = ref.current;
    if (!c) return;
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
      g.fillStyle = "#f6f8fa";
      g.fillRect(x0, 0, span, h);
      const now = nowMin === null ? null : nowMin * 60;
      for (const t of clicks) {
        const age = now === null ? 999 : now - t;
        g.fillStyle = age < 60 ? "#0a3069" : "rgba(31,111,235,0.45)";
        g.fillRect(Math.round(X(t)), age < 60 ? 2 : 8, 1, age < 60 ? h - 4 : h - 16);
      }
      if (now !== null) {
        g.fillStyle = "#8c959f";
        g.fillRect(Math.round(X(now)), 0, 1, h);
      }
    };
    draw();
    const ro = new ResizeObserver(draw);
    ro.observe(c);
    return () => ro.disconnect();
  }, [clicks, pre, post, nowMin]);
  return (
    <div className="strip">
      <span className="strip-label">클릭 검출</span>
      <canvas ref={ref} className="strip-canvas" aria-label={`검출된 클릭 ${clicks.length}개`} />
    </div>
  );
}
