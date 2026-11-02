"""업로드·샘플 → 분석 → 실시간 이벤트 → 저장 결과."""

import numpy as np
from shrimp_ai.anomaly import build_baseline

from tests.conftest import wait_done, write_wav


def test_tanks_and_samples(client):
    tanks = client.get("/api/v1/tanks").json()
    assert [t["id"] for t in tanks] == ["A1", "A2", "A3", "B1", "B2", "B3"]
    assert {t["noise_condition"] for t in tanks} == {"blocked", "operating"}
    s = client.get("/api/v1/samples").json()
    assert [x["id"] for x in s] == ["demo_test_B1"] and s[0]["tank_id"] == "B1"


def test_sample_analysis_streams_events_and_saves(client):
    r = client.post("/api/v1/analyses/from-sample", json={"sample_id": "demo_test_B1", "speed": 0})
    assert r.status_code == 202
    aid = r.json()["id"]
    ev = wait_done(client, aid)
    kinds = [e["type"] for e in ev]
    assert kinds[0] == "meta" and kinds[-1] == "done"
    assert {"clicks", "minute", "progress", "final", "insight"} <= set(kinds)
    clicks = sum(len(e["t"]) for e in ev if e["type"] == "clicks")
    assert clicks >= 50                                  # 20초에 초당 3회
    ins = next(e for e in ev if e["type"] == "insight")
    assert ins["source"] == "template" and ins["content"]["summary"]

    d = client.get(f"/api/v1/analyses/{aid}").json()
    assert d["status"] == "done" and d["n_clicks"] == clicks and len(d["minutes"]) == 40
    assert d["insight"]["source"] == "template" and d["max_grade"] is None   # 정상 기준 없음 → 등급 없음
    # 끝난 분석에 늦게 연결하면 같은 이벤트를 처음부터 다시 받는다
    again = wait_done(client, aid)
    assert [e["type"] for e in again] == kinds


def test_upload_validation(client, tmp_path):
    f = tmp_path / "a.txt"
    f.write_text("x")
    r = client.post("/api/v1/analyses", data={"tank_id": "A1"}, files={"file": ("a.txt", f.open("rb"), "text/plain")})
    assert r.status_code == 400 and r.json()["error"]["code"] == "invalid_audio"
    w = tmp_path / "a.wav"
    write_wav(w, seconds=3)
    r = client.post("/api/v1/analyses", data={"tank_id": "Z9"}, files={"file": ("a.wav", w.open("rb"), "audio/wav")})
    assert r.status_code == 404 and r.json()["error"]["code"] == "tank_not_found"
    r = client.post("/api/v1/analyses", data={"tank_id": "A1", "feeding_offset_sec": "10"},
                    files={"file": ("a.wav", w.open("rb"), "audio/wav")})
    assert r.status_code == 422 and r.json()["error"]["code"] == "invalid_feeding_offset"
    r = client.post("/api/v1/analyses", data={"tank_id": "A1", "speed": "-1"},
                    files={"file": ("a.wav", w.open("rb"), "audio/wav")})
    assert r.status_code == 422 and r.json()["error"]["code"] == "invalid_speed"


def test_upload_with_baseline_scores_and_alerts(client, settings, tmp_path):
    """정상 기준이 있으면 점수·등급·비교표·알림이 생긴다. 클릭이 적은 녹음 → 경보."""
    normal = np.zeros(40, dtype=int)
    normal[:10] = 1
    normal[10:] = 400                     # 정상이라면 급이 후 분당 400회 (테스트용으로 과장)
    curves = [normal + i for i in range(4)]
    build_baseline(curves, "A1", ["n1", "n2", "n3", "n4"]).save(settings.ai_artifacts_dir / "baselines" / "A1.json")
    w = tmp_path / "quiet.wav"
    write_wav(w, seconds=20, clicks_per_sec=2)
    r = client.post("/api/v1/analyses", data={"tank_id": "A1", "feeding_offset_sec": "2", "speed": "0",
                                              "fed_at": "2026-10-28T09:00:00+09:00", "feed_amount_g": "100"},
                    files={"file": ("quiet.wav", w.open("rb"), "audio/wav")})
    assert r.status_code == 202
    aid = r.json()["id"]
    ev = wait_done(client, aid)
    meta = ev[0]
    assert meta["baseline"]["tank"] == "A1" and len(meta["baseline"]["lo"]) == 40
    assert any(e["type"] == "alert" and e["level"] == "alert" for e in ev)
    d = client.get(f"/api/v1/analyses/{aid}").json()
    assert d["max_grade"] == "alert" and d["comparison"] and d["alerts"]
    assert len(d["scores"]) == 30 and d["fed_at"].startswith("2026-10-28")
    alerts = client.get("/api/v1/alerts", params={"acknowledged": False}).json()
    assert alerts and alerts[0]["analysis_id"] == aid
    r = client.post(f"/api/v1/alerts/{alerts[0]['id']}/ack")
    assert r.json()["acknowledged"] is True
    assert client.get("/api/v1/alerts", params={"acknowledged": False}).json() == []
