"""REST API v1. 로직은 services 에 두고 여기서는 입력 받기·호출·응답만 한다."""

from __future__ import annotations

import asyncio
import json
from datetime import datetime

from fastapi import APIRouter, Depends, File, Form, Query, Request, UploadFile
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.errors import ApiError
from app.db.models import Alert, Analysis, Tank
from app.services import analyses as svc
from app.services.runner import baseline_band

router = APIRouter(prefix="/api/v1")


def get_db(request: Request):
    with request.app.state.sessions() as db:
        yield db


def state(request: Request):
    return request.app.state


def _analysis(db: Session, analysis_id: int) -> Analysis:
    a = db.get(Analysis, analysis_id)
    if a is None:
        raise ApiError(404, "analysis_not_found", f"분석 {analysis_id} 이(가) 없습니다.")
    return a


# ---------------------------------------------------------------- 수조·샘플
@router.get("/tanks")
def list_tanks(db: Session = Depends(get_db), st=Depends(state)):
    """수조 목록과 정상 기준 유무."""
    return [{"id": t.id, "name": t.name, "noise_condition": t.noise_condition,
             "has_baseline": st.ai.baseline(t.id) is not None}
            for t in db.scalars(select(Tank).order_by(Tank.id))]


@router.get("/samples")
def list_samples(st=Depends(state)):
    """시연용 샘플 녹음(합성) 목록."""
    return svc.list_samples(st.settings)


# ---------------------------------------------------------------- 분석
@router.post("/analyses", status_code=202)
def create_analysis(file: UploadFile = File(...), tank_id: str = Form(...), fed_at: datetime | None = Form(None),
                    feeding_offset_sec: float | None = Form(None), feed_amount_g: float | None = Form(None),
                    speed: float | None = Form(None), db: Session = Depends(get_db), st=Depends(state)):
    """WAV 업로드 → 분석 시작(202). 진행은 /analyses/{id}/events 로 받는다."""
    a = svc.create_from_upload(db, st.settings, file, tank_id, fed_at, feeding_offset_sec, feed_amount_g, speed)
    st.runner.submit(a.id)
    return svc.summary(a)


class SampleRequest(BaseModel):
    sample_id: str = Field(..., description="샘플 ID (예: demo_abnormal_B1)")
    speed: float | None = Field(None, description="배속. 비우면 기본값(40)")


@router.post("/analyses/from-sample", status_code=202)
def create_from_sample(req: SampleRequest, db: Session = Depends(get_db), st=Depends(state)):
    """서버에 있는 샘플 녹음으로 분석 시작(시연 예비 경로: 큰 파일 업로드 없이)."""
    a = svc.create_from_sample(db, st.settings, req.sample_id, req.speed)
    st.runner.submit(a.id)
    return svc.summary(a)


@router.get("/analyses")
def list_analyses(limit: int = Query(50, ge=1, le=500), tank_id: str | None = None, db: Session = Depends(get_db)):
    q = select(Analysis).order_by(Analysis.id.desc()).limit(limit)
    if tank_id:
        q = q.where(Analysis.tank_id == tank_id)
    return [svc.summary(a) for a in db.scalars(q)]


@router.get("/analyses/{analysis_id}")
def get_analysis(analysis_id: int, db: Session = Depends(get_db), st=Depends(state)):
    a = _analysis(db, analysis_id)
    return svc.detail(a, baseline_band(st.ai.baseline(a.tank_id)))


@router.get("/analyses/{analysis_id}/events")
async def analysis_events(analysis_id: int, request: Request, db: Session = Depends(get_db), st=Depends(state)):
    """분석 진행 이벤트(SSE). 처음 이벤트부터 보내므로 늦게 연결해도 그래프를 빠짐없이 그린다.

    서버가 다시 켜져 이벤트 기록이 없으면 DB 상세를 snapshot 이벤트 하나로 보낸다.
    """
    a = _analysis(db, analysis_id)
    snapshot = svc.detail(a, baseline_band(st.ai.baseline(a.tank_id)))
    poll = st.settings.event_poll_sec

    async def gen():
        i = 0
        while True:
            evs, closed, exists = st.bus.read(analysis_id, i)
            if not exists:
                yield _sse({"type": "snapshot", **snapshot})
                yield _sse({"type": "done", "analysis_id": analysis_id})
                return
            for e in evs:
                yield _sse(e)
            i += len(evs)
            if closed and not evs:
                return
            if await request.is_disconnected():
                return
            await asyncio.sleep(poll)

    return StreamingResponse(gen(), media_type="text/event-stream",
                             headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"})


def _sse(e: dict) -> str:
    return f"data: {json.dumps(e, ensure_ascii=False)}\n\n"


# ---------------------------------------------------------------- 알림·모델
@router.get("/alerts")
def list_alerts(acknowledged: bool | None = None, limit: int = Query(100, ge=1, le=1000),
                db: Session = Depends(get_db)):
    q = select(Alert).order_by(Alert.id.desc()).limit(limit)
    if acknowledged is not None:
        q = q.where(Alert.acknowledged == acknowledged)
    return [svc.alert_out(x) for x in db.scalars(q)]


@router.post("/alerts/{alert_id}/ack")
def ack_alert(alert_id: int, db: Session = Depends(get_db)):
    x = db.get(Alert, alert_id)
    if x is None:
        raise ApiError(404, "alert_not_found", f"알림 {alert_id} 이(가) 없습니다.")
    x.acknowledged = True
    db.commit()
    return svc.alert_out(x)


@router.get("/model/report")
def model_report(st=Depends(state)):
    """모델 평가 리포트(ai/artifacts/eval_report.json). 모크 데이터 기준."""
    rep = st.ai.eval_report()
    if rep is None:
        raise ApiError(404, "report_not_found", "평가 리포트가 없습니다. ai 폴더에서 평가를 먼저 실행하세요.")
    a = rep["model_a"]
    return {"created_at": rep["created_at"], "note": rep["note"], "detector": rep["detector"],
            "model_a": {k: a[k] for k in ("A_val", "B_test_noise", "B_day2_4") if k in a},
            "mae_reduction_pct": a.get("mae_reduction_pct"), "speed_x": a.get("speed_x_cnn_median"),
            "model_b": {k: v for k, v in rep["model_b"].items() if k != "loo"},
            "conditions": rep.get("conditions"),
            "demo": [{k: d[k] for k in ("session_id", "label", "max_grade", "final_score", "alerts", "f1")}
                     for d in rep.get("demo", [])],
            "training": st.ai.training_info()}
