"""모크 세션 합성기 검증. 실제 샘플 WAV 없이 임시 클릭 파일로 확인한다."""

import csv
import json

import numpy as np
import pytest
import soundfile as sf

from shrimp_data.session import load_session
from shrimp_data.synthetic import (ABNORMAL, NORMAL, ResponseProfile, SessionSpec, SynthConfig,
                                   expected_cpm, load_click_bank, render_session, sample_click_times)

SR = 48000


@pytest.fixture
def click_source(tmp_path):
    """클릭 4개가 든 2초 WAV + labels.csv."""
    x = np.zeros(2 * SR, dtype=np.float32)
    t = np.arange(int(0.003 * SR)) / SR
    click = np.sin(2 * np.pi * 11000 * t) * np.exp(-t / 0.0005)
    rows = []
    for i, s in enumerate([0.2, 0.6, 1.0, 1.4]):
        k = int((s + 0.01) * SR)
        x[k:k + len(click)] += 0.2 * click
        rows.append({"file": "src.wav", "event_id": i, "start_sec": s, "end_sec": s + 0.035,
                     "label": "c", "deliberate_overlap": "no"})
    sf.write(tmp_path / "src.wav", x, SR, subtype="PCM_16")
    with open(tmp_path / "labels.csv", "w", newline="", encoding="utf-8-sig") as f:
        w = csv.DictWriter(f, fieldnames=list(rows[0]))
        w.writeheader()
        w.writerows(rows)
    return tmp_path / "src.wav", tmp_path / "labels.csv"


SHORT = SynthConfig(pre_min=1, post_min=4)
QUICK = ResponseProfile(baseline_cpm=10, peak_cpm=120, onset_min=0.5, rise_min=1.0, decay_tau_min=2.0, tail_cpm=20)


def test_expected_cpm_shape():
    t = np.array([-5, 0, NORMAL.onset_min + NORMAL.rise_min, 29])
    c = expected_cpm(NORMAL, t)
    assert c[0] == c[1] == NORMAL.baseline_cpm
    assert c[2] == pytest.approx(NORMAL.peak_cpm)
    assert NORMAL.tail_cpm < c[3] < NORMAL.peak_cpm


def test_profiles_match_demo_targets():
    """시안의 정상·이상 수치와 비슷한 초기 10분 AUC."""
    t = np.arange(0, 10, 1 / 60) + 1 / 120
    auc = lambda p: expected_cpm(p, t).sum() / 60  # noqa: E731
    assert 560 < auc(NORMAL) < 680
    assert 180 < auc(ABNORMAL) < 260


def test_click_times_follow_profile():
    rng = np.random.default_rng(0)
    times = sample_click_times(QUICK, SHORT, rng)
    assert np.all(np.diff(times) >= SHORT.min_click_gap_sec)
    rel = times / 60 - SHORT.pre_min
    pre = np.sum(rel < 0)
    peak_win = np.sum((rel >= 1.0) & (rel < 2.0))
    assert peak_win > 4 * pre


def test_click_bank_aligned(click_source):
    bank, sr = load_click_bank(*click_source, SHORT)
    assert sr == SR and bank.shape[0] == 4
    pre = int(SHORT.template_pre_sec * SR)
    assert np.all(np.abs(np.argmax(np.abs(bank), axis=1) - pre) <= 2)
    assert np.allclose(np.abs(bank).max(1), 1.0)


@pytest.mark.parametrize("tank", ["A1", "B1"])
def test_render_session(tmp_path, click_source, tank):
    bank, sr = load_click_bank(*click_source, SHORT)
    spec = SessionSpec("s1", tank, 1, "normal", "train", profile=QUICK)
    r = render_session(spec, bank, sr, tmp_path / "out", SHORT, master_seed=1)
    d = tmp_path / "out" / "s1"
    info = sf.info(d / "audio.wav")
    assert info.samplerate == SR and info.frames == 5 * 60 * SR
    meta, problems = load_session(d)
    assert problems == [] and meta.data_source == "synthetic" and meta.synthetic["profile"]["peak_cpm"] == 120
    with open(d / "clicks.csv", encoding="utf-8") as f:
        clicks = [float(row["time_sec"]) for row in csv.DictReader(f)]
    assert len(clicks) == r["n_clicks"] > 50
    # 정답 시각에 실제로 소리가 있어야 한다(클릭 최고점 ±1 ms)
    x, _ = sf.read(d / "audio.wav", dtype="float32")
    floor = np.median(np.abs(x))
    loud = [np.abs(x[int(t * SR) - 48: int(t * SR) + 48]).max() > 5 * floor for t in clicks[:50]]
    assert np.mean(loud) > 0.9
    kinds = {row["kind"] for row in csv.DictReader(open(d / "distractors.csv", encoding="utf-8"))}
    assert {"splash", "pellet"} <= kinds
    assert ("bubble" in kinds) == (tank == "B1")


def test_render_is_reproducible(tmp_path, click_source):
    bank, sr = load_click_bank(*click_source, SHORT)
    spec = SessionSpec("s", "A2", 1, "abnormal", "demo")
    a = render_session(spec, bank, sr, tmp_path / "a", SHORT, master_seed=7)
    b = render_session(spec, bank, sr, tmp_path / "b", SHORT, master_seed=7)
    assert a == b
    ma = json.loads((tmp_path / "a" / "s" / "meta.json").read_text(encoding="utf-8"))
    assert ma["label"] == "abnormal" and ma["synthetic"]["split"] == "demo"
