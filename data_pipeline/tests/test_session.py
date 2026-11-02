"""세션 메타 검증."""

import json

from shrimp_data.session import SessionMeta, load_session

OK = dict(session_id="2026-10-24_A_0900", tank="A", fed_at="2026-10-24T09:00:00+09:00",
          feeding_offset_sec=600, label="normal")


def test_valid_meta():
    assert SessionMeta(**OK).validate() == []


def test_invalid_meta():
    bad = SessionMeta(**{**OK, "fed_at": "2026-10-24T09:00:00", "feeding_offset_sec": -1,
                         "data_source": "x", "label": "good"})
    assert len(bad.validate()) == 4


def test_load_session(tmp_path):
    (tmp_path / "meta.json").write_text(json.dumps(OK), encoding="utf-8")
    meta, problems = load_session(tmp_path)
    assert meta.tank == "A" and problems == ["audio.wav 없음"]
