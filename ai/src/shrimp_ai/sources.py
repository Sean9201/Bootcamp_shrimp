"""입력 소스: 오디오를 시간순 청크로 내보낸다.

실사용(하이드로폰)과 시연(파일 배속 재생)은 이 소스만 다르고, 그 뒤 분석 코드는 같다.
"""

from __future__ import annotations

import time
from collections.abc import Iterator
from pathlib import Path

import numpy as np
import soundfile as sf


class FileSource:
    """WAV 파일을 청크 단위로 읽는다. speed 를 주면 그 배속에 맞춰 기다린다(0 이면 최대 속도)."""

    def __init__(self, path: str | Path, chunk_sec: float = 1.0, speed: float = 0.0,
                 clock=time.monotonic, sleep=time.sleep):
        self.path = Path(path)
        info = sf.info(self.path)
        self.sr = info.samplerate
        self.duration_sec = info.duration
        self.chunk = int(round(chunk_sec * self.sr))
        self.speed = speed
        self._clock, self._sleep = clock, sleep

    def __iter__(self) -> Iterator[np.ndarray]:
        t0 = self._clock()
        done = 0
        with sf.SoundFile(self.path) as f:
            while True:
                x = f.read(self.chunk, dtype="float32", always_2d=True)
                if len(x) == 0:
                    return
                done += len(x)
                if self.speed > 0:
                    # 소리 시간 done/sr 을 speed 배로 재생했을 때의 목표 시각까지 기다린다
                    wait = t0 + done / self.sr / self.speed - self._clock()
                    if wait > 0:
                        self._sleep(wait)
                yield x[:, 0]


class LiveSource:
    """하이드로폰 실시간 입력 자리. 장비가 정해지면 구현한다(sounddevice 등)."""

    def __init__(self, *args, **kwargs):
        raise NotImplementedError("실시간 입력은 후속 단계. 시연은 FileSource(speed=...) 사용")
