"""1단계 후보 검출기: 정확도, 청크 크기와 무관한 결과, 불응기 병합."""

import numpy as np

from conftest import SR, make_clicks
from shrimp_ai.detect.candidates import StreamingCandidateDetector, detect_all
from shrimp_ai.metrics import match_clicks

TIMES = np.round(np.sort(np.random.default_rng(1).uniform(0.5, 9.5, 40)), 4)


def test_detects_clicks_in_noise():
    x = make_clicks(TIMES, 10)
    pred = [c.index / SR for c in detect_all(x, SR, k=20)]
    m = match_clicks(TIMES, pred, 5.0)
    assert m.recall == 1.0 and m.precision > 0.95


def test_chunk_size_does_not_change_result():
    """실시간(작은 청크)과 파일 일괄 처리의 결과가 같아야 한다."""
    x = make_clicks(TIMES, 10)
    a = [c.index for c in detect_all(x, SR, chunk_sec=1.0, k=20)]
    b = [c.index for c in detect_all(x, SR, chunk_sec=0.0371, k=20)]
    assert a == b


def test_refractory_merges_close_peaks():
    x = make_clicks([1.0, 1.003], 2, noise_rms=0.001)
    c = detect_all(x, SR, k=20)
    assert len(c) == 1


def test_streaming_emits_only_after_refractory():
    x = make_clicks([0.99], 2)
    det = StreamingCandidateDetector(SR, k=20)
    first = det.process(x[:SR])          # 최고점이 청크 끝 근처 → 아직 확정 안 됨
    second = det.process(x[SR:])
    assert first == [] and len(second) == 1
