"""1단계 클릭 후보 검출(신호처리, 스트리밍).

대역통과 → 에너지 포락선 → 최근 몇 초의 잡음 수준 대비 임계값 → 최고점 → 불응기 병합.
모든 처리가 과거 샘플만 쓰므로 청크를 어떻게 자르든 결과가 같다(경계 처리 포함).
임계값 배수 k 를 크게 주면 이 단계만으로 신호처리 베이스라인 검출기가 된다.
"""

from __future__ import annotations

from collections import deque
from dataclasses import dataclass

import numpy as np
from scipy import signal

from shrimp_ai.config import DetectorConfig


@dataclass
class Candidate:
    """후보 하나. index 는 스트림 시작 기준 샘플 위치(에너지 최고점)."""

    index: int
    energy: float
    snr: float          # 최고점 에너지 / 잡음 에너지


class StreamingCandidateDetector:
    """청크를 순서대로 받아 후보를 내보낸다."""

    def __init__(self, sr: int, cfg: DetectorConfig = DetectorConfig(), k: float | None = None):
        self.sr, self.cfg = sr, cfg
        self.k = cfg.candidate_k if k is None else k
        hi = min(cfg.band_high_hz, 0.45 * sr)
        self.bp = signal.butter(cfg.filter_order, (cfg.band_low_hz, hi), btype="bandpass", fs=sr, output="sos")
        self.lp = signal.butter(2, cfg.envelope_lp_hz, btype="lowpass", fs=sr, output="sos")
        self.bp_zi = np.zeros((self.bp.shape[0], 2))
        self.lp_zi = np.zeros((self.lp.shape[0], 2))
        self.block = max(1, int(cfg.noise_block_sec * sr))
        self.noise_blocks: deque[float] = deque(maxlen=max(1, int(cfg.noise_history_sec / cfg.noise_block_sec)))
        self._block_parts: list[np.ndarray] = []   # 채우는 중인 블록의 포락선
        self.refractory = int(cfg.refractory_ms / 1000 * sr)
        self.pos = 0                       # 다음 청크의 시작 샘플
        self.pending: Candidate | None = None
        self.noise_energy: float | None = None     # 완료된 블록이 하나도 없으면 None(검출 안 함)
        self.run: list | None = None               # 진행 중인 임계값 초과 구간 [시작, 최고값, 최고 위치, 잡음]

    def _close_block(self) -> None:
        self.noise_blocks.append(float(np.median(np.concatenate(self._block_parts))))
        self._block_parts = []
        self.noise_energy = max(float(np.median(self.noise_blocks)), self.cfg.min_noise_energy)

    def _push(self, c: Candidate, out: list[Candidate]) -> None:
        """불응기 안의 최고점은 하나로(더 큰 쪽)."""
        if self.pending is None:
            self.pending = c
        elif c.index - self.pending.index <= self.refractory:
            if c.energy > self.pending.energy:
                self.pending = c
        else:
            out.append(self.pending)
            self.pending = c

    def _end_run(self, out: list[Candidate]) -> None:
        _, peak, idx, noise = self.run
        self._push(Candidate(idx, peak, peak / noise), out)
        self.run = None

    def _scan(self, seg: np.ndarray, start: int, out: list[Candidate]) -> None:
        """잡음 수준이 같은 구간(블록 하나 안)에서 초과 구간을 찾는다. 청크 경계를 넘는 구간은 이어 붙인다."""
        if self.noise_energy is None:
            return
        noise = self.noise_energy
        above = seg > noise * self.k
        if not above.any():
            if self.run is not None:
                self._end_run(out)
            return
        edges = np.diff(np.concatenate([[0], above.astype(np.int8), [0]]))
        starts, ends = np.flatnonzero(edges == 1), np.flatnonzero(edges == -1)
        if self.run is not None and starts[0] != 0:
            self._end_run(out)
        for s, t in zip(starts, ends):
            i = s + int(np.argmax(seg[s:t]))
            if self.run is None:
                self.run = [start + s, float(seg[i]), start + i, noise]
            elif seg[i] > self.run[1]:
                self.run[1:] = [float(seg[i]), start + i, noise]
            if t < len(seg):
                self._end_run(out)

    def process(self, x: np.ndarray) -> list[Candidate]:
        """청크 하나 처리 → 확정된 후보(이후 청크와 합쳐질 수 없는 것)만 반환.

        임계값은 '이미 끝난 잡음 블록들'로만 정하고 블록 경계(전역 위치)에서만 바뀐다.
        그래서 청크를 어떻게 자르든 같은 결과가 나온다.
        """
        y, self.bp_zi = signal.sosfilt(self.bp, x, zi=self.bp_zi)
        e, self.lp_zi = signal.sosfilt(self.lp, y * y, zi=self.lp_zi)
        out: list[Candidate] = []
        i = 0
        while i < len(e):
            g = self.pos + i
            j = min(len(e), (g // self.block + 1) * self.block - self.pos)
            self._scan(e[i:j], g, out)
            self._block_parts.append(e[i:j])
            if (self.pos + j) % self.block == 0:
                self._close_block()
            i = j
        self.pos += len(x)
        hold = self.run is not None and self.run[0] - (self.pending.index if self.pending else 0) <= self.refractory
        if self.pending is not None and not hold and self.pos - self.pending.index > self.refractory:
            out.append(self.pending)
            self.pending = None
        return out

    def flush(self) -> list[Candidate]:
        """스트림 끝: 남은 후보 확정."""
        out: list[Candidate] = []
        if self.run is not None:
            self._end_run(out)
        if self.pending is not None:
            out.append(self.pending)
        self.pending = None
        return out


def detect_all(x: np.ndarray, sr: int, chunk_sec: float = 1.0, cfg: DetectorConfig = DetectorConfig(),
               k: float | None = None) -> list[Candidate]:
    """배열 전체를 청크로 나눠 순서대로 처리(평가·학습용 편의 함수)."""
    det = StreamingCandidateDetector(sr, cfg, k)
    n = int(chunk_sec * sr)
    out: list[Candidate] = []
    for i in range(0, len(x), n):
        out += det.process(x[i:i + n])
    return out + det.flush()
