"""세션 메타 검증."""

import json

from shrimp_data.session import SessionMeta, load_session

OK = dict(session_id="2026-10-24_A1", tank="A1", noise_condition="blocked", day=1,
          fed_at="2026-10-24T09:00:00+09:00", feeding_offset_sec=600, label="normal")


def test_valid_meta():
    assert SessionMeta(**OK).validate() == []


def test_invalid_meta():
    bad = SessionMeta(**{**OK, "fed_at": "2026-10-24T09:00:00", "feeding_offset_sec": -1,
                         "data_source": "x", "label": "good", "noise_condition": "loud"})
    assert len(bad.validate()) == 5


def test_residual_feed_not_recovered_must_be_null():
    m = SessionMeta(**OK, residual_feed={"recovered": False, "dry_mass_g": 0, "reason": "유실"})
    assert len(m.validate()) == 1


def test_load_session_roundtrip(tmp_path):
    (tmp_path / "meta.json").write_text(SessionMeta(**OK).to_json(), encoding="utf-8")
    meta, problems = load_session(tmp_path)
    assert meta.tank == "A1" and meta.day == 1 and problems == ["audio.wav 없음"]


def test_load_session_ignores_unknown_keys(tmp_path):
    (tmp_path / "meta.json").write_text(json.dumps({**OK, "extra": 1}), encoding="utf-8")
    meta, _ = load_session(tmp_path)
    assert meta.session_id == OK["session_id"]
