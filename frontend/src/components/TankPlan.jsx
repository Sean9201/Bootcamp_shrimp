import { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { getAnalyses, getAnalysis, getTanks } from "../api.js";
import { gradeLabel, pct } from "../format.js";
import { COLOR } from "../theme.js";

const HALLS = [
  { cond: "blocked", name: "소음 차단 동", sub: "펌프·에어레이션 정지" },
  { cond: "operating", name: "운영 소음 동", sub: "실제 운영 상태", gear: true },
];

/** 분석 상세 → 수조 칸에 필요한 값 */
export function tileFromDetail(d) {
  const cpm = Array(40).fill(null);
  for (const p of d.minutes ?? []) cpm[p.minute + 10] = p.cpm;
  const auc = (d.comparison ?? []).find((r) => r.metric === "auc10");
  return {
    analysisId: d.id, grade: d.max_grade, cpm, mu: d.baseline?.mu ?? null,
    auc10: d.metrics?.auc10 ?? null, auc10Pct: auc?.change_pct ?? null, live: false,
  };
}

/** 수조 목록 + 수조별 마지막 완료 분석(곡선 포함). */
export function useTankStates() {
  const [state, setState] = useState({ tanks: null, latest: {}, error: null });
  useEffect(() => {
    let alive = true;
    (async () => {
      try {
        const [tanks, analyses] = await Promise.all([getTanks(), getAnalyses(200)]);
        const last = {};
        for (const a of analyses) if (a.status === "done" && !last[a.tank_id]) last[a.tank_id] = a.id;
        const details = await Promise.all(Object.values(last).map((id) => getAnalysis(id).catch(() => null)));
        const latest = {};
        for (const d of details) if (d) latest[d.tank_id] = tileFromDetail(d);
        if (alive) setState({ tanks, latest, error: null });
      } catch (e) {
        if (alive) setState((s) => ({ ...s, error: e.message }));
      }
    })();
    return () => { alive = false; };
  }, []);
  return state;
}

function Mini({ cpm, mu, alert }) {
  const W = 200, H = 42;
  const x = (i) => 2 + (i / 39) * (W - 4);
  const y = (v) => 2 + (1 - Math.min(v, 140) / 140) * (H - 4);
  const path = (arr) => arr.map((v, i) => (v === null || v === undefined ? null : `${x(i)},${y(v)}`)).filter(Boolean).join(" ");
  return (
    <svg viewBox={`0 0 ${W} ${H}`} preserveAspectRatio="none" aria-hidden="true">
      {mu && <polyline points={path(mu)} fill="none" stroke={COLOR.mean} strokeWidth="1" strokeDasharray="3 2" vectorEffect="non-scaling-stroke" />}
      <line x1={x(10)} x2={x(10)} y1="0" y2={H} stroke={COLOR.axis} strokeWidth="1" opacity="0.6" vectorEffect="non-scaling-stroke" />
      {cpm && <polyline points={path(cpm)} fill="none" stroke={alert ? COLOR.neg : COLOR.hue} strokeWidth="1.75" vectorEffect="non-scaling-stroke" />}
    </svg>
  );
}

function Tile({ tank, t, selected, compact }) {
  const live = t?.live;
  const grade = t?.grade;
  const status = live ? { cls: "live", text: "분석 중" }
    : !t ? { cls: "none", text: "기록 없음" }
    : !grade ? { cls: "none", text: "기준 없음" }
    : { cls: grade, text: gradeLabel(grade) };
  const alert = grade === "alert";
  const to = t?.analysisId ? `/analyses/${t.analysisId}` : `/analyze?tank=${tank.id}`;
  return (
    <Link to={to} className={`tank${alert ? " alert" : ""}${selected ? " sel" : ""}`} aria-current={selected ? "page" : undefined}>
      <div className="code">{tank.id}</div>
      <div className={`st ${status.cls}`}>{status.text}</div>
      {t ? <Mini cpm={t.cpm} mu={t.mu} alert={alert} /> : <svg aria-hidden="true" />}
      {!compact && (
        <div className="meta">
          {t?.auc10 !== null && t?.auc10 !== undefined
            ? <><span>첫 10분 {t.auc10}회</span><span>정상 대비 {pct(t.auc10Pct)}</span></>
            : <span>{t ? "급이 후 10분 전" : tank.has_baseline ? "정상 기준 있음" : "정상 기준 없음"}</span>}
        </div>
      )}
    </Link>
  );
}

/** 양식장 평면도: 소음 차단 동 / 운영 소음 동, 수조마다 최근 급이 곡선과 판정. override 로 지금 분석 중인 수조를 덮어쓴다. */
export function TankPlan({ tanks, latest, selected, override, compact }) {
  if (!tanks) return <div className="plan"><div className="hall muted">수조를 불러오는 중…</div></div>;
  const data = override ? { ...latest, [override.tankId]: override } : latest;
  return (
    <section className={`plan${compact ? " compact" : ""}`} aria-label="양식장 평면도">
      {HALLS.map((h) => (
        <div key={h.cond} className="hall">
          <div className="hall-h">{h.name} <small>{h.sub}</small>
            {h.gear && <span className="gear"><i className="pump" /><i className="pump" /><i className="pump" /> 에어레이션 가동</span>}
          </div>
          <div className="tanks">
            {tanks.filter((t) => t.noise_condition === h.cond).map((t) => (
              <Tile key={t.id} tank={t} t={data[t.id]} selected={selected === t.id} compact={compact} />
            ))}
          </div>
        </div>
      ))}
    </section>
  );
}
