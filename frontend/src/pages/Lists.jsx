import { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { ackAlert, getAlerts, getAnalyses, getTanks } from "../api.js";
import { Card, ErrorBox, GradeBadge } from "../components/Bits.jsx";
import { STATUS, conditionLabel, kst, num, speedLabel } from "../format.js";

function useLoad(fn, deps = []) {
  const [data, setData] = useState(null);
  const [err, setErr] = useState(null);
  const reload = () => fn().then(setData).catch((e) => setErr(e.message));
  useEffect(() => { reload(); }, deps); // eslint-disable-line react-hooks/exhaustive-deps
  return [data, err, reload];
}

function AnalysesTable({ rows }) {
  if (rows === null) return <p className="muted">불러오는 중…</p>;
  if (!rows.length) return <p className="muted">아직 분석이 없습니다. <Link to="/analyze">분석하기</Link></p>;
  return (
    <table className="table">
      <thead>
        <tr><th>#</th><th>요청 시각</th><th>수조</th><th>녹음</th><th>배속</th><th>상태</th><th>판정</th><th>Peak</th><th>AUC10</th><th /></tr>
      </thead>
      <tbody>
        {rows.map((a) => (
          <tr key={a.id}>
            <td>{a.id}</td>
            <td>{kst(a.created_at)}</td>
            <td>{a.tank_id}</td>
            <td className="ellipsis" title={a.filename}>{a.filename}</td>
            <td>{speedLabel(a.speed)}</td>
            <td>{STATUS[a.status] ?? a.status}</td>
            <td>{a.status === "done" ? (a.max_grade ? <GradeBadge grade={a.max_grade} /> : "기준 없음") : "—"}</td>
            <td>{a.peak_cpm ?? "—"}</td>
            <td>{a.auc10 ?? "—"}</td>
            <td><Link to={`/analyses/${a.id}`}>보기</Link></td>
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
      <div className="page-h"><h1>분석 이력</h1></div>
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
        <div><h1>알림 내역</h1><p className="muted">섭식 반응이 정상 기준을 벗어나 등급이 올라간 기록입니다. 원인은 현장에서 확인합니다.</p></div>
      </div>
      <ErrorBox message={err} />
      <Card>
        {rows === null && !err ? <p className="muted">불러오는 중…</p> : !rows?.length ? <p className="muted">알림이 없습니다.</p> : (
          <table className="table">
            <thead><tr><th>시각</th><th>수조</th><th>등급</th><th>발생 시점</th><th>이상 점수</th><th>분석</th><th>확인</th></tr></thead>
            <tbody>
              {rows.map((x) => (
                <tr key={x.id} className={x.acknowledged ? "dim" : ""}>
                  <td>{kst(x.created_at)}</td>
                  <td>{x.tank_id}</td>
                  <td><GradeBadge grade={x.level} /></td>
                  <td>급이 후 {x.minute + 1}분</td>
                  <td>{num(x.score, 1)}</td>
                  <td><Link to={`/analyses/${x.analysis_id}`}>#{x.analysis_id}</Link></td>
                  <td>{x.acknowledged ? "확인함" : (
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

export function Dashboard() {
  const [tanks, e1] = useLoad(getTanks);
  const [analyses, e2] = useLoad(() => getAnalyses(50));
  const [alerts, e3] = useLoad(() => getAlerts(false));
  const latest = {};
  for (const a of analyses ?? []) if (a.status === "done" && !latest[a.tank_id]) latest[a.tank_id] = a;
  return (
    <div className="page">
      <div className="page-h">
        <div><h1>대시보드</h1><p className="muted">수조별 최근 급이 반응과 확인하지 않은 알림</p></div>
        <Link className="btn primary" to="/analyze">분석하기</Link>
      </div>
      <ErrorBox message={e1 || e2 || e3} />
      <div className="tanks">
        {(tanks ?? []).map((t) => {
          const a = latest[t.id];
          return (
            <Link key={t.id} to={a ? `/analyses/${a.id}` : "/analyze"} className="tank">
              <div className="row between"><b>{t.name}</b>{a?.max_grade ? <GradeBadge grade={a.max_grade} /> : <span className="muted small">기록 없음</span>}</div>
              <div className="muted small">{conditionLabel(t.noise_condition)} · 정상 기준 {t.has_baseline ? "있음" : "없음"}</div>
              <div className="small">{a ? <>최근 {kst(a.created_at)} · Peak {a.peak_cpm ?? "—"}</> : " "}</div>
            </Link>
          );
        })}
      </div>
      <div className="grid2">
        <Card title={`확인하지 않은 알림 ${alerts?.length ?? 0}건`} right={<Link to="/alerts">전체</Link>}>
          {!alerts?.length ? <p className="muted">없습니다.</p> : (
            <ul className="list">
              {alerts.slice(0, 6).map((x) => (
                <li key={x.id}>
                  <GradeBadge grade={x.level} /> 수조 {x.tank_id} · 급이 후 {x.minute + 1}분 · 점수 {num(x.score, 1)}
                  {" "}<Link to={`/analyses/${x.analysis_id}`}>보기</Link>
                </li>
              ))}
            </ul>
          )}
        </Card>
        <Card title="최근 분석" right={<Link to="/history">전체</Link>}>
          <AnalysesTable rows={(analyses ?? []).slice(0, 6)} />
        </Card>
      </div>
    </div>
  );
}
