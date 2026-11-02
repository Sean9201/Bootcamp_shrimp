"""분석별 이벤트 기록. 분석 스레드가 쌓고, SSE 연결이 처음부터 따라 읽는다.

늦게 연결한 화면도 처음 이벤트부터 받으므로 그래프를 빠짐없이 그릴 수 있다.
"""

from __future__ import annotations

import threading
from dataclasses import dataclass, field


@dataclass
class EventLog:
    events: list[dict] = field(default_factory=list)
    closed: bool = False


class EventBus:
    """analysis_id → 이벤트 목록 (메모리, 서버 재시작 시 사라짐)."""

    def __init__(self):
        self._logs: dict[int, EventLog] = {}
        self._lock = threading.Lock()

    def open(self, analysis_id: int) -> None:
        with self._lock:
            self._logs[analysis_id] = EventLog()

    def publish(self, analysis_id: int, event: dict) -> None:
        with self._lock:
            log = self._logs.setdefault(analysis_id, EventLog())
            log.events.append(event)

    def close(self, analysis_id: int) -> None:
        with self._lock:
            self._logs.setdefault(analysis_id, EventLog()).closed = True

    def read(self, analysis_id: int, start: int) -> tuple[list[dict], bool, bool]:
        """start 번째 이후 이벤트, 끝났는지, 기록이 있는지."""
        with self._lock:
            log = self._logs.get(analysis_id)
            if log is None:
                return [], True, False
            return log.events[start:], log.closed, True
