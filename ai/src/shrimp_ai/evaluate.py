"""평가: 모델 A(베이스라인 vs CNN, A·B 조건), 모델 B(오경보율·합성 이상 탐지율), 시연 파일.

- 모델 A: 세션마다 정답 클릭과 5 ms 1:1 매칭 → P/R/F1, 분당 클릭 수 MAE. 처리 속도(배속).
- 정상 기준: 수조별 정상 4일치의 '모델 A 출력' G(t) 로 만든다(실사용과 같은 조건).
- 모델 B: 수조 안에서 하루씩 빼고 기준을 만든 뒤 뺀 날로 오경보율, 그 날을 변형한 합성 이상으로 탐지율.
- 시연: demo 세션을 실제 스트리밍 엔진으로 돌려 경보 시점·최종 등급 확인.

실행 (ai 폴더):
    ..\\..\\.venv\\Scripts\\python.exe -m shrimp_ai.evaluate --data ..\\data_pipeline\\data\\synthetic\\mock_v1
"""

from __future__ import annotations

import argparse
import json
import time
from collections import defaultdict
from pathlib import Path

import numpy as np
import soundfile as sf

from shrimp_ai.activity import minute_counts
from shrimp_ai.anomaly import GRADES, build_baseline, score_session
from shrimp_ai.config import AnalysisConfig, AnomalyConfig, DetectorConfig
from shrimp_ai.dataset import Session, load_sessions
from shrimp_ai.detect.candidates import StreamingCandidateDetector, detect_all
from shrimp_ai.detect.cnn import ClickClassifier
from shrimp_ai.engine import StreamingAnalyzer
from shrimp_ai.metrics import cpm_mae, from_counts, match_clicks
from shrimp_ai.sources import FileSource

VARIANTS = {"peak_drop": (0.75, 0.5, 0.3), "delay_min": (1, 2, 3), "early_decay_tau": (15, 8, 4)}


def run_detectors(s: Session, clf: ClickClassifier, det: dict, cfg: AnalysisConfig) -> dict:
    """세션 하나에 베이스라인·CNN 검출을 돌리고 결과 요약과 분당 클릭 수."""
    x, sr = sf.read(s.audio_path, dtype="float32")
    t0 = time.perf_counter()
    cands = detect_all(x, sr, cfg.chunk_sec, DetectorConfig(), k=det["candidate_k"])
    idx = [c.index for c in cands]
    patches = [clf.spec.cut(x, i) for i in idx]
    ok = [p is not None for p in patches]
    prob = clf.predict_proba(np.stack([p for p in patches if p is not None]))
    cnn_t = np.array([i / sr for i, o in zip(idx, ok) if o])[prob >= clf.threshold]
    t_cnn = time.perf_counter() - t0
    t0 = time.perf_counter()
    base_t = np.array([c.index / sr for c in detect_all(x, sr, cfg.chunk_sec, DetectorConfig(), k=det["baseline_k"])])
    t_base = time.perf_counter() - t0
    truth = s.truth_clicks()
    dur = len(x) / sr
    out = {"session_id": s.session_id, "tank": s.tank, "condition": s.noise_condition, "split": s.split,
           "label": s.label, "duration_sec": round(dur, 1), "n_truth": len(truth),
           "speed_x_cnn": round(dur / t_cnn, 1), "speed_x_baseline": round(dur / t_base, 1)}
    counts = {"truth": minute_counts(truth, s.feeding_offset_sec, cfg)}
    for name, t in (("cnn", cnn_t), ("baseline", base_t)):
        m = match_clicks(truth, t, cfg.eval_tolerance_ms)
        counts[name] = minute_counts(t, s.feeding_offset_sec, cfg)
        out[name] = {"tp": m.tp, "fp": m.fp, "fn": m.fn, "precision": round(m.precision, 4),
                     "recall": round(m.recall, 4), "f1": round(m.f1, 4),
                     "cpm_mae": round(cpm_mae(counts["truth"], counts[name]), 3)}
    return {"summary": out, "counts": {k: v.tolist() for k, v in counts.items()}}


def aggregate(rows: list[dict], name: str) -> dict:
    tp, fp, fn = (sum(r[name][k] for r in rows) for k in ("tp", "fp", "fn"))
    m = from_counts(tp, fp, fn)
    return {"n_sessions": len(rows), "precision": round(m.precision, 4), "recall": round(m.recall, 4),
            "f1": round(m.f1, 4), "cpm_mae": round(float(np.mean([r[name]["cpm_mae"] for r in rows])), 3)}


def make_variant(counts: np.ndarray, kind: str, level: float, rng: np.random.Generator,
                 cfg: AnalysisConfig) -> np.ndarray:
    """정상 곡선을 변형한 합성 이상(급이 후만). 포아송 재표본으로 분당 개수의 흔들림을 유지."""
    pre_n = int(cfg.pre_window_min)
    c = np.asarray(counts, dtype=float)
    base = c[:pre_n].mean()
    excess = np.maximum(c[pre_n:] - base, 0)
    t = np.arange(len(excess))
    if kind == "peak_drop":
        excess = excess * level
    elif kind == "delay_min":
        excess = np.concatenate([np.zeros(int(level)), excess[: len(excess) - int(level)]])
    elif kind == "early_decay_tau":
        excess = excess * np.exp(-t / level)
    post = rng.poisson(base + excess)
    return np.concatenate([c[:pre_n], post]).astype(int)


def first_alert(states, level: str = "alert") -> int | None:
    for s in states:
        if GRADES.index(s.grade) >= GRADES.index(level):
            return s.minute
    return None


def evaluate_model_b(curves: dict, sessions: list[Session], cfg: AnalysisConfig, acfg: AnomalyConfig,
                     out_dir: Path, seed: int = 0) -> dict:
    rng = np.random.default_rng(seed)
    by_tank = defaultdict(list)
    for s in sessions:
        if s.label == "normal" and s.split in ("train", "val", "test_noise"):
            by_tank[s.tank].append(s.session_id)
    # 수조별 정상 기준(4일 전부) 저장
    for tank, ids in by_tank.items():
        b = build_baseline([np.array(curves[i]) for i in ids], tank, ids, cfg, acfg)
        b.save(out_dir / "baselines" / f"{tank}.json")
    fa, var = [], defaultdict(list)
    for tank, ids in by_tank.items():
        for held in ids:
            rest = [i for i in ids if i != held]
            b = build_baseline([np.array(curves[i]) for i in rest], tank, rest, cfg, acfg)
            st = score_session(np.array(curves[held]), b, cfg, acfg)
            fa.append({"session_id": held, "tank": tank, "max_grade": max((s.grade for s in st), key=GRADES.index),
                       "final_score": round(st[-1].score, 3), "max_score": round(max(s.score for s in st), 3)})
            for kind, levels in VARIANTS.items():
                for lv in levels:
                    v = make_variant(np.array(curves[held]), kind, lv, rng, cfg)
                    sv = score_session(v, b, cfg, acfg)
                    var[(kind, lv)].append({"alert": first_alert(sv) is not None,
                                            "watch": first_alert(sv, "watch") is not None,
                                            "first_alert_min": first_alert(sv)})
    n = len(fa)
    detection = []
    for (kind, lv), rows in var.items():
        mins = [r["first_alert_min"] for r in rows if r["first_alert_min"] is not None]
        detection.append({"kind": kind, "level": lv, "n": len(rows),
                          "alert_rate": round(np.mean([r["alert"] for r in rows]), 3),
                          "watch_or_alert_rate": round(np.mean([r["watch"] for r in rows]), 3),
                          "median_first_alert_min": float(np.median(mins)) if mins else None})
    return {"loo_sessions": n,
            "false_alarm_rate": round(sum(r["max_grade"] == "alert" for r in fa) / n, 3),
            "watch_rate": round(sum(r["max_grade"] != "normal" for r in fa) / n, 3),
            "loo": fa, "synthetic_detection": detection}


def run_demo(s: Session, clf: ClickClassifier, det: dict, out_dir: Path, cfg: AnalysisConfig,
             acfg: AnomalyConfig) -> dict:
    """실제 스트리밍 엔진(FileSource → StreamingAnalyzer)으로 시연 세션 분석."""
    from shrimp_ai.anomaly import Baseline
    base = Baseline.load(out_dir / "baselines" / f"{s.tank}.json")
    src = FileSource(s.audio_path, cfg.chunk_sec, speed=0)
    eng = StreamingAnalyzer(src.sr, s.feeding_offset_sec,
                            StreamingCandidateDetector(src.sr, DetectorConfig(), det["candidate_k"]),
                            clf, base, cfg, acfg)
    t0 = time.perf_counter()
    events = []
    for chunk in src:
        events += eng.feed(chunk)
    events += eng.finish()
    wall = time.perf_counter() - t0
    final = events[-1]
    alerts = [e for e in events if e["type"] == "alert"]
    truth = s.truth_clicks()
    m = match_clicks(truth, eng.click_times, cfg.eval_tolerance_ms)
    return {"session_id": s.session_id, "label": s.label, "max_grade": final["max_grade"],
            "final_score": final["score"], "alerts": alerts, "metrics": final["metrics"],
            "comparison": final["comparison"], "f1": round(m.f1, 4),
            "speed_x": round(src.duration_sec / wall, 1), "compute_sec": final["compute_sec"]}


def write_markdown(rep: dict, path: Path) -> None:
    a, b = rep["model_a"], rep["model_b"]
    L = ["# 평가 리포트 (모크 데이터 — 실측 성능 아님)", "",
         f"- 데이터: `{rep['data']}`  · 생성 {rep['created_at']}", "", "## 모델 A: 클릭 검출", "",
         "| 조건 | 방식 | Precision | Recall | F1 | CPM MAE |", "|---|---|---|---|---|---|"]
    for cond in ("A_val", "B_test_noise"):
        for name in ("baseline", "cnn"):
            r = a[cond][name]
            L.append(f"| {cond} | {name} | {r['precision']} | {r['recall']} | {r['f1']} | {r['cpm_mae']} |")
    L += ["", f"- CPM MAE 감소(베이스라인 대비 CNN): A {a['mae_reduction_pct']['A_val']}%, "
              f"B {a['mae_reduction_pct']['B_test_noise']}%",
          f"- 처리 속도(40분 녹음 기준, CNN 경로): 중앙값 {a['speed_x_cnn_median']}배속", "",
          "## 모델 B: 이상 탐지", "",
          f"- 정상 세션 오경보율(LOO, {b['loo_sessions']}개): **{b['false_alarm_rate']}** (주의 이상 {b['watch_rate']})",
          "", "| 합성 이상 | 강도 | 경보율 | 주의 이상 | 첫 경보(분, 중앙값) |", "|---|---|---|---|---|"]
    for r in b["synthetic_detection"]:
        L.append(f"| {r['kind']} | {r['level']} | {r['alert_rate']} | {r['watch_or_alert_rate']} | "
                 f"{r['median_first_alert_min']} |")
    L += ["", "## 시연 세션 (스트리밍 엔진)", ""]
    for d in rep["demo"]:
        first = d["alerts"][0] if d["alerts"] else None
        L.append(f"- `{d['session_id']}`: 최종 {d['max_grade']} (점수 {d['final_score']['score']}), "
                 f"첫 등급 상승 {('급이 후 ' + str(first['minute'] + 1) + '분 ' + first['level']) if first else '없음'}, "
                 f"F1 {d['f1']}, {d['speed_x']}배속")
    path.write_text("\n".join(L) + "\n", encoding="utf-8")


def main(argv=None):
    ap = argparse.ArgumentParser(description="모델 A·B 평가")
    ap.add_argument("--data", required=True)
    ap.add_argument("--artifacts", default="artifacts")
    a = ap.parse_args(argv)
    cfg, acfg = AnalysisConfig(), AnomalyConfig()
    out = Path(a.artifacts)
    clf = ClickClassifier.load(out / "click_cnn.pt")
    det = json.loads((out / "detector.json").read_text(encoding="utf-8"))
    sessions = load_sessions(a.data)

    rows, curves = [], {}
    (out / "curves").mkdir(parents=True, exist_ok=True)
    for s in sessions:
        r = run_detectors(s, clf, det, cfg)
        rows.append(r["summary"])
        curves[s.session_id] = r["counts"]["cnn"]
        (out / "curves" / f"{s.session_id}.json").write_text(json.dumps(r["counts"]), encoding="utf-8")
        sm = r["summary"]
        print(f"{s.session_id:>20} {sm['split']:<10} base F1={sm['baseline']['f1']:.3f} MAE={sm['baseline']['cpm_mae']:.2f}"
              f" | cnn F1={sm['cnn']['f1']:.3f} MAE={sm['cnn']['cpm_mae']:.2f} | {sm['speed_x_cnn']}x")

    groups = {"A_val": [r for r in rows if r["split"] == "val"],
              "B_test_noise": [r for r in rows if r["split"] == "test_noise"],
              "A_train": [r for r in rows if r["split"] == "train"]}
    model_a = {g: {n: aggregate(v, n) for n in ("baseline", "cnn")} for g, v in groups.items()}
    model_a["mae_reduction_pct"] = {
        g: round((1 - model_a[g]["cnn"]["cpm_mae"] / model_a[g]["baseline"]["cpm_mae"]) * 100, 1)
        if model_a[g]["baseline"]["cpm_mae"] else None for g in ("A_val", "B_test_noise")}
    model_a["speed_x_cnn_median"] = float(np.median([r["speed_x_cnn"] for r in rows]))
    model_a["sessions"] = rows

    model_b = evaluate_model_b(curves, sessions, cfg, acfg, out)
    demo = [run_demo(s, clf, det, out, cfg, acfg) for s in sessions if s.split == "demo"]
    rep = {"created_at": time.strftime("%Y-%m-%d %H:%M"), "data": str(a.data), "note": "모크 데이터 — 실측 성능 아님",
           "detector": det, "classifier_threshold": clf.threshold, "model_a": model_a, "model_b": model_b,
           "demo": demo}
    (out / "eval_report.json").write_text(json.dumps(rep, ensure_ascii=False, indent=2), encoding="utf-8")
    write_markdown(rep, out / "eval_report.md")
    print((out / "eval_report.md").read_text(encoding="utf-8"))


if __name__ == "__main__":
    main()
