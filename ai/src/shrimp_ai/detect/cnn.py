"""2단계 클릭 판정 CNN: 후보 최고점 주변 짧은 스펙트로그램 → 클릭 확률.

입력 길이·주파수 범위는 PatchConfig(초·Hz)로 정하고 샘플레이트에 맞춰 환산한다.
학습과 추론이 같은 spectrogram() 을 쓴다.
"""

from __future__ import annotations

import json
from dataclasses import asdict
from pathlib import Path

import numpy as np
import torch
from torch import nn

from shrimp_ai.config import PatchConfig


class PatchSpec:
    """샘플레이트별 패치·STFT 크기."""

    def __init__(self, sr: int, cfg: PatchConfig = PatchConfig()):
        self.sr, self.cfg = sr, cfg
        self.pre = int(round(cfg.pre_sec * sr))
        self.post = int(round(cfg.post_sec * sr))
        self.length = self.pre + self.post
        self.n_fft = int(round(cfg.n_fft_sec * sr))
        self.hop = int(round(cfg.hop_sec * sr))
        freqs = np.fft.rfftfreq(self.n_fft, 1 / sr)
        self.f_idx = np.flatnonzero((freqs >= cfg.f_low_hz) & (freqs <= min(cfg.f_high_hz, sr / 2)))
        self.window = torch.hann_window(self.n_fft)

    def cut(self, x: np.ndarray, index: int, offset: int = 0) -> np.ndarray | None:
        """배열 x(스트림 위치 offset 부터 시작)에서 index 주변 패치. 범위를 벗어나면 None."""
        s = index - offset - self.pre
        if s < 0 or s + self.length > len(x):
            return None
        return x[s: s + self.length]

    def spectrogram(self, patches: torch.Tensor) -> torch.Tensor:
        """(B, L) 파형 → (B, 1, F, T) 로그 파워, 패치별 중앙값(배경 수준)을 0 으로 맞춤."""
        s = torch.stft(patches, self.n_fft, self.hop, window=self.window, center=False, return_complex=True)
        p = torch.log10(s.abs() ** 2 + 1e-12)[:, torch.as_tensor(self.f_idx), :]
        med = p.flatten(1).median(dim=1).values[:, None, None]
        return (p - med).unsqueeze(1)


class ClickCNN(nn.Module):
    """합성곱 3층 + 전역 평균 풀링. 파라미터 약 2.4만 개.

    정규화는 GroupNorm: BatchNorm 은 학습(잡음 증강 섞인 배치)과 추론의 통계가 달라
    검증 성능이 epoch 마다 크게 흔들렸다.
    """

    def __init__(self):
        super().__init__()
        def block(i, o, pool):  # noqa: E306
            layers = [nn.Conv2d(i, o, 3, padding=1), nn.GroupNorm(4, o), nn.ReLU()]
            return layers + ([nn.MaxPool2d(2)] if pool else [])
        self.body = nn.Sequential(*block(1, 16, True), *block(16, 32, True), *block(32, 64, False),
                                  nn.AdaptiveAvgPool2d(1), nn.Flatten())
        self.head = nn.Linear(64, 1)

    def forward(self, x: torch.Tensor) -> torch.Tensor:
        return self.head(self.body(x)).squeeze(1)


class ClickClassifier:
    """학습된 CNN + 패치 설정 + 판정 임계값."""

    def __init__(self, model: ClickCNN, spec: PatchSpec, threshold: float = 0.5):
        self.model, self.spec, self.threshold = model.eval(), spec, threshold

    @torch.no_grad()
    def predict_proba(self, patches: np.ndarray, batch: int = 2048) -> np.ndarray:
        if len(patches) == 0:
            return np.empty(0)
        out = []
        for i in range(0, len(patches), batch):
            t = torch.from_numpy(np.ascontiguousarray(patches[i:i + batch], dtype=np.float32))
            out.append(torch.sigmoid(self.model(self.spec.spectrogram(t))).numpy())
        return np.concatenate(out)

    def save(self, path: str | Path, extra: dict | None = None) -> None:
        path = Path(path)
        path.parent.mkdir(parents=True, exist_ok=True)
        torch.save(self.model.state_dict(), path)
        meta = {"sr": self.spec.sr, "patch": asdict(self.spec.cfg), "threshold": self.threshold, **(extra or {})}
        path.with_suffix(".json").write_text(json.dumps(meta, ensure_ascii=False, indent=2), encoding="utf-8")

    @classmethod
    def load(cls, path: str | Path) -> "ClickClassifier":
        path = Path(path)
        meta = json.loads(path.with_suffix(".json").read_text(encoding="utf-8"))
        model = ClickCNN()
        model.load_state_dict(torch.load(path, map_location="cpu", weights_only=True))
        return cls(model, PatchSpec(meta["sr"], PatchConfig(**meta["patch"])), meta["threshold"])
