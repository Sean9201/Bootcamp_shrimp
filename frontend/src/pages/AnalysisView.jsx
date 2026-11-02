import { useEffect, useState } from "react";
import { Link, useParams } from "react-router-dom";
import { getAnalysis } from "../api.js";
import { AlertBanner, Card, ComparisonTable, ErrorBox, GradeBadge, InsightBody, Progress, ScoreChart } from "../components/Bits.jsx";
import { ChartLegend, LiveChart } from "../components/LiveChart.jsx";
import { TankPlan, useTankStates } from "../components/TankPlan.jsx";
import { conditionLabel, feedClock, kst, num, pct, speedLabel } from "../format.js";
import { feedingSummary, useAnalysisStream } from "../stream.js";

/** 지금까지 끝난 분으로 계산한 Peak·초기 10분 AUC (분석 중에도 갱신) */
export function liveMetrics(state) {
  let peak = null;
  let auc10 = 0;
  let n10 = 0;
  for (const [k, p] of Object.entries(state.minutes)) {
    const m = Number(k);
    if (m < 0) continue;
    peak = Math.max(peak ?? 0, p.cpm);
    if (m < 10) { auc10 += p.cpm; n10 += 1; }
  }
  const ref = state.meta?.baseline?.metrics ?? {};
  return { peak, auc10: n10 ? auc10 : null, n10, peakRef: ref.peak_cpm?.mean, aucRef: ref.auc10?.mean,
           onsetRef: ref.onset_min?.mean };
}

const change = (v, ref) => (v === null || !ref ? null : ((v - ref) / ref) * 100);

export default function AnalysisView() {
  const { id } = useParams();
  const st = useAnalysisStream(id);
  const plan = useTankStates();
  const [info, setInfo] = useState(null);
  const [err, setErr] = useState(null);
  const finished = st.status === "done";

  useEffect(() => {
    getAnalysis(id).then(setInfo).catch((e) => setErr(e.message));
  }, [id, finished]);

  const meta = st.meta;
  const tankId = meta?.tank_id ?? info?.tank_id;
  const lm = liveMetrics(st);
  const last = st.scores[st.scores.length - 1];
  const thr = meta?.thresholds ?? { watch: 1.25, alert: 2, onset_sd_floor_min: 0.7 };
  const hasBase = Boolean(meta?.baseline);
  const running = st.status === "running" || st.status === "connecting";
  const stage = st.final ? "급이 후 30분 확정" : last && last.minute >= 9 ? "10분 조기 판정 이후" : "잠정";
  const summary = feedingSummary(st);
  const onset = st.final?.metrics?.onset_min;

  // 평면도에서 지금 분석 중인 수조를 실시간 값으로 덮어쓴다
  const cpm = Array(40).fill(null);
  for (const [k, p] of Object.entries(st.minutes)) cpm[Number(k) + 10] = p.cpm;
  const override = tankId ? {
    tankId, analysisId: Number(id), live: running, grade: hasBase ? st.maxGrade : null, cpm,
    mu: meta?.baseline?.mu ?? null, auc10: lm.n10 === 10 ? lm.auc10 : null, auc10Pct: lm.n10 === 10 ? change(lm.auc10, lm.aucRef) : null,
  } : null;

  return (
    <div className="page">
      <TankPlan tanks={plan.tanks} latest={plan.latest} selected={tankId} override={override} compact />

      <ErrorBox message={err || st.error} />
      <AlertBanner alerts={st.alerts} />

      <div className="progress-row">
        <span className={`chip ${running ? "live" : ""}`}>
          {running ? "● 실시간 분석 중" : st.status === "finalizing" ? "결과 정리 중" : st.status === "failed" ? "실패" : "완료"}
        </span>
        <Progress tSec={st.tSec} pre={meta?.pre_min ?? 10} post={meta?.post_min ?? 30} />
        <span className="muted">{feedClock(st.tSec)} · 검출 클릭 {st.clicks.length.toLocaleString()}개</span>
      </div>

      <div className="detail">
        <div className="col">
          <Card className="chartbox" title={tankId ?? "—"} right={<ChartLegend />}>
            <p className="muted" style={{ margin: "-6px 0 0" }}>
              분당 클릭 수 · 급이 시각 = 0분 · {conditionLabel(meta?.noise_condition ?? info?.noise_condition)}
              {" · "}{info?.filename ?? ""} · {speedLabel(meta?.speed ?? info?.speed)}
              {info?.fed_at && <> · 급이 {kst(info.fed_at)}</>}
            </p>
            {!hasBase && meta && <p className="note">이 수조는 정상 기준이 없어 점수·경보 없이 활동 곡선만 표시합니다.</p>}
            <LiveChart state={st} />
          </Card>
          <Card title="주요 지표 비교">
            {st.final?.comparison ? <ComparisonTable rows={st.final.comparison} onsetFloor={thr.onset_sd_floor_min} />
              : <p className="muted">급이 후 30분 분석이 끝나면 표시됩니다.</p>}
          </Card>
        </div>

        <aside className="verdict" aria-label="판정">
          <div className="k">
            {hasBase ? <GradeBadge grade={st.maxGrade} big /> : <span className="badge muted big">기준 없음</span>}
            <span>{stage}{last ? ` · 이상 점수 ${num(last.score, 1)}` : ""}</span>
          </div>
          <h2>{summary.text}</h2>
          {summary.sub && <p>{summary.sub}</p>}
          <div className="nums">
            <div>첫 10분 누적
              <strong>{lm.auc10 ?? "—"}</strong>
              <em className={lm.n10 === 10 && change(lm.auc10, lm.aucRef) < -20 ? "neg" : ""}>
                {lm.n10 && lm.n10 < 10 ? `${lm.n10}분까지 · ` : ""}
                {lm.aucRef ? `정상 ${num(lm.aucRef, 1)}${lm.n10 === 10 ? ` · ${pct(change(lm.auc10, lm.aucRef))}` : ""}` : ""}
              </em></div>
            <div>Peak (회/분)
              <strong>{lm.peak ?? "—"}</strong>
              <em className={change(lm.peak, lm.peakRef) < -20 ? "neg" : ""}>
                {lm.peakRef ? `정상 ${num(lm.peakRef, 1)} · ${pct(change(lm.peak, lm.peakRef))}` : ""}
              </em></div>
            <div>반응 시작
              <strong>{onset === null || onset === undefined ? "—" : `${onset}분`}</strong>
              <em className={onset && lm.onsetRef && onset - lm.onsetRef >= 1 ? "neg" : ""}>
                {lm.onsetRef !== undefined && lm.onsetRef !== null ? `정상 ${num(lm.onsetRef, 1)}분` : ""}
              </em></div>
          </div>
          <div className="sec">
            <div className="sec-h"><b>이상 점수 추이</b><span>주의 {thr.watch} · 경보 {thr.alert} · 2분 연속일 때 등급 상승</span></div>
            {hasBase ? <ScoreChart scores={st.scores} thresholds={thr} dark /> : <p className="muted">정상 기준 없음</p>}
          </div>
          <div className="sec">
            <InsightBody insight={st.insight} pending={st.insightPending} waiting={running} />
          </div>
          <div className="row between">
            <span className="small">분석 #{id}</span>
            <Link className="btn" to={`/analyze?tank=${tankId ?? ""}`}>새 분석</Link>
          </div>
        </aside>
      </div>
    </div>
  );
}
