"""테스트용 짧은 합성 신호."""

import numpy as np
import pytest

SR = 48000


def make_clicks(times_sec, dur_sec, noise_rms=0.002, amp=0.15, seed=0, distractors=()):
    """11 kHz 감쇠 클릭을 times_sec 에 넣은 신호. distractors 는 (시각, 주파수) 저주파 방해음."""
    rng = np.random.default_rng(seed)
    x = rng.standard_normal(int(dur_sec * SR)).astype(np.float32) * noise_rms
    t = np.arange(int(0.004 * SR)) / SR
    click = (np.sin(2 * np.pi * 11000 * t) * np.exp(-t / 0.0005)).astype(np.float32)
    for c in times_sec:
        k = int(c * SR)
        x[k:k + len(click)] += amp * click
    for c, f in distractors:
        tone = (np.sin(2 * np.pi * f * t) * np.exp(-t / 0.002)).astype(np.float32)
        k = int(c * SR)
        x[k:k + len(tone)] += amp * tone
    return x


@pytest.fixture
def sr():
    return SR
