import { useEffect, useState } from "react";
import { Link, NavLink, Route, Routes, useLocation } from "react-router-dom";
import { getAlerts, getHealth } from "./api.js";
import Analyze from "./pages/Analyze.jsx";
import AnalysisView from "./pages/AnalysisView.jsx";
import { Alerts, Dashboard, History } from "./pages/Lists.jsx";
import Model from "./pages/Model.jsx";

const MENU = [
  ["/", "수조 현황"],
  ["/analyze", "급이 분석"],
  ["/history", "분석 이력"],
  ["/alerts", "점검 알림"],
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

/** 제품 표식: 하이드로폰에서 소리가 퍼지는 모양 */
export function Mark({ size = 28 }) {
  return (
    <svg width={size} height={size} viewBox="0 0 26 26" aria-hidden="true">
      <circle cx="7" cy="13" r="3.2" fill="#0f6b78" />
      <path d="M12 7.5a8 8 0 0 1 0 11" fill="none" stroke="#0f6b78" strokeWidth="2" strokeLinecap="round" />
      <path d="M16.5 4a13 13 0 0 1 0 18" fill="none" stroke="#0f6b78" strokeWidth="2" strokeLinecap="round" opacity=".5" />
    </svg>
  );
}

function StatusDots({ health, down }) {
  if (down) return <span className="status"><i className="dot bad" /><span className="status-tip">서버 연결 안 됨</span></span>;
  const items = [
    [health?.ai?.classifier, "ok", "bad", "클릭 검출 모델", "검출 모델"],
    [health?.ai?.baselines?.length, "ok", "bad", `정상 기준 ${health?.ai?.baselines?.length ?? 0}개 수조`, `기준 ${health?.ai?.baselines?.length ?? 0}`],
    [health?.llm?.configured, "ok", "warn", `AI 인사이트 ${health?.llm?.configured ? "Gemini" : "템플릿"}`, health?.llm?.configured ? "Gemini" : "템플릿"],
  ];
  return (
    <span className="status" title={items.map((i) => i[3]).join(" · ")}>
      {items.map(([on, good, bad, label, short]) => (
        <span key={label} className="status-tip"><i className={`dot ${on ? good : bad}`} aria-hidden="true" /> {short}</span>
      ))}
    </span>
  );
}

export default function App() {
  const { health, unacked, down, refresh } = useStatus();
  const { pathname } = useLocation();
  return (
    <>
      <header className="top">
        <Link to="/" className="brand"><Mark />TickTechTok</Link>
        <span className="scope">실험 수조 6개</span>
        <nav className="menu" aria-label="메뉴">
          {MENU.map(([to, label]) => (
            <NavLink key={to} to={to} end={to === "/"}
                     className={({ isActive }) => (isActive || (to === "/analyze" && pathname.startsWith("/analyses")) ? "on" : "")}>
              {label}{to === "/alerts" && unacked > 0 && <span className="count">{unacked}</span>}
            </NavLink>
          ))}
        </nav>
        <StatusDots health={health} down={down} />
      </header>
      <main className="main">
        <Routes>
          <Route path="/" element={<Dashboard />} />
          <Route path="/analyze" element={<Analyze />} />
          <Route path="/analyses/:id" element={<AnalysisView />} />
          <Route path="/history" element={<History />} />
          <Route path="/alerts" element={<Alerts onChange={refresh} />} />
          <Route path="/model" element={<Model />} />
          <Route path="*" element={<div className="page"><h1>없는 화면입니다</h1><Link to="/">수조 현황으로</Link></div>} />
        </Routes>
      </main>
    </>
  );
}
