import { CartesianGrid, Line, LineChart, ReferenceLine, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts";
import { METRICS, gradeLabel, gradeTone, num, pct } from "../format.js";

export function GradeBadge({ grade, big }) {
  return <span className={`badge ${gradeTone(grade)}${big ? " big" : ""}`}>{gradeLabel(grade)}</span>;
}

export function Card({ title, right, children, className = "" }) {
  return (
    <section className={`card ${className}`}>
      {(title || right) && <header className="card-h"><h3>{title}</h3>{right}</header>}
      {children}
    </section>
  );
}

export function Metric({ label, value, unit, sub, tone }) {
  return (
    <div className={`metric ${tone ?? ""}`}>
      <div className="metric-label">{label}</div>
      <div className="metric-value">{value}<small>{unit}</small></div>
      {sub && <div className="metric-sub">{sub}</div>}
    </div>
  );
}

export function ErrorBox({ message }) {
  return message ? <div className="errorbox" role="alert">{message}</div> : null;
}

/** 분석 진행 막대: 급이 전 10분 + 급이 후 30분 */
export function Progress({ tSec, pre = 10, post = 30 }) {
  const ratio = tSec === null ? 0 : Math.min(1, Math.max(0, (tSec / 60 + pre) / (pre + post)));
  return (
    <div className="progress" aria-label="분석 진행">
      <div className="progress-fill" style={{ width: `${ratio * 100}%` }} />
      <div className="progress-feed" style={{ left: `${(pre / (pre + post)) * 100}%` }} />
    </div>
  );
}

/** 경보·주의 배너 */
export function AlertBanner({ alerts }) {
  if (!alerts?.length) return null;
  const top = alerts.some((a) => a.level === "alert") ? alerts.find((a) => a.level === "alert") : alerts[0];
  const danger = top.level === "alert";
  return (
    <div className={`banner ${danger ? "danger" : "warn"}`} role="alert">
      <strong>{danger ? "섭식 활동 저하 경보" : "섭식 활동 주의"}</strong>
      <span>급이 후 {top.minute + 1}분 시점에 정상 기준을 벗어났습니다 (이상 점수 {num(top.score, 1)}).</span>
      <span className="banner-sub">원인은 단정하지 않습니다. 다음 급이 전 현장 점검을 권합니다.</span>
    </div>
  );
}

/**
 * 지표별 정상 기준 vs 현재. "±" 는 정상 4일 동안 그 지표가 날마다 달랐던 정도(설명용, 점수 계산에는 안 씀).
 * onsetFloor: 반응 시작은 점수 계산 때 이만큼(분)은 원래 흔들린다고 본다.
 */
export function ComparisonTable({ rows, onsetFloor }) {
  if (!rows?.length) return <p className="muted">정상 기준이 없어 비교하지 않았습니다.</p>;
  return (
    <table className="table compact">
      <thead><tr><th>지표</th><th>정상 4일 평균 ± 날짜별 차이</th><th>현재</th><th>변화율</th></tr></thead>
      <tbody>
        {rows.map((r) => {
          const m = METRICS[r.metric] ?? { label: r.metric, unit: "" };
          const worse = r.metric === "onset_min" || r.metric === "peak_min" ? r.change_pct > 0 : r.change_pct < 0;
          const floorNote = r.metric === "onset_min" && onsetFloor && (r.normal_sd ?? 0) < onsetFloor;
          return (
            <tr key={r.metric}>
              <td>{m.label}</td>
              <td>
                {num(r.normal_mean, 1)}{m.unit} <span className="muted">± {num(r.normal_sd, 1)}</span>
                {floorNote && <div className="muted small">점수 계산엔 최소 ±{onsetFloor}분 차이로 봄</div>}
              </td>
              <td><b>{r.current ?? "—"}</b>{m.unit}</td>
              <td className={r.change_pct === null ? "" : worse && Math.abs(r.change_pct) >= 20 ? "neg" : ""}>
                {pct(r.change_pct)}
              </td>
            </tr>
          );
        })}
      </tbody>
    </table>
  );
}

/** AI 인사이트 */
export function InsightCard({ insight, pending, waiting }) {
  const c = insight?.content;
  const src = insight?.source === "gemini" ? `Gemini (${insight.model})` : "템플릿 문장";
  return (
    <Card title="AI 인사이트" right={insight && <span className="chip">{src}</span>} className="insight">
      {pending && <p className="pulse">AI 가 이번 급이 결과를 해석하는 중입니다…</p>}
      {!pending && !c && <p className="muted">{waiting ? "급이 후 30분 분석이 끝나면 표시됩니다." : "인사이트가 없습니다."}</p>}
      {c && (
        <>
          <p className="insight-sum">{c.summary}</p>
          <ul>{c.bullets?.map((b) => <li key={b}>{b}</li>)}</ul>
          <p className="insight-rec">→ {c.recommendation}</p>
          <p className="muted small">수치만 AI 에 보내며, 원인을 단정하는 표현과 근거 없는 숫자는 자동으로 걸러냅니다.</p>
        </>
      )}
    </Card>
  );
}

/** 급이 후 매 분 이상 점수와 주의·경보 기준선 */
export function ScoreChart({ scores, thresholds }) {
  const data = scores.map((s) => ({ x: s.minute + 1, score: s.score }));
  return (
    <ResponsiveContainer width="100%" height={150}>
      <LineChart data={data} margin={{ top: 8, right: 36, left: 0, bottom: 0 }}>
        <CartesianGrid stroke="#eaeef2" vertical={false} />
        <XAxis dataKey="x" type="number" domain={[0, 30]} ticks={[0, 5, 10, 15, 20, 25, 30]} tick={{ fontSize: 11 }} />
        <YAxis width={36} tick={{ fontSize: 11 }} domain={[0, (max) => Math.max(3, Math.ceil(max + 0.5))]} />
        <Tooltip formatter={(v) => [Number(v).toFixed(2), "이상 점수"]} labelFormatter={(x) => `급이 후 ${x}분`} />
        <ReferenceLine y={thresholds?.alert ?? 2} stroke="#d1242f" strokeDasharray="4 3"
                       label={{ value: "경보", position: "right", fontSize: 11, fill: "#d1242f" }} />
        <ReferenceLine y={thresholds?.watch ?? 1.25} stroke="#bf8700" strokeDasharray="4 3"
                       label={{ value: "주의", position: "right", fontSize: 11, fill: "#bf8700" }} />
        <Line dataKey="score" stroke="#cf222e" strokeWidth={2} dot={false} isAnimationActive={false} />
      </LineChart>
    </ResponsiveContainer>
  );
}
