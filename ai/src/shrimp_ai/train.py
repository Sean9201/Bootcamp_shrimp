"""2단계 CNN 학습 + 신호처리 베이스라인 임계값 선택.

- 학습: split=train 세션(A 수조 1–3일차)의 후보 패치. 정답 클릭과 5 ms 안에 1:1 로 맞으면 클릭.
- 검증: split=val 세션(A 수조 4일차)으로 epoch 선택·판정 임계값·베이스라인 k 를 정한다.
- B 수조(test_noise)는 여기서 쓰지 않는다(소음 강건성 시험용).

실행 (ai 폴더):
    ..\\..\\.venv\\Scripts\\python.exe -m shrimp_ai.train --data ..\\data_pipeline\\data\\synthetic\\mock_v1
"""

from __future__ import annotations

import argparse
import json
import time
from pathlib import Path

import numpy as np
import soundfile as sf
import torch
from torch import nn

from shrimp_ai.config import AnalysisConfig, DetectorConfig, PatchConfig
from shrimp_ai.dataset import Session, load_sessions
from shrimp_ai.detect.candidates import detect_all
from shrimp_ai.detect.cnn import ClickClassifier, ClickCNN, PatchSpec
from shrimp_ai.metrics import from_counts, match_flags

MARGIN_SEC = 0.001          # 학습 때 시간 이동 증강 폭(±)
K_GRID = (8, 12, 16, 20, 30, 40, 60, 80, 120, 160, 240, 320, 480, 640, 960, 1280)
K_TOLERANCE = 0.005


def collect(sessions: list[Session], spec: PatchSpec, cfg: AnalysisConfig, dcfg: DetectorConfig) -> dict:
    """세션들의 후보 패치·라벨·SNR 과 정답 개수."""
    margin = int(MARGIN_SEC * spec.sr)
    X, y, snr, n_truth, per = [], [], [], 0, []
    for s in sessions:
        x, sr = sf.read(s.audio_path, dtype="float32")
        assert sr == spec.sr, f"{s.session_id}: 샘플레이트 {sr} ≠ {spec.sr}"
        truth = s.truth_clicks()
        cands = detect_all(x, sr, cfg.chunk_sec, dcfg)
        times = np.array([c.index / sr for c in cands])
        flags = match_flags(truth, times, cfg.eval_tolerance_ms)
        for c, f in zip(cands, flags):
            a = c.index - spec.pre - margin
            b = a + spec.length + 2 * margin
            if a >= 0 and b <= len(x):
                X.append(x[a:b])
                y.append(f)
                snr.append(c.snr)
        n_truth += len(truth)
        per.append({"session_id": s.session_id, "n_truth": len(truth), "n_candidates": len(cands),
                    "candidate_recall": round(float(flags.sum() / max(len(truth), 1)), 4)})
        print(f"  {s.session_id}: 후보 {len(cands)}, 정답 {len(truth)}, 후보 재현율 {per[-1]['candidate_recall']}")
    return {"X": np.stack(X).astype(np.float32), "y": np.array(y), "snr": np.array(snr),
            "n_truth": n_truth, "sessions": per}


def crop(X: np.ndarray, spec: PatchSpec, rng: np.random.Generator | None) -> np.ndarray:
    """여유분을 둔 패치에서 정해진 길이로 자르기(학습: 무작위 이동, 평가: 가운데)."""
    margin = (X.shape[1] - spec.length) // 2
    if rng is None:
        return X[:, margin: margin + spec.length]
    off = rng.integers(0, 2 * margin + 1, len(X))
    idx = off[:, None] + np.arange(spec.length)[None, :]
    return np.take_along_axis(X, idx, axis=1)


def session_f1(prob: np.ndarray, y: np.ndarray, n_truth: int, thr: float):
    """후보 판정 결과를 세션 단위 F1 로(후보 단계에서 놓친 정답도 FN 으로 센다)."""
    pred = prob >= thr
    tp = int((pred & y).sum())
    return from_counts(tp, int((pred & ~y).sum()), n_truth - tp)


def train(args) -> None:
    cfg, dcfg = AnalysisConfig(), DetectorConfig()
    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)
    tr_s = load_sessions(args.data, ("train",))
    va_s = load_sessions(args.data, ("val",))
    sr = sf.info(tr_s[0].audio_path).samplerate
    spec = PatchSpec(sr, PatchConfig())
    print(f"학습 세션 {len(tr_s)}개, 검증 {len(va_s)}개, sr={sr}")
    va = collect(va_s, spec, cfg, dcfg)
    if not args.baseline_only:
        t0 = time.perf_counter()
        tr = collect(tr_s, spec, cfg, dcfg)
        print(f"패치: 학습 {len(tr['y'])} (클릭 {tr['y'].sum()}), 검증 {len(va['y'])} (클릭 {va['y'].sum()})"
              f" — {time.perf_counter() - t0:.0f}s")
        fit_cnn(tr, va, spec, args, out)

    # 신호처리 베이스라인 임계값 두 가지 (후보 SNR 로 근사 선택)
    #  - baseline: A 검증 세션으로 선택 (CNN 과 같은 데이터 조건)
    #  - baseline_day1: 설계서 v2 Day 1 게이트 — 두 조건의 1일차로 정하고 2–4일차에 고정
    day1 = collect([s for s in load_sessions(args.data) if s.day == 1 and s.split != "demo"], spec, cfg, dcfg)
    k_a, f1_a = pick_k(va)
    k_d1, f1_d1 = pick_k(day1)
    det = {"candidate_k": dcfg.candidate_k, "baseline_k": k_a, "baseline_k_day1": k_d1,
           "baseline_val_f1_by_k": f1_a, "baseline_day1_f1_by_k": f1_d1,
           "rule": f"F1 최고값에서 {K_TOLERANCE} 안쪽인 가장 작은 k"}
    (out / "detector.json").write_text(json.dumps(det, indent=2, ensure_ascii=False), encoding="utf-8")
    print(f"베이스라인 k: A 검증 기준 {k_a}, Day 1 게이트 {k_d1}  → {out}")


def fit_cnn(tr: dict, va: dict, spec: PatchSpec, args, out: Path) -> None:
    """CNN 학습 → 검증 F1 이 가장 높은 epoch 와 판정 임계값 저장."""
    torch.manual_seed(args.seed)
    rng = np.random.default_rng(args.seed)
    model = ClickCNN()
    opt = torch.optim.Adam(model.parameters(), lr=args.lr)
    pos, neg = tr["y"].sum(), (~tr["y"]).sum()
    loss_fn = nn.BCEWithLogitsLoss(pos_weight=torch.tensor(neg / max(pos, 1), dtype=torch.float32))
    Xva = torch.from_numpy(crop(va["X"], spec, None))
    yva = torch.from_numpy(va["y"].astype(np.float32))
    history, best = [], (-1.0, None)
    for ep in range(1, args.epochs + 1):
        model.train()
        order = rng.permutation(len(tr["y"]))
        tot = 0.0
        for i in range(0, len(order), args.batch):
            b = order[i:i + args.batch]
            xb = crop(tr["X"][b], spec, rng)
            # 증강: 일반 백색 잡음만(B 수조의 기포 소리는 쓰지 않는다)
            noisy = rng.random(len(b)) < 0.5
            amp = np.abs(xb).max(1, keepdims=True) * rng.uniform(0, 0.2, (len(b), 1))
            xb = xb + noisy[:, None] * amp * rng.standard_normal(xb.shape).astype(np.float32)
            logits = model(spec.spectrogram(torch.from_numpy(xb.astype(np.float32))))
            loss = loss_fn(logits, torch.from_numpy(tr["y"][b].astype(np.float32)))
            opt.zero_grad()
            loss.backward()
            opt.step()
            tot += loss.item() * len(b)
        model.eval()
        with torch.no_grad():
            lv = model(spec.spectrogram(Xva))
            vloss = float(nn.functional.binary_cross_entropy_with_logits(lv, yva))
            prob = torch.sigmoid(lv).numpy()
        m = session_f1(prob, va["y"], va["n_truth"], 0.5)
        history.append({"epoch": ep, "train_loss": round(tot / len(order), 5), "val_loss": round(vloss, 5),
                        "val_f1": round(m.f1, 4), "val_precision": round(m.precision, 4),
                        "val_recall": round(m.recall, 4)})
        print(f"  epoch {ep}: train_loss={history[-1]['train_loss']:.4f} val_loss={vloss:.4f} "
              f"val F1={m.f1:.4f} (P={m.precision:.4f} R={m.recall:.4f})")
        if m.f1 > best[0]:
            best = (m.f1, {k: v.clone() for k, v in model.state_dict().items()}, prob)
    model.load_state_dict(best[1])
    prob = best[2]
    grid = np.round(np.arange(0.1, 0.96, 0.05), 2)
    f1s = [session_f1(prob, va["y"], va["n_truth"], t).f1 for t in grid]
    thr = float(grid[int(np.argmax(f1s))])
    print(f"판정 임계값 {thr} (검증 F1 {max(f1s):.4f})")
    clf = ClickClassifier(model, spec, thr)
    clf.save(out / "click_cnn.pt", {"history": history, "val_f1": round(max(f1s), 4),
                                    "train_sessions": tr["sessions"], "val_sessions": va["sessions"],
                                    "n_train_patches": int(len(tr["y"])), "n_train_clicks": int(pos),
                                    "augmentation": "white noise (p=0.5, ≤20% of patch peak), ±1 ms shift"})


def pick_k(d: dict) -> tuple[float, dict]:
    """임계값 배수 k 선택. F1 이 거의 평평하면 극단값으로 가지 않도록 최고값 근처에서 가장 작은 k."""
    f1 = {}
    for k in K_GRID:
        pred = d["snr"] >= k
        tp = int((pred & d["y"]).sum())
        f1[k] = from_counts(tp, int((pred & ~d["y"]).sum()), d["n_truth"] - tp).f1
    best = max(f1.values())
    k = min(k for k, v in f1.items() if v >= best - K_TOLERANCE)
    return k, {str(k): round(v, 4) for k, v in f1.items()}


def main(argv=None):
    ap = argparse.ArgumentParser(description="2단계 클릭 CNN 학습")
    ap.add_argument("--data", required=True)
    ap.add_argument("--out", default="artifacts")
    ap.add_argument("--epochs", type=int, default=6)
    ap.add_argument("--batch", type=int, default=256)
    ap.add_argument("--lr", type=float, default=1e-3)
    ap.add_argument("--seed", type=int, default=0)
    ap.add_argument("--baseline-only", action="store_true", help="CNN 은 그대로 두고 베이스라인 임계값만 다시 고름")
    train(ap.parse_args(argv))


if __name__ == "__main__":
    main()
