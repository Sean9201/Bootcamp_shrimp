import { useEffect, useState } from "react";
import { Link, useParams } from "react-router-dom";
import { getAnalysis } from "../api.js";
import { AlertBanner, Card, ComparisonTable, ErrorBox, GradeBadge, InsightCard, Metric, Progress, ScoreChart } from "../components/Bits.jsx";
import { LiveChart } from "../components/LiveChart.jsx";
import { conditionLabel, feedClock, kst, num, pct, speedLabel } from "../format.js";
import { useAnalysisStream } from "../stream.js";

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
  return { peak, auc10: n10 ? auc10 : null, n10, peakRef: ref.peak_cpm?.mean, aucRef: ref.auc10?.mean };
}

const change = (v, ref) => (v === null || !ref ? null : ((v - ref) / ref) * 100);

export default function AnalysisView() {
  const { id } = useParams();
  const st = useAnalysisStream(id);
  const [info, setInfo] = useState(null);
  const [err, setErr] = useState(null);
  const finished = st.status === "done";

  useEffect(() => {
    getAnalysis(id).then(setInfo).catch((e) => setErr(e.message));
  }, [id, finished]);

  const meta = st.meta;
  const lm = liveMetrics(st);
  const last = st.scores[st.scores.length - 1];
  const thr = meta?.thresholds ?? { watch: 1.25, alert: 2, onset_sd_floor_min: 0.7 };
  const hasBase = Boolean(meta?.baseline);
  const running = st.status === "running" || st.status === "connecting";
  const comparison = st.final?.comparison;
  const stage = st.final ? "급이 후 30분 확정" : last && last.minute >= 9 ? "10분 조기 판정 이후" : "잠정";

  return (
    <div className="page">
      <div className="page-h">
        <div>
          <h1>분석 #{id}</h1>
          <p className="muted">
            수조 {meta?.tank_id ?? info?.tank_id ?? "—"} · {conditionLabel(meta?.noise_condition ?? info?.noise_condition)}
            {" · "}{info?.filename ?? ""}{" · "}{speedLabel(meta?.speed ?? info?.speed)}
            {info?.fed_at && <> · 급이 {kst(info.fed_at)}</>}
          </p>
        </div>
        <div className="row gap">
          <span className={`chip ${running ? "live" : ""}`}>
            {running ? "● 실시간 분석 중" : st.status === "finalizing" ? "결과 정리 중" : st.status === "failed" ? "실패" : "완료"}
          </span>
          <Link className="btn ghost" to="/analyze">새 분석</Link>
        </div>
      </div>

      <ErrorBox message={err || st.error} />
      {!hasBase && meta && <div className="note">이 수조는 정상 기준이 없어 점수·경보 없이 활동 곡선만 표시합니다.</div>}

      <div className="progress-row">
        <Progress tSec={st.tSec} pre={meta?.pre_min ?? 10} post={meta?.post_min ?? 30} />
        <span className="muted">{feedClock(st.tSec)} · 검출 클릭 {st.clicks.length.toLocaleString()}개</span>
      </div>

      <AlertBanner alerts={st.alerts} />

      <div className="metrics">
        <Metric label="판정" value={hasBase ? <GradeBadge grade={st.maxGrade} big /> : "—"} sub={stage} />
        <Metric label="현재 Peak" value={lm.peak ?? "—"} unit="CPM"
                sub={lm.peakRef ? `정상 ${num(lm.peakRef)} · ${pct(change(lm.peak, lm.peakRef))}` : ""}
                tone={change(lm.peak, lm.peakRef) < -20 ? "neg" : ""} />
        <Metric label={`초기 10분 AUC${lm.n10 && lm.n10 < 10 ? ` (${lm.n10}분까지)` : ""}`} value={lm.auc10 ?? "—"}
                sub={lm.aucRef && lm.n10 === 10 ? `정상 ${num(lm.aucRef)} · ${pct(change(lm.auc10, lm.aucRef))}`
                  : lm.aucRef ? `정상 ${num(lm.aucRef)} (10분 기준)` : ""}
                tone={lm.n10 === 10 && change(lm.auc10, lm.aucRef) < -20 ? "neg" : ""} />
        <Metric label="이상 점수" value={last ? num(last.score, 1) : "—"} sub={`주의 ${thr.watch} · 경보 ${thr.alert}`}
                tone={last && last.score >= thr.alert ? "neg" : last && last.score >= thr.watch ? "warn" : ""} />
      </div>

      <div className="grid-main">
        <Card title="클릭 활동 시계열 G(t)" right={<span className="muted small">급이 시각 = 0분, 1분 단위</span>}>
          <LiveChart state={st} />
        </Card>
        <div className="col">
          <Card title="이상 점수 추이">
            {hasBase ? <ScoreChart scores={st.scores} thresholds={thr} /> : <p className="muted">정상 기준 없음</p>}
            <p className="muted small">같은 경과 시간의 정상 기준과 매 분 비교합니다. 2분 연속 기준 이상일 때 등급이 올라갑니다.</p>
          </Card>
          <Card title="주요 지표 비교">
            {comparison ? <ComparisonTable rows={comparison} onsetFloor={thr.onset_sd_floor_min} />
              : <p className="muted">급이 후 30분 분석이 끝나면 표시됩니다.</p>}
          </Card>
        </div>
      </div>

      <InsightCard insight={st.insight} pending={st.insightPending} waiting={running} />
    </div>
  );
}
