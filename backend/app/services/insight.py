"""분석 결과 설명 문장(인사이트): LangGraph 로 생성 → 검증 → (재생성) → 템플릿 대체.

- LLM(Gemini)에는 집계 수치(facts)만 보낸다. 원본 음향·파일명·수조 ID 는 보내지 않는다.
- 검증: 원인·질병 단정 표현 금지, 수치는 facts 에 있는 값만, 형식(요약 1 + 근거 2–4 + 권고 1).
- 키가 없거나 LLM 이 실패·검증 탈락하면 템플릿 문장을 쓴다(시연이 끊기지 않게).
"""

from __future__ import annotations

import json
import re
from collections.abc import Callable
from typing import TypedDict

from langgraph.graph import END, StateGraph

GRADE_KO = {"normal": "정상", "watch": "주의", "alert": "경보"}
CONDITION_KO = {"blocked": "소음 차단", "operating": "운영 소음"}
METRIC_KO = {"peak_cpm": ("최고 분당 클릭 수(Peak)", "회"), "auc10": ("급이 후 첫 10분 누적 클릭 수(AUC)", "회"),
             "auc30": ("급이 후 30분 누적 클릭 수", "회"), "onset_min": ("반응 시작", "분"),
             "peak_min": ("최고점 도달", "분")}
# 원인·질병을 단정하는 표현 (계획안: 원인은 단정하지 않는다). '확인해' 같은 말은 걸리지 않게 패턴으로 본다
FORBIDDEN = {"원인": r"원인", "때문": r"때문", "(으)로 인해/인한": r"로\s*인(?:해|한)",
             **{w: re.escape(w) for w in ("질병", "질환", "감염", "바이러스", "세균", "흰반점", "WSSV", "EMS",
                                          "AHPND", "진단", "확진", "폐사")}}
ALWAYS_OK_NUMBERS = (10, 30)          # 분석 창 이름(첫 10분, 30분)

SYSTEM = (
    "당신은 흰다리새우 양식장의 급이 관리자를 돕는 모니터링 보조원입니다. "
    "수중 음향으로 센 새우 섭식 클릭 수를 정상 기준과 비교한 수치(JSON)를 받아 이번 급이를 설명합니다.\n"
    "규칙:\n"
    "1. 주어진 JSON 에 있는 숫자만 쓴다. 새 숫자를 계산하거나 지어내지 않는다.\n"
    "2. 질병·감염·폐사 등 원인을 추정하거나 언급하지 않는다. '원인', '때문', '인해' 같은 표현을 쓰지 않는다.\n"
    "3. 진단하지 않는다. 다음 급이 전 현장 점검을 권하는 수준까지만 쓴다.\n"
    "4. 초보 운영자도 이해하도록 쉬운 한국어 존댓말로 쓴다.\n"
    '5. 출력은 JSON 하나: {"summary": 한 문장, "bullets": 2~4개 문장 배열, "recommendation": 한 문장}'
)


def build_facts(final: dict, alerts: list[dict], noise_condition: str, watch: float, alert: float) -> dict:
    """엔진 최종 결과 → LLM 에 보낼 수치 요약(식별 정보 없음)."""
    score = final.get("score") or {}
    rows = []
    for r in final.get("comparison") or []:
        name, unit = METRIC_KO[r["metric"]]
        rows.append({"name": name, "unit": unit, "normal_mean": r["normal_mean"], "current": r["current"],
                     "change_pct": r["change_pct"]})
    first = alerts[0] if alerts else None
    return {
        "grade": GRADE_KO.get(final.get("max_grade"), "기준 없음") if rows else "기준 없음",
        "score": round(score.get("score", 0.0), 1) if score else None,
        "watch_threshold": watch, "alert_threshold": alert,
        "first_alert": {"minute_after_feeding": first["minute"] + 1, "level": GRADE_KO[first["level"]]}
        if first else None,
        "condition": CONDITION_KO.get(noise_condition, noise_condition),
        "metrics": rows,
    }


def template(f: dict) -> dict:
    """규칙 기반 문장(키가 없거나 LLM 이 실패할 때)."""
    g = f["grade"]
    summary = {"경보": "이번 급이의 섭식 반응이 정상 기준보다 뚜렷하게 낮았습니다.",
               "주의": "이번 급이의 섭식 반응이 정상 기준보다 다소 낮았습니다.",
               "정상": "이번 급이의 섭식 반응은 정상 범위 안에 있었습니다."}.get(
        g, "이 수조의 정상 기준이 없어 비교 없이 활동량만 기록했습니다.")
    bullets = []
    for m in f["metrics"]:
        if m["current"] is None or m["normal_mean"] is None or m["name"].startswith("급이 후 30분"):
            continue
        if m["unit"] == "분":
            diff = round(m["current"] - m["normal_mean"], 1)
            when = "늦었습니다" if diff > 0 else ("빨랐습니다" if diff < 0 else "같았습니다")
            bullets.append(f"{m['name']}은 급이 후 {m['current']}분으로 정상 평균 {m['normal_mean']}분보다 "
                           f"{abs(diff)}분 {when}." if diff else f"{m['name']}은 급이 후 {m['current']}분으로 정상 평균과 같았습니다.")
        elif m["change_pct"] is not None:
            way = "낮습니다" if m["change_pct"] < 0 else "높습니다"
            bullets.append(f"{m['name']}는 {m['current']}{m['unit']}로 정상 평균 {m['normal_mean']}{m['unit']}보다 "
                           f"{abs(m['change_pct'])}% {way}.")
    if f["first_alert"]:
        a = f["first_alert"]
        bullets.append(f"급이 후 {a['minute_after_feeding']}분에 처음 '{a['level']}' 등급이 되었습니다.")
    bullets = bullets[:4] or ["정상 기준과 비교할 수치가 없습니다."]
    rec = {"경보": "다음 급이 전에 잔여 사료와 수조 상태(수질, 급이 장치)를 직접 점검해 주세요.",
           "주의": "다음 급이에서 반응을 한 번 더 확인하고, 계속 낮으면 수조 상태를 점검해 주세요.",
           "정상": "지금의 급이 방식을 유지하면서 다음 급이도 같은 방법으로 확인해 주세요."}.get(
        g, "같은 수조의 정상 녹음을 모아 기준을 만든 뒤 비교해 주세요.")
    return {"summary": summary, "bullets": bullets, "recommendation": rec}


def _allowed_numbers(f: dict) -> list[float]:
    vals: list[float] = list(ALWAYS_OK_NUMBERS)
    for k in ("score", "watch_threshold", "alert_threshold"):
        if f.get(k) is not None:
            vals.append(float(f[k]))
    if f.get("first_alert"):
        vals.append(float(f["first_alert"]["minute_after_feeding"]))
    for m in f["metrics"]:
        for k in ("normal_mean", "current", "change_pct"):
            if m.get(k) is not None:
                vals.append(abs(float(m[k])))
        if m["current"] is not None and m["normal_mean"] is not None:
            vals.append(abs(float(m["current"]) - float(m["normal_mean"])))
    return vals


def validate(draft: dict | None, f: dict) -> list[str]:
    """문제 목록(비면 통과)."""
    if not isinstance(draft, dict):
        return ["JSON 객체가 아님"]
    p = []
    s, b, r = draft.get("summary"), draft.get("bullets"), draft.get("recommendation")
    if not isinstance(s, str) or not s.strip():
        p.append("summary 없음")
    if not isinstance(b, list) or not 1 <= len(b) <= 4 or not all(isinstance(x, str) and x.strip() for x in b):
        p.append("bullets 는 1–4개 문장")
    if not isinstance(r, str) or not r.strip():
        p.append("recommendation 없음")
    if p:
        return p
    text = " ".join([s, *b, r])
    bad = [w for w, pat in FORBIDDEN.items() if re.search(pat, text)]
    if bad:
        p.append(f"금지 표현: {', '.join(bad)}")
    allowed = _allowed_numbers(f)
    for tok in re.findall(r"\d+(?:\.\d+)?", text):
        v = float(tok)
        if not any(abs(v - a) <= max(0.51, 0.01 * a) for a in allowed):
            p.append(f"근거 없는 수치: {tok}")
    return p


class InsightState(TypedDict, total=False):
    facts: dict
    draft: dict | None
    last_problems: list[str]
    problems: list[str]          # 지금까지 걸린 문제 전부(기록용)
    attempts: int
    source: str


LLM = Callable[[dict, list[str]], dict]


def build_graph(llm: LLM | None, max_retries: int):
    """생성 → 검증 → 통과면 끝 / 재시도 남으면 다시 생성 / 아니면 템플릿."""

    def generate(s: InsightState) -> InsightState:
        if llm is None:
            return {"draft": template(s["facts"]), "source": "template"}
        n = s.get("attempts", 0) + 1
        try:
            return {"draft": llm(s["facts"], s.get("last_problems", [])), "attempts": n, "source": "gemini"}
        except Exception as e:  # 네트워크·키·형식 오류 → 검증 단계에서 탈락 처리
            return {"draft": None, "attempts": n, "source": "gemini",
                    "problems": s.get("problems", []) + [f"LLM 호출 실패: {type(e).__name__}: {str(e)[:120]}"]}

    def check(s: InsightState) -> InsightState:
        probs = validate(s.get("draft"), s["facts"])
        return {"last_problems": probs, "problems": s.get("problems", []) + probs}

    def fallback(s: InsightState) -> InsightState:
        return {"draft": template(s["facts"]), "source": "template"}

    def route(s: InsightState) -> str:
        if not s["last_problems"]:
            return "done"
        if s.get("source") == "gemini" and s.get("attempts", 0) <= max_retries:
            return "retry"
        return "fallback"

    g = StateGraph(InsightState)
    g.add_node("generate", generate)
    g.add_node("validate", check)
    g.add_node("fallback", fallback)
    g.set_entry_point("generate")
    g.add_edge("generate", "validate")
    g.add_conditional_edges("validate", route, {"done": END, "retry": "generate", "fallback": "fallback"})
    g.add_edge("fallback", END)
    return g.compile()


def make_gemini(api_key: str, model: str, timeout_sec: float, temperature: float) -> LLM:
    """Gemini 호출 함수. 이전 검증 문제가 있으면 고쳐 달라고 덧붙인다."""
    from google import genai
    from google.genai import types

    client = genai.Client(api_key=api_key, http_options=types.HttpOptions(timeout=int(timeout_sec * 1000)))
    cfg = types.GenerateContentConfig(system_instruction=SYSTEM, temperature=temperature,
                                      response_mime_type="application/json")

    def call(facts: dict, feedback: list[str]) -> dict:
        prompt = "이번 급이 분석 수치:\n" + json.dumps(facts, ensure_ascii=False, indent=1)
        if feedback:
            prompt += "\n\n이전 답변이 규칙을 어겼습니다. 다음 문제를 고쳐서 다시 쓰세요: " + "; ".join(feedback)
        r = client.models.generate_content(model=model, contents=prompt, config=cfg)
        return json.loads(r.text)
    return call


def run_insight(facts: dict, llm: LLM | None, model_name: str | None, max_retries: int) -> dict:
    """그래프 실행 → 저장할 결과."""
    out = build_graph(llm, max_retries).invoke({"facts": facts, "attempts": 0, "problems": []})
    return {"content": out["draft"], "source": out["source"], "model": model_name if out["source"] == "gemini" else None,
            "attempts": out.get("attempts", 0), "problems": out.get("problems", [])}
