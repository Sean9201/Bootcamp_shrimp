"""평가 지표: 허용오차 내 1:1 클릭 매칭 → Precision/Recall/F1."""

from dataclasses import dataclass

import numpy as np


@dataclass
class MatchResult:
    """매칭 결과."""

    tp: int
    fp: int
    fn: int
    precision: float
    recall: float
    f1: float


def match_clicks(truth_sec, pred_sec, tolerance_ms: float = 5.0) -> MatchResult:
    """정답·예측을 |Δt| ≤ tolerance 안에서 1:1 매칭(정렬 후 투포인터). 중복 검출은 FP.

    규약: 둘 다 비면 P=R=F1=1, 분모가 0인 비율은 0.
    """
    t = np.sort(np.asarray(truth_sec, dtype=float))
    p = np.sort(np.asarray(pred_sec, dtype=float))
    if len(t) == 0 and len(p) == 0:
        return MatchResult(0, 0, 0, 1.0, 1.0, 1.0)
    tol = tolerance_ms / 1000.0 + 1e-12
    i = j = tp = 0
    while i < len(t) and j < len(p):
        d = p[j] - t[i]
        if abs(d) <= tol:
            tp, i, j = tp + 1, i + 1, j + 1
        elif d < 0:
            j += 1
        else:
            i += 1
    fp, fn = len(p) - tp, len(t) - tp
    return from_counts(tp, fp, fn)


def from_counts(tp: int, fp: int, fn: int) -> MatchResult:
    """TP·FP·FN → 비율. 분모가 0이면 0."""
    prec = tp / (tp + fp) if tp + fp else 0.0
    rec = tp / (tp + fn) if tp + fn else 0.0
    f1 = 2 * prec * rec / (prec + rec) if prec + rec else 0.0
    return MatchResult(tp, fp, fn, prec, rec, f1)


def match_flags(truth_sec, pred_sec, tolerance_ms: float = 5.0) -> np.ndarray:
    """예측마다 정답과 1:1 매칭됐는지(bool, pred_sec 원래 순서). 학습 라벨 만들기용."""
    p = np.asarray(pred_sec, dtype=float)
    order = np.argsort(p)
    t = np.sort(np.asarray(truth_sec, dtype=float))
    tol = tolerance_ms / 1000.0 + 1e-12
    flags = np.zeros(len(p), dtype=bool)
    i = j = 0
    while i < len(t) and j < len(p):
        d = p[order[j]] - t[i]
        if abs(d) <= tol:
            flags[order[j]] = True
            i, j = i + 1, j + 1
        elif d < 0:
            j += 1
        else:
            i += 1
    return flags


def cpm_mae(truth_counts, pred_counts) -> float:
    """분당 클릭 수 평균 절대 오차."""
    return float(np.mean(np.abs(np.asarray(truth_counts, float) - np.asarray(pred_counts, float))))
