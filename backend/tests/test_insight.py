"""인사이트 그래프: 템플릿, 검증, 재생성, 대체."""

from app.services.insight import build_facts, run_insight, template, validate

FINAL = {"max_grade": "alert", "score": {"score": 6.9},
         "comparison": [
             {"metric": "peak_cpm", "normal_mean": 96.5, "normal_sd": 8.0, "current": 39, "change_pct": -59.6},
             {"metric": "auc10", "normal_mean": 601.5, "normal_sd": 50.0, "current": 201, "change_pct": -66.6},
             {"metric": "auc30", "normal_mean": 1240.0, "normal_sd": 90.0, "current": 500, "change_pct": -59.7},
             {"metric": "onset_min", "normal_mean": 2.0, "normal_sd": 0.0, "current": 4, "change_pct": 100.0},
             {"metric": "peak_min", "normal_mean": 4.3, "normal_sd": 0.5, "current": 9, "change_pct": 109.3}]}
ALERTS = [{"minute": 3, "level": "alert"}]
FACTS = build_facts(FINAL, ALERTS, "operating", 1.25, 2.0)


def test_facts_have_no_identifiers():
    s = str(FACTS)
    assert "B1" not in s and "wav" not in s and FACTS["condition"] == "운영 소음"
    assert FACTS["first_alert"] == {"minute_after_feeding": 4, "level": "경보"}


def test_template_passes_validation():
    t = template(FACTS)
    assert validate(t, FACTS) == []
    assert "점검" in t["recommendation"] and len(t["bullets"]) >= 2
    ok = template(build_facts({**FINAL, "max_grade": "normal"}, [], "operating", 1.25, 2.0))
    assert validate(ok, FACTS) == [] and "정상" in ok["summary"]


def test_validation_catches_cause_and_made_up_numbers():
    bad = {"summary": "질병 때문에 섭식이 줄었습니다.", "bullets": ["Peak 가 77회로 줄었습니다."], "recommendation": "점검하세요."}
    p = validate(bad, FACTS)
    assert any("금지 표현" in x for x in p) and any("77" in x for x in p)
    assert validate({"summary": "수온 저하로 인해 줄었습니다.", "bullets": ["확인해 주세요."], "recommendation": "점검"},
                    FACTS) == ["금지 표현: (으)로 인해/인한"]


def test_llm_retry_then_success():
    calls = []

    def llm(facts, feedback):
        calls.append(feedback)
        if len(calls) == 1:
            return {"summary": "감염이 의심됩니다.", "bullets": ["x"], "recommendation": "점검"}
        return {"summary": "섭식 반응이 정상보다 낮았습니다.", "bullets": ["최고 분당 클릭 수가 39회로 59.6% 낮습니다."],
                "recommendation": "다음 급이 전 수조 상태를 점검해 주세요."}
    r = run_insight(FACTS, llm, "gemini-test", max_retries=1)
    assert r["source"] == "gemini" and r["attempts"] == 2 and r["model"] == "gemini-test"
    assert calls[1] and "금지 표현" in calls[1][0]          # 두 번째 호출에 이전 문제를 알려 줌


def test_llm_failure_falls_back_to_template():
    def llm(facts, feedback):
        raise TimeoutError("network")
    r = run_insight(FACTS, llm, "gemini-test", max_retries=1)
    assert r["source"] == "template" and r["model"] is None and r["attempts"] == 2
    assert any("LLM 호출 실패" in p for p in r["problems"])
