"""분석 요청 만들기(업로드·샘플), 조회용 직렬화."""

from __future__ import annotations

import json
import shutil
import uuid
from datetime import datetime, timedelta, timezone
from pathlib import Path

import soundfile as sf
from fastapi import UploadFile
from sqlalchemy.orm import Session

from app.core.config import Settings
from app.core.errors import ApiError
from app.db.models import Analysis, Tank

COPY_CHUNK = 4 * 1024 * 1024
KST = timezone(timedelta(hours=9))


def to_utc(dt: datetime | None) -> datetime | None:
    """저장은 UTC. 시간대 없이 들어온 입력은 한국 시간으로 본다."""
    if dt is None:
        return None
    return (dt if dt.tzinfo else dt.replace(tzinfo=KST)).astimezone(timezone.utc)


def iso(dt: datetime | None) -> str | None:
    """응답은 항상 시간대 포함 ISO8601 (SQLite 는 시간대를 버리므로 UTC 로 붙인다)."""
    if dt is None:
        return None
    return (dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)).isoformat()


def check_speed(speed: float | None, s: Settings) -> float:
    v = s.default_speed if speed is None else float(speed)
    if not 0 <= v <= s.max_speed:
        raise ApiError(422, "invalid_speed", f"배속은 0–{s.max_speed:g} 사이여야 합니다.", {"speed": speed})
    return v


def get_tank(db: Session, tank_id: str) -> Tank:
    t = db.get(Tank, tank_id)
    if t is None:
        raise ApiError(404, "tank_not_found", f"수조 '{tank_id}' 가 없습니다.")
    return t


def wav_info(path: Path):
    try:
        info = sf.info(path)
    except Exception:
        raise ApiError(400, "invalid_audio", "WAV 파일을 읽을 수 없습니다.") from None
    if info.channels < 1 or info.frames == 0:
        raise ApiError(400, "invalid_audio", "비어 있는 오디오입니다.")
    return info


def save_upload(file: UploadFile, s: Settings) -> Path:
    """업로드 파일을 크기 제한을 지키며 data/uploads 에 저장."""
    if not (file.filename or "").lower().endswith(".wav"):
        raise ApiError(400, "invalid_audio", "WAV 파일만 올릴 수 있습니다.")
    s.upload_dir.mkdir(parents=True, exist_ok=True)
    dst = s.upload_dir / f"{uuid.uuid4().hex}.wav"
    limit, n = s.max_upload_mb * 1024 * 1024, 0
    with open(dst, "wb") as out:
        while chunk := file.file.read(COPY_CHUNK):
            n += len(chunk)
            if n > limit:
                out.close()
                dst.unlink(missing_ok=True)
                raise ApiError(413, "file_too_large", f"파일이 {s.max_upload_mb} MB 를 넘습니다.")
            out.write(chunk)
    return dst


def create_from_upload(db: Session, s: Settings, file: UploadFile, tank_id: str, fed_at: datetime | None,
                       feeding_offset_sec: float | None, feed_amount_g: float | None, speed: float | None) -> Analysis:
    tank = get_tank(db, tank_id)
    speed = check_speed(speed, s)
    path = save_upload(file, s)
    try:
        info = wav_info(path)
        offset = s.default_feeding_offset_sec if feeding_offset_sec is None else float(feeding_offset_sec)
        if not 0 <= offset < info.duration:
            raise ApiError(422, "invalid_feeding_offset", "급이 시각이 녹음 범위 밖입니다.",
                           {"feeding_offset_sec": offset, "duration_sec": round(info.duration, 1)})
    except ApiError:
        path.unlink(missing_ok=True)
        raise
    a = Analysis(tank_id=tank.id, source="upload", original_filename=file.filename, file_path=str(path.resolve()),
                 sample_rate=info.samplerate, duration_sec=info.duration, fed_at=to_utc(fed_at),
                 feeding_offset_sec=offset, feed_amount_g=feed_amount_g, speed=speed)
    db.add(a)
    db.commit()
    return a


def list_samples(s: Settings) -> list[dict]:
    """시연용 샘플 세션(합성). 라벨은 화면 안내용으로만 보여 준다."""
    root = Path(s.samples_dir)
    out = []
    if not root.is_dir():
        return out
    for d in sorted(root.iterdir()):
        m = d / "meta.json"
        if not (m.is_file() and (d / "audio.wav").is_file()):
            continue
        meta = json.loads(m.read_text(encoding="utf-8"))
        if (meta.get("synthetic") or {}).get("split") != s.sample_split:
            continue
        out.append({"id": meta["session_id"], "tank_id": meta["tank"], "noise_condition": meta["noise_condition"],
                    "label": meta.get("label"), "feeding_offset_sec": meta["feeding_offset_sec"],
                    "fed_at": meta.get("fed_at"), "feed_amount_g": meta.get("feed_amount_g"),
                    "size_mb": round((d / "audio.wav").stat().st_size / 1e6, 1)})
    return out


def create_from_sample(db: Session, s: Settings, sample_id: str, speed: float | None) -> Analysis:
    sample = next((x for x in list_samples(s) if x["id"] == sample_id), None)
    if sample is None:
        raise ApiError(404, "sample_not_found", f"샘플 '{sample_id}' 가 없습니다.")
    tank = get_tank(db, sample["tank_id"])
    path = Path(s.samples_dir) / sample_id / "audio.wav"
    info = wav_info(path)
    fed_at = to_utc(datetime.fromisoformat(sample["fed_at"])) if sample.get("fed_at") else None
    a = Analysis(tank_id=tank.id, source="sample", original_filename=f"{sample_id}.wav", file_path=str(path.resolve()),
                 sample_rate=info.samplerate, duration_sec=info.duration, fed_at=fed_at,
                 feeding_offset_sec=float(sample["feeding_offset_sec"]), feed_amount_g=sample.get("feed_amount_g"),
                 speed=check_speed(speed, s))
    db.add(a)
    db.commit()
    return a


def summary(a: Analysis) -> dict:
    """목록용."""
    return {"id": a.id, "tank_id": a.tank_id, "source": a.source, "filename": a.original_filename,
            "status": a.status, "speed": a.speed, "duration_sec": round(a.duration_sec, 1),
            "fed_at": iso(a.fed_at), "feed_amount_g": a.feed_amount_g,
            "created_at": iso(a.created_at), "max_grade": a.max_grade, "final_score": a.final_score,
            "peak_cpm": (a.metrics or {}).get("peak_cpm"), "auc10": (a.metrics or {}).get("auc10"),
            "error": a.error}


def detail(a: Analysis, band: dict | None) -> dict:
    """상세: 분 단위 곡선·점수·알림·인사이트 포함(완료 후 화면 다시 열 때)."""
    return {
        **summary(a), "noise_condition": a.tank.noise_condition, "feeding_offset_sec": a.feeding_offset_sec,
        "sample_rate": a.sample_rate, "started_at": iso(a.started_at), "finished_at": iso(a.finished_at),
        "metrics": a.metrics, "comparison": a.comparison, "baseline": band, "n_clicks": a.n_clicks,
        "compute_sec": a.compute_sec,
        "minutes": [{"minute": p.minute, "cpm": p.cpm, "mu": p.mu, "lo": p.lo, "hi": p.hi} for p in a.minutes],
        "scores": [{k: getattr(p, k) for k in ("minute", "score", "grade", "raw_grade", "z_auc", "z_peak",
                                                "z_onset", "stage")} for p in a.scores],
        "alerts": [alert_out(x) for x in a.alerts],
        "insight": None if a.insight is None else {
            "source": a.insight.source, "model": a.insight.model, **a.insight.content,
            "attempts": a.insight.attempts, "problems": a.insight.problems},
    }


def alert_out(x) -> dict:
    return {"id": x.id, "analysis_id": x.analysis_id, "tank_id": x.tank_id, "minute": x.minute, "level": x.level,
            "score": x.score, "stage": x.stage, "created_at": iso(x.created_at), "acknowledged": x.acknowledged}
