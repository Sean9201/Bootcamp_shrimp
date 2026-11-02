"""스트리밍 엔진과 입력 소스."""

import numpy as np
import soundfile as sf

from conftest import SR, make_clicks
from shrimp_ai.anomaly import build_baseline
from shrimp_ai.config import AnalysisConfig, AnomalyConfig
from shrimp_ai.detect.candidates import StreamingCandidateDetector
from shrimp_ai.engine import StreamingAnalyzer
from shrimp_ai.sources import FileSource

# 짧은 세션: 급이 전 1분 + 급이 후 2분, 분 단위는 10초로 줄여 테스트를 빠르게
CFG = AnalysisConfig(pre_window_min=1, post_window_min=2, bin_sec=10.0, auc_window_min=1)
ACFG = AnomalyConfig(min_minutes_for_alert=1, early_minute=1)


def session_audio(rate_pre, rate_post, seed=0):
    rng = np.random.default_rng(seed)
    grid = lambda a, b, n: np.sort(rng.choice(np.arange(a, b, 0.05), n, replace=False))  # noqa: E731  50 ms 이상 간격
    pre, post = grid(0.1, 9.9, rate_pre), grid(10.1, 29.9, rate_post)
    times = np.concatenate([pre, post])
    return make_clicks(times, 30, seed=seed), times


def run(x, base=None, chunk=SR):
    eng = StreamingAnalyzer(SR, 10.0, StreamingCandidateDetector(SR, k=20), None, base, CFG, ACFG)
    ev = []
    for i in range(0, len(x), chunk):
        ev += eng.feed(x[i:i + chunk])
    return eng, ev + eng.finish()


def test_engine_counts_and_events():
    x, times = session_audio(3, 30)
    eng, ev = run(x)
    final = ev[-1]
    assert final["type"] == "final" and final["counts"][0] == 3 and sum(final["counts"]) == 33
    minutes = [e["minute"] for e in ev if e["type"] == "minute"]
    assert minutes == [-1, 0, 1]
    clicks = sum(len(e["t"]) for e in ev if e["type"] == "clicks")
    assert clicks == len(eng.click_times) == 33


def test_engine_scores_and_alert():
    normals = [run(session_audio(3, 30, seed=s)[0])[0].counts for s in range(4)]
    base = build_baseline(normals, "T", None, CFG, ACFG)
    _, ev = run(session_audio(3, 6, seed=9)[0], base)
    kinds = [e["type"] for e in ev]
    assert "score" in kinds and ev[-1]["comparison"]
    assert ev[-1]["max_grade"] in ("watch", "alert")


def test_engine_same_result_for_any_chunk_size():
    x, _ = session_audio(3, 30)
    a, _ = run(x, chunk=SR)
    b, _ = run(x, chunk=777)
    assert a.click_times == b.click_times


def test_file_source_paces_by_speed(tmp_path):
    p = tmp_path / "a.wav"
    sf.write(p, np.zeros(SR * 4, dtype=np.float32), SR)
    now = [0.0]
    waits = []
    src = FileSource(p, chunk_sec=1.0, speed=40, clock=lambda: now[0],
                     sleep=lambda s: (waits.append(s), now.__setitem__(0, now[0] + s)))
    chunks = list(src)
    assert len(chunks) == 4 and all(len(c) == SR for c in chunks)
    assert np.allclose(waits, [1 / 40] * 4)
