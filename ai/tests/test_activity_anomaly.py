"""활동 지표와 모델 B(정상 기준·점수·등급)."""

import numpy as np
import pytest

from shrimp_ai.activity import compute_metrics, minute_counts, onset_minute
from shrimp_ai.anomaly import Baseline, build_baseline, compare, score_session
from shrimp_ai.config import AnalysisConfig

CFG = AnalysisConfig()


def curve(peak=100, onset=1, decay=8.0, base=8, seed=0):
    """분 번호 축(-10..29) 분당 클릭 수."""
    rng = np.random.default_rng(seed)
    t = np.arange(30)
    post = np.where(t < onset, base, base + (peak - base) * np.exp(-np.maximum(t - onset - 3, 0) / decay)
                    * np.clip((t - onset + 1) / 3, 0, 1))
    return np.concatenate([rng.poisson(base, 10), rng.poisson(post)]).astype(int)


def test_minute_counts_alignment():
    # 녹음 시작 기준: 급이 600초. 599.9초 → -1분, 600초 → 0분, 2399초 → 29분
    c = minute_counts([599.9, 600.0, 2399.0, 5000.0], 600, CFG)
    assert len(c) == 40 and c[9] == 1 and c[10] == 1 and c[39] == 1 and c.sum() == 3


def test_metrics_and_onset():
    c = curve(peak=100, onset=2)
    m = compute_metrics(c, CFG)
    assert m.peak_cpm >= 80 and m.auc10 > m.peak_cpm and m.auc30 >= m.auc10
    assert onset_minute(c[10:], c[:10]) in (1, 2, 3)


def test_baseline_and_scores():
    normals = [curve(seed=i, peak=100 + 5 * i) for i in range(4)]
    b = build_baseline(normals, "A1", [f"s{i}" for i in range(4)], CFG)
    assert len(b.mu) == 40 and all(e >= s for e, s in zip(b.sd_eff, b.sd))
    ok = score_session(curve(seed=9, peak=104), b, CFG)
    bad = score_session(curve(seed=9, peak=40, onset=4), b, CFG)
    assert max(s.grade for s in ok) == "normal"
    assert any(s.grade == "alert" for s in bad)
    assert ok[-1].stage == "final" and ok[9].stage == "early" and ok[0].stage == "provisional"
    # 첫 경보는 최소 분 수 이후
    assert all(s.grade == "normal" for s in bad[:2])


def test_grade_needs_persistence(monkeypatch):
    """한 분만 튄 점수로는 등급이 오르지 않고, 2분 연속이면 오른다."""
    import shrimp_ai.anomaly as an
    from shrimp_ai.anomaly import OnlineScorer, ScoreState

    raw = iter(["normal", "alert", "normal", "watch", "alert", "alert"])
    monkeypatch.setattr(an, "score_at", lambda *a, **k: (lambda g: ScoreState(0, 0.0, g, 0, 0, 0, "provisional", g))(next(raw)))
    sc = OnlineScorer(None)
    grades = [sc.update(None, m).grade for m in range(6)]
    assert grades == ["normal", "normal", "normal", "normal", "watch", "alert"]


def test_baseline_roundtrip(tmp_path):
    b = build_baseline([curve(seed=i) for i in range(3)], "B2", None, CFG)
    b.save(tmp_path / "b.json")
    b2 = Baseline.load(tmp_path / "b.json")
    assert b2.mu == b.mu and b2.metrics == b.metrics


def test_compare_rows():
    b = build_baseline([curve(seed=i) for i in range(4)], "A1", None, CFG)
    rows = {r["metric"]: r for r in compare(curve(seed=7, peak=50), b, CFG)}
    assert rows["peak_cpm"]["change_pct"] < -30
    assert rows["auc10"]["normal_mean"] == pytest.approx(b.metrics["auc10"]["mean"], abs=0.1)
