"""발표용 그림: 운영 소음 녹음 한 구간이 소음 처리 단계를 거치는 모습.

원신호 → 스펙트로그램 → 대역통과 → 에너지 포락선·적응 임계값·후보 → CNN 판정.
실행 (ai 폴더):
    ..\\..\\.venv\\Scripts\\python.exe scripts\\figure_noise_pipeline.py ^
        --session ..\\data_pipeline\\data\\synthetic\\mock_v1\\demo_normal_B1 --out docs\\figures\\noise_pipeline_B1.png
"""

from __future__ import annotations

import argparse
import csv
import json
from pathlib import Path

import matplotlib
import numpy as np
import soundfile as sf
from scipy import signal

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402

from shrimp_ai.config import DetectorConfig  # noqa: E402
from shrimp_ai.detect.candidates import StreamingCandidateDetector  # noqa: E402
from shrimp_ai.detect.cnn import ClickClassifier  # noqa: E402

plt.rcParams["font.family"] = "Malgun Gothic"
plt.rcParams["axes.unicode_minus"] = False


def read_csv(p: Path) -> list[dict]:
    with open(p, encoding="utf-8") as f:
        return list(csv.DictReader(f))


def pick_window(clicks: np.ndarray, bubbles: list[tuple[float, float]], feed: float, width: float) -> float:
    """급이 후 구간에서 클릭 2개 이상 + 강한 기포가 함께 있는 창의 시작 시각."""
    for t, a in sorted(bubbles, key=lambda b: -b[1]):
        if t < feed + 120:
            continue
        s = t - width * 0.4
        if np.sum((clicks >= s) & (clicks < s + width)) >= 2:
            return s
    return feed + 180


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("--session", required=True)
    ap.add_argument("--artifacts", default="artifacts")
    ap.add_argument("--out", required=True)
    ap.add_argument("--width", type=float, default=0.6)
    a = ap.parse_args(argv)
    d, art = Path(a.session), Path(a.artifacts)
    meta = json.loads((d / "meta.json").read_text(encoding="utf-8"))
    clicks = np.array([float(r["time_sec"]) for r in read_csv(d / "clicks.csv")])
    dis = read_csv(d / "distractors.csv")
    bubbles = [(float(r["time_sec"]), float(r["amp"])) for r in dis if r["kind"] == "bubble"]
    feed = float(meta["feeding_offset_sec"])
    w0 = pick_window(clicks, bubbles, feed, a.width)
    sr = sf.info(d / "audio.wav").samplerate
    warm = 6.0                                   # 잡음 수준 추정이 안정되도록 앞 6초부터 처리
    s0 = int((w0 - warm) * sr)
    x, _ = sf.read(d / "audio.wav", dtype="float32", start=s0, frames=int((warm + a.width + 0.05) * sr))

    cfg = DetectorConfig()
    clf = ClickClassifier.load(art / "click_cnn.pt")
    k = json.loads((art / "detector.json").read_text(encoding="utf-8"))["candidate_k"]
    det = StreamingCandidateDetector(sr, cfg, k)
    step = det.block
    cands, thr_t, thr_v = [], [], []
    for i in range(0, len(x), step):
        cands += det.process(x[i:i + step])
        if det.noise_energy is not None:
            thr_t.append((s0 + i) / sr)
            thr_v.append(det.noise_energy * det.k)
    cands += det.flush()
    bp = signal.butter(cfg.filter_order, (cfg.band_low_hz, min(cfg.band_high_hz, 0.45 * sr)),
                       btype="bandpass", fs=sr, output="sos")
    y = signal.sosfilt(bp, x)
    e = signal.sosfilt(signal.butter(2, cfg.envelope_lp_hz, fs=sr, output="sos"), y * y)

    ws, we = int(warm * sr), int((warm + a.width) * sr)
    t = (s0 + np.arange(ws, we)) / sr - feed
    in_win = [c for c in cands if ws <= c.index < we]          # 후보 위치는 x 시작 기준
    patches = [clf.spec.cut(x, c.index) for c in in_win]
    prob = clf.predict_proba(np.stack(patches)) if in_win else np.empty(0)
    ct = np.array([(s0 + c.index) / sr for c in in_win]) - feed
    db = lambda v: 10 * np.log10(np.asarray(v) + 1e-14)  # noqa: E731
    acc = prob >= clf.threshold
    truth = clicks[(clicks >= w0) & (clicks < w0 + a.width)] - feed
    dis_win = [(float(r["time_sec"]) - feed, r["kind"]) for r in dis if w0 <= float(r["time_sec"]) < w0 + a.width]

    fig, ax = plt.subplots(5, 1, figsize=(12, 13), sharex=True,
                           gridspec_kw={"height_ratios": [1, 1.3, 1, 1.2, 0.8]})
    ax[0].plot(t, x[ws:we], lw=0.4, color="#444")
    ax[0].set_title("① 원신호 — 펌프 웅웅거림(저주파 출렁임) + 에어레이션 쉿 소리 + 기포 + 클릭", loc="left", fontsize=11)
    f, tt, S = signal.spectrogram(x[ws:we], sr, nperseg=256, noverlap=192)
    ax[1].pcolormesh(t[0] + tt, f / 1000, 10 * np.log10(S + 1e-14), shading="auto", cmap="magma",
                     vmin=-120, vmax=-55)
    ax[1].axhspan(cfg.band_low_hz / 1000, min(cfg.band_high_hz, 0.45 * sr) / 1000, fill=False, ec="#5DCAA5", lw=1.2, ls="--")
    ax[1].set_ylabel("kHz")
    ax[1].set_title("② 스펙트로그램 — 클릭은 9–13 kHz 세로줄, 기포는 1–6 kHz 짧은 울림, 웅웅거림은 맨 아래 (점선 = 통과 대역)",
                    loc="left", fontsize=11)
    ax[2].plot(t, y[ws:we], lw=0.4, color="#185FA5")
    ax[2].set_title(f"③ 대역통과 {cfg.band_low_hz/1000:g}–{cfg.band_high_hz/1000:g} kHz — 펌프 웅웅거림·수류 저주파 제거",
                    loc="left", fontsize=11)
    ax[3].plot(t, db(e[ws:we]), lw=0.6, color="#185FA5", label="에너지 포락선")
    tv = np.array(thr_t) - feed
    m = (tv >= t[0] - 0.05) & (tv <= t[-1])
    ax[3].step(tv[m], db(np.array(thr_v)[m]), where="post", color="#D85A30", lw=1.2,
               label=f"적응 임계값 = 최근 {cfg.noise_history_sec:g}초 잡음 수준 × {k:g}")
    if len(ct):
        ax[3].plot(ct, db([e[c.index] for c in in_win]), "o", color="#D85A30", ms=6, label="후보")
    ax[3].set_ylabel("dB")
    ax[3].set_ylim(db(np.array(thr_v)[m]).min() - 25 if m.any() else None, None)
    ax[3].legend(loc="upper right", fontsize=9)
    ax[3].set_title("④ 에너지 포락선 + 적응 임계값 → 후보 (넓게 잡아 놓치지 않기)", loc="left", fontsize=11)
    for c, p, ok in zip(ct, prob, acc):
        ax[4].bar(c, p, width=0.004, color="#1D9E75" if ok else "#B4B2A9")
        ax[4].text(c, p + 0.04, f"{p:.2f}", ha="center", fontsize=8)
    ax[4].axhline(clf.threshold, color="#1D9E75", ls="--", lw=1, label=f"판정 임계값 {clf.threshold:g}")
    ax[4].plot(truth, np.full_like(truth, 1.25), "v", color="#185FA5", ms=8, label="정답 클릭")
    for tm, kind in dis_win:
        ax[4].plot(tm, 1.25, "^", color="#D85A30", ms=8)
        ax[4].text(tm, 1.38, kind, ha="center", fontsize=8, color="#D85A30")
    ax[4].set_ylim(0, 1.5)
    ax[4].legend(loc="upper left", fontsize=9)
    ax[4].set_title("⑤ CNN 판정 — 초록 = 클릭으로 인정, 회색 = 방해음으로 버림 (▲ 방해음 정답 위치)", loc="left", fontsize=11)
    ax[4].set_xlabel("급이 기준 시간 (초)")
    fig.suptitle(f"{meta['session_id']} · 운영 소음 조건 · 소음 처리 단계 (모크 데이터)", fontsize=13)
    fig.tight_layout()
    Path(a.out).parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(a.out, dpi=110)
    print(f"saved {a.out}  window {w0 - feed:.2f}s  candidates {len(in_win)}  accepted {int(acc.sum())}  "
          f"truth {len(truth)}  distractors {[k for _, k in dis_win]}")


if __name__ == "__main__":
    main()
