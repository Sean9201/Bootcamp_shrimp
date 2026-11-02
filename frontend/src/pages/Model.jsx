import { useEffect, useState } from "react";
import { CartesianGrid, Legend, Line, LineChart, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts";
import { getModelReport } from "../api.js";
import { Card, ErrorBox } from "../components/Bits.jsx";
import { conditionLabel } from "../format.js";

const DET = { baseline: "신호처리 (A 로 기준값)", baseline_day1: "신호처리 (1일차로 기준값)", cnn: "AI: 후보 + CNN" };
const GROUP = { A_val: "소음 차단 · A 4일차", B_test_noise: "운영 소음 · B 1–4일차", B_day2_4: "운영 소음 · B 2–4일차 (공정 비교)" };
const VARIANT = { peak_drop: "Peak 감소 (×)", delay_min: "반응 지연 (분)", early_decay_tau: "조기 감쇠 (τ, 분)" };
const f = (v, d = 3) => (v === null || v === undefined ? "—" : Number(v).toFixed(d));

export default function Model() {
  const [r, setR] = useState(null);
  const [err, setErr] = useState(null);
  useEffect(() => { getModelReport().then(setR).catch((e) => setErr(e.message)); }, []);
  if (err) return <div className="page"><h1>모델 성능</h1><ErrorBox message={err} /></div>;
  if (!r) return <div className="page"><h1>모델 성능</h1><p className="muted">불러오는 중…</p></div>;
  const b = r.model_b;
  return (
    <div className="page">
      <div className="page-h">
        <div>
          <h1>모델 성능</h1>
          <p className="muted">{r.note} · 평가 {r.created_at}</p>
        </div>
      </div>

      <Card title="모델 A — 클릭 검출" right={<span className="muted small">정답과 ±5 ms 1:1 매칭</span>}>
        <table className="table">
          <thead><tr><th>조건</th><th>방식</th><th>Precision</th><th>Recall</th><th>F1</th><th>분당 클릭 수 오차</th></tr></thead>
          <tbody>
            {Object.entries(r.model_a).flatMap(([g, rows]) => Object.entries(rows).map(([d, m], i) => (
              <tr key={g + d} className={d === "cnn" ? "hl" : ""}>
                <td>{i === 0 ? GROUP[g] ?? g : ""}</td><td>{DET[d] ?? d}</td>
                <td>{f(m.precision)}</td><td>{f(m.recall)}</td><td><b>{f(m.f1)}</b></td><td>{f(m.cpm_mae, 2)}</td>
              </tr>
            )))}
          </tbody>
        </table>
        <p className="small">
          AI 는 조용한 A 수조로만 학습했고 운영 소음(B)은 학습하지 않았습니다. 공정 비교(B 2–4일차)에서 분당 클릭 수 오차
          {" "}<b>{r.mae_reduction_pct?.B_day2_4_vs_baseline_day1}% 감소</b> (목표 20%). 처리 속도 약 {Math.round(r.speed_x ?? 0)}배속.
        </p>
      </Card>

      {r.training?.history && (
        <Card title="CNN 학습 기록" right={<span className="muted small">학습 패치 {r.training.n_train_patches?.toLocaleString()}개</span>}>
          <ResponsiveContainer width="100%" height={220}>
            <LineChart data={r.training.history} margin={{ top: 8, right: 24, left: 0, bottom: 0 }}>
              <CartesianGrid stroke="#eaeef2" />
              <XAxis dataKey="epoch" tick={{ fontSize: 12 }} />
              <YAxis yAxisId="l" tick={{ fontSize: 12 }} width={44} />
              <YAxis yAxisId="r" orientation="right" domain={[0.9, 1]} tick={{ fontSize: 12 }} width={44} />
              <Tooltip />
              <Legend />
              <Line yAxisId="l" dataKey="train_loss" name="학습 손실" stroke="#8250df" dot />
              <Line yAxisId="l" dataKey="val_loss" name="검증 손실" stroke="#bf8700" dot />
              <Line yAxisId="r" dataKey="val_f1" name="검증 F1" stroke="#1a7f37" strokeWidth={2} dot />
            </LineChart>
          </ResponsiveContainer>
        </Card>
      )}

      <div className="grid2">
        <Card title="모델 B — 정상 세션 오경보">
          <div className="metrics two">
            <div className="metric"><div className="metric-label">경보 오경보율</div><div className="metric-value">{(b.false_alarm_rate * 100).toFixed(0)}<small>%</small></div><div className="metric-sub">목표 10% 이하 · {b.loo_sessions}개 세션</div></div>
            <div className="metric"><div className="metric-label">'주의' 이상 비율</div><div className="metric-value">{(b.watch_rate * 100).toFixed(0)}<small>%</small></div><div className="metric-sub">하루씩 빼고 기준을 만든 뒤 확인</div></div>
          </div>
        </Card>
        <Card title="모델 B — 합성 이상 탐지율">
          <table className="table">
            <thead><tr><th>변형</th><th>강도</th><th>경보</th><th>주의 이상</th><th>첫 경보</th></tr></thead>
            <tbody>
              {b.synthetic_detection.map((x) => (
                <tr key={x.kind + x.level}>
                  <td>{VARIANT[x.kind] ?? x.kind}</td><td>{x.level}</td>
                  <td>{(x.alert_rate * 100).toFixed(0)}%</td><td>{(x.watch_or_alert_rate * 100).toFixed(0)}%</td>
                  <td>{x.median_first_alert_min === null ? "—" : `${x.median_first_alert_min}분`}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </Card>
      </div>

      {r.conditions?.reproducibility && (
        <Card title="재현성 — 같은 수조 4일간 곡선">
          <table className="table">
            <thead><tr><th>수조</th><th>조건</th><th>곡선 형태 상관 (평균 / 최소)</th><th>Peak 변동계수</th><th>AUC10 변동계수</th></tr></thead>
            <tbody>
              {r.conditions.reproducibility.map((x) => (
                <tr key={x.tank}><td>{x.tank}</td><td>{conditionLabel(x.condition)}</td>
                  <td>{f(x.shape_corr_mean)} / {f(x.shape_corr_min)}</td><td>{f(x.peak_cv)}</td><td>{f(x.auc10_cv)}</td></tr>
              ))}
            </tbody>
          </table>
        </Card>
      )}
    </div>
  );
}
