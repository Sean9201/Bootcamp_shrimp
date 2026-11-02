import { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { ackAlert, getAlerts, getAnalyses } from "../api.js";
import { Card, ErrorBox, GradeBadge } from "../components/Bits.jsx";
import { TankPlan, useTankStates } from "../components/TankPlan.jsx";
import { STATUS, kst, num, speedLabel } from "../format.js";

function useLoad(fn, deps = []) {
  const [data, setData] = useState(null);
  const [err, setErr] = useState(null);
  const reload = () => fn().then(setData).catch((e) => setErr(e.message));
  useEffect(() => { reload(); }, deps); // eslint-disable-line react-hooks/exhaustive-deps
  return [data, err, reload];
}

/** 분석 목록 표. compact: 수조 현황의 반폭 칸용(녹음·배속·상태 열 생략) */
function AnalysesTable({ rows, compact = false }) {
  if (rows === null) return <p className="muted">불러오는 중…</p>;
  if (!rows.length) return <p className="muted">아직 분석이 없습니다. <Link to="/analyze">급이 분석 시작</Link></p>;
  return (
    <table className="table">
      <thead>
        <tr><th className="n">#</th><th>요청 시각</th><th>수조</th>{!compact && <><th>녹음</th><th>배속</th><th>상태</th></>}<th>판정</th>
          <th className="n">Peak</th><th className="n">첫 10분</th><th /></tr>
      </thead>
      <tbody>
        {rows.map((a) => (
          <tr key={a.id}>
            <td className="n">{a.id}</td>
            <td>{kst(a.created_at)}</td>
            <td><b>{a.tank_id}</b></td>
            {!compact && <>
              <td className="ellipsis" title={a.filename}>{a.filename}</td>
              <td>{speedLabel(a.speed)}</td>
              <td>{STATUS[a.status] ?? a.status}</td>
            </>}
            <td>{a.status === "done" ? (a.max_grade ? <GradeBadge grade={a.max_grade} /> : <span className="muted">기준 없음</span>) : "—"}</td>
            <td className="n">{a.peak_cpm ?? "—"}</td>
            <td className="n">{a.auc10 ?? "—"}</td>
            <td className="n"><Link to={`/analyses/${a.id}`}>보기</Link></td>
          </tr>
        ))}
      </tbody>
    </table>
  );
}

export function History() {
  const [rows, err] = useLoad(() => getAnalyses(200));
  return (
    <div className="page">
      <div className="page-h"><div><h1>분석 이력</h1><p>수조별 급이 분석 기록. 판정은 급이 후 30분 확정 기준입니다.</p></div>
        <Link className="btn primary" to="/analyze">급이 분석 시작</Link></div>
      <ErrorBox message={err} />
      <Card><AnalysesTable rows={rows} /></Card>
    </div>
  );
}

export function Alerts({ onChange }) {
  const [rows, err, reload] = useLoad(() => getAlerts());
  const [busy, setBusy] = useState(null);
  async function ack(id) {
    setBusy(id);
    try { await ackAlert(id); await reload(); onChange?.(); } finally { setBusy(null); }
  }
  return (
    <div className="page">
      <div className="page-h">
        <div><h1>점검 알림</h1><p>섭식 반응이 정상 기준을 벗어나 등급이 올라간 기록입니다. 원인은 현장에서 확인합니다.</p></div>
      </div>
      <ErrorBox message={err} />
      <Card>
        {rows === null && !err ? <p className="muted">불러오는 중…</p> : !rows?.length ? <p className="muted">알림이 없습니다.</p> : (
          <table className="table">
            <thead><tr><th>시각</th><th>수조</th><th>등급</th><th>발생 시점</th><th className="n">이상 점수</th><th>분석</th><th className="n">확인</th></tr></thead>
            <tbody>
              {rows.map((x) => (
                <tr key={x.id} className={x.acknowledged ? "dim" : ""}>
                  <td>{kst(x.created_at)}</td>
                  <td><b>{x.tank_id}</b></td>
                  <td><GradeBadge grade={x.level} /></td>
                  <td>급이 후 {x.minute + 1}분</td>
                  <td className="n">{num(x.score, 1)}</td>
                  <td><Link to={`/analyses/${x.analysis_id}`}>#{x.analysis_id}</Link></td>
                  <td className="n">{x.acknowledged ? "확인함" : (
                    <button className="btn small" onClick={() => ack(x.id)} disabled={busy === x.id}>확인</button>
                  )}</td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </Card>
    </div>
  );
}

/** 수조 현황: 양식장 평면도 + 확인하지 않은 알림 + 최근 분석 */
export function Dashboard() {
  const plan = useTankStates();
  const [analyses, e2] = useLoad(() => getAnalyses(50));
  const [alerts, e3] = useLoad(() => getAlerts(false));
  return (
    <div className="page">
      <div className="page-h">
        <div><h1>수조 현황</h1><p>수조마다 가장 최근 급이의 분당 클릭 수와 판정입니다. 수조를 누르면 그 급이 분석이 열립니다.</p></div>
        <Link className="btn primary" to="/analyze">급이 분석 시작</Link>
      </div>
      <ErrorBox message={plan.error || e2 || e3} />
      <TankPlan tanks={plan.tanks} latest={plan.latest} />
      <div className="grid2">
        <Card title={`확인하지 않은 알림 ${alerts?.length ?? 0}건`} right={<Link to="/alerts">전체 보기</Link>}>
          {alerts === null ? <p className="muted">불러오는 중…</p> : !alerts.length ? <p className="muted">없습니다.</p> : (
            <ul className="list">
              {alerts.slice(0, 6).map((x) => (
                <li key={x.id}>
                  <GradeBadge grade={x.level} /><b>{x.tank_id}</b>급이 후 {x.minute + 1}분 · 점수 {num(x.score, 1)}
                  <Link to={`/analyses/${x.analysis_id}`}>보기</Link>
                </li>
              ))}
            </ul>
          )}
        </Card>
        <Card title="최근 분석" right={<Link to="/history">전체 보기</Link>}>
          <AnalysesTable rows={analyses === null ? null : analyses.slice(0, 6)} compact />
        </Card>
      </div>
    </div>
  );
}
