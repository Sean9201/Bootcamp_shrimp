import { useEffect, useState } from "react";
import { Link, NavLink, Route, Routes } from "react-router-dom";
import { getAlerts, getHealth } from "./api.js";
import Analyze from "./pages/Analyze.jsx";
import AnalysisView from "./pages/AnalysisView.jsx";
import { Alerts, Dashboard, History } from "./pages/Lists.jsx";
import Model from "./pages/Model.jsx";

const NAV = [
  ["/", "대시보드"],
  ["/analyze", "분석하기"],
  ["/history", "분석 이력"],
  ["/alerts", "알림 내역"],
  ["/model", "모델 성능"],
];
const POLL_MS = 5000;

/** 서버 상태와 확인하지 않은 알림 수(5초마다 갱신) */
function useStatus() {
  const [health, setHealth] = useState(null);
  const [unacked, setUnacked] = useState(0);
  const [down, setDown] = useState(false);
  const refresh = () => {
    getHealth().then((h) => { setHealth(h); setDown(false); }).catch(() => setDown(true));
    getAlerts(false).then((a) => setUnacked(a.length)).catch(() => {});
  };
  useEffect(() => {
    refresh();
    const t = setInterval(refresh, POLL_MS);
    return () => clearInterval(t);
  }, []);
  return { health, unacked, down, refresh };
}

export default function App() {
  const { health, unacked, down, refresh } = useStatus();
  return (
    <div className="app">
      <aside className="side">
        <Link to="/" className="brand">ShrimpCare</Link>
        <p className="brand-sub">흰다리새우 섭식 활동 조기 경보</p>
        <nav>
          {NAV.map(([to, label]) => (
            <NavLink key={to} to={to} end={to === "/"} className={({ isActive }) => (isActive ? "on" : "")}>
              {label}{to === "/alerts" && unacked > 0 && <span className="count">{unacked}</span>}
            </NavLink>
          ))}
        </nav>
        <div className="side-foot">
          {down ? <span className="dot bad">서버 연결 안 됨</span> : (
            <>
              <span className={`dot ${health?.ai?.classifier ? "ok" : "bad"}`}>클릭 검출 모델</span>
              <span className={`dot ${health?.ai?.baselines?.length ? "ok" : "bad"}`}>정상 기준 {health?.ai?.baselines?.length ?? 0}개 수조</span>
              <span className={`dot ${health?.llm?.configured ? "ok" : "warn"}`}>AI 인사이트 {health?.llm?.configured ? "Gemini" : "템플릿"}</span>
            </>
          )}
        </div>
      </aside>
      <main className="main">
        <Routes>
          <Route path="/" element={<Dashboard />} />
          <Route path="/analyze" element={<Analyze />} />
          <Route path="/analyses/:id" element={<AnalysisView />} />
          <Route path="/history" element={<History />} />
          <Route path="/alerts" element={<Alerts onChange={refresh} />} />
          <Route path="/model" element={<Model />} />
          <Route path="*" element={<div className="page"><h1>없는 화면입니다</h1><Link to="/">대시보드로</Link></div>} />
        </Routes>
      </main>
    </div>
  );
}
