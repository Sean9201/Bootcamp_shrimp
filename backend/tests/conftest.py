"""테스트용 앱: 임시 DB·업로드 폴더, 짧은 합성 샘플, 간이 정상 기준. 실제 모델·Gemini 는 쓰지 않는다."""

import json

import numpy as np
import pytest
import soundfile as sf
from fastapi.testclient import TestClient

from app.core.config import Settings
from app.main import create_app

SR = 48000


def write_wav(path, seconds=20.0, clicks_per_sec=3.0, seed=0):
    """11 kHz 감쇠 클릭이 든 짧은 WAV."""
    rng = np.random.default_rng(seed)
    x = rng.standard_normal(int(seconds * SR)).astype(np.float32) * 0.002
    t = np.arange(int(0.004 * SR)) / SR
    click = (np.sin(2 * np.pi * 11000 * t) * np.exp(-t / 0.0005)).astype(np.float32) * 0.15
    for c in np.arange(0.3, seconds - 0.1, 1 / clicks_per_sec):
        k = int(c * SR)
        x[k:k + len(click)] += click
    sf.write(path, x, SR, subtype="PCM_16")


@pytest.fixture
def settings(tmp_path):
    samples = tmp_path / "samples"
    d = samples / "demo_test_B1"
    d.mkdir(parents=True)
    write_wav(d / "audio.wav")
    (d / "meta.json").write_text(json.dumps({
        "session_id": "demo_test_B1", "tank": "B1", "noise_condition": "operating", "feeding_offset_sec": 5.0,
        "fed_at": "2026-10-28T09:00:00+09:00", "feed_amount_g": 100, "label": "normal",
        "synthetic": {"split": "demo"}}), encoding="utf-8")
    return Settings(data_dir=tmp_path / "data", ai_artifacts_dir=tmp_path / "artifacts", samples_dir=samples,
                    gemini_api_key=None, _env_file=None)


@pytest.fixture
def client(settings):
    with TestClient(create_app(settings)) as c:
        yield c


def wait_done(client, analysis_id, timeout=60):
    """분석이 끝날 때까지 이벤트 스트림을 읽고 이벤트 목록 반환."""
    events = []
    with client.stream("GET", f"/api/v1/analyses/{analysis_id}/events", timeout=timeout) as r:
        for line in r.iter_lines():
            if line.startswith("data: "):
                events.append(json.loads(line[6:]))
    return events
