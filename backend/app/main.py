from __future__ import annotations

import hashlib
import hmac
import importlib.metadata
import json
import os
import tempfile
import uuid
from contextlib import asynccontextmanager
from datetime import date
from pathlib import Path

from fastapi import Depends, FastAPI, File, Header, HTTPException, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, Response
from fastapi.staticfiles import StaticFiles
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db import SessionLocal, get_db, init_db
from app.evidence import EvidenceError, ParsedEvidence, parse_evidence
from app.models import AuditEvent, CorrectiveAction, Exercise, Finding, Observation, Source, utcnow
from app.pipeline import analyze_exercise
from app.reporting import make_report_pdf
from app.schemas import (
    ActionClosure,
    ActionReview,
    ActionUpdate,
    ExerciseCreate,
    FindingEdit,
    FindingReview,
    TranscriptIngest,
)

DEMO_REVIEWER_KEY = os.getenv("REVIEWER_KEY", "demo-reviewer")
MAX_FILE_SIZE = 15 * 1024 * 1024


@asynccontextmanager
async def lifespan(_app: FastAPI):
    init_db()
    if os.getenv("DEMO_SEED", "1").lower() in {"1", "true", "yes"}:
        with SessionLocal() as db:
            exercise = _seed_demo(db)
            analyze_exercise(db, exercise)
    yield


app = FastAPI(
    title="DrillLoop",
    version="0.1.0",
    description="Evidence-backed emergency exercise evaluation demo",
    lifespan=lifespan,
)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173", "http://127.0.0.1:5173"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

FRONTEND_DIST = Path(__file__).resolve().parents[2] / "frontend" / "dist"
if (FRONTEND_DIST / "assets").is_dir():
    app.mount("/assets", StaticFiles(directory=FRONTEND_DIST / "assets"), name="assets")


def _dump(value: object) -> str:
    return json.dumps(value, ensure_ascii=False)


def _load(value: str):
    return json.loads(value)


def _exercise_dict(row: Exercise) -> dict:
    return {
        "id": row.id,
        "title": row.title,
        "scenario": row.scenario,
        "exercise_date": row.exercise_date,
        "duration_minutes": row.duration_minutes,
        "objectives": _load(row.objectives_json),
        "criteria": _load(row.criteria_json),
        "evaluator_roles": _load(row.evaluator_roles_json),
        "participants": _load(row.participants_json),
        "expected_milestones": _load(row.milestones_json),
    }


def _require_reviewer(x_reviewer_key: str | None) -> None:
    if not x_reviewer_key or not hmac.compare_digest(x_reviewer_key, DEMO_REVIEWER_KEY):
        raise HTTPException(
            status_code=401,
            detail={
                "code": "REVIEWER_AUTH_REQUIRED",
                "message": "An authorized reviewer key is required for decisions and closure.",
            },
        )


def _audit(
    db: Session, exercise_id: str, actor: str, action: str, object_id: str, details: dict
) -> None:
    db.add(
        AuditEvent(
            id=str(uuid.uuid4()),
            exercise_id=exercise_id,
            actor=actor,
            action=action,
            object_id=object_id,
            details_json=_dump(details),
        )
    )


def _store_parsed(
    db: Session,
    exercise_id: str,
    filename: str,
    mime_type: str,
    parsed: ParsedEvidence,
    content_bytes: bytes,
) -> Source:
    source = Source(
        id=str(uuid.uuid4()),
        exercise_id=exercise_id,
        filename=Path(filename).name,
        kind=parsed.kind,
        mime_type=mime_type or "application/octet-stream",
        sha256=hashlib.sha256(content_bytes).hexdigest(),
        content_text=parsed.content_text,
        source_bytes=content_bytes,
        provenance_json=_dump(parsed.provenance),
    )
    db.add(source)
    db.flush()
    for item in parsed.observations:
        db.add(
            Observation(
                id=str(uuid.uuid4()),
                exercise_id=exercise_id,
                source_id=source.id,
                text=item.text,
                event_time_raw=item.event_time_raw,
                event_time_normalized=item.event_time_normalized,
                time_confidence=item.time_confidence,
                source_locator=item.source_locator,
                observation_type=item.observation_type,
                extraction_method=item.extraction_method,
                recognition_confidence=item.recognition_confidence,
            )
        )
    return source


def _seed_demo(db: Session) -> Exercise:
    existing = db.get(Exercise, "HOSP-PO-2026-01")
    if existing:
        return existing
    exercise = Exercise(
        id="HOSP-PO-2026-01",
        title="Night Shift: Extended Power Loss",
        scenario="Fictional regional hospital exercise: prolonged utility outage tests emergency power transfer, unit communications, timestamp accuracy, and patient-care continuity.",
        exercise_date="2026-10-16",
        duration_minutes=120,
        objectives_json=_dump(
            [
                {
                    "id": "OBJ-01",
                    "text": "Restore and confirm essential power circuits within 60 seconds of a primary supply interruption.",
                },
                {
                    "id": "OBJ-02",
                    "text": "Communicate outage status and obtain unit acknowledgement within three minutes.",
                },
                {
                    "id": "OBJ-03",
                    "text": "Activate patient-care continuity procedures and preserve medication cold-chain records.",
                },
                {
                    "id": "OBJ-04",
                    "text": "Capture and reconcile response start and arrival timestamps in the incident log.",
                },
            ]
        ),
        criteria_json=_dump(
            [
                "Evidence-backed observation",
                "Source timestamps reconciled",
                "Actions have owner and acceptance criteria",
            ]
        ),
        evaluator_roles_json=_dump(
            ["Facilities evaluator", "Clinical operations evaluator", "Communications evaluator"]
        ),
        participants_json=_dump(
            [
                "Hospital Incident Command",
                "Facilities Operations",
                "ICU team",
                "Communications Unit",
            ]
        ),
        milestones_json=_dump(
            [
                {
                    "id": "M-01",
                    "expected": "Essential circuits restored by 09:03",
                    "objective_id": "OBJ-01",
                },
                {
                    "id": "M-02",
                    "expected": "Unit acknowledgement by 09:06",
                    "objective_id": "OBJ-02",
                },
                {
                    "id": "M-03",
                    "expected": "Cold-chain procedure activated and logged",
                    "objective_id": "OBJ-03",
                },
            ]
        ),
    )
    db.add(exercise)
    db.flush()
    evidence_dir = Path(__file__).resolve().parents[2] / "demo" / "evidence"
    for file_name in ("control_room_log.csv", "evaluator_notes.txt", "transcript.json"):
        raw = (evidence_dir / file_name).read_bytes()
        mime = (
            "text/csv"
            if file_name.endswith(".csv")
            else "application/json"
            if file_name.endswith(".json")
            else "text/plain"
        )
        parsed = parse_evidence(file_name, mime, raw, date.fromisoformat(exercise.exercise_date))
        _store_parsed(db, exercise.id, file_name, mime, parsed, raw)
    db.commit()
    db.refresh(exercise)
    return exercise


@app.get("/api/health")
def health() -> dict:
    return {"status": "ok", "app": "DrillLoop", "mode": "local-first"}


@app.get("/", include_in_schema=False)
def frontend() -> Response:
    index = FRONTEND_DIST / "index.html"
    if index.is_file():
        return FileResponse(index)
    return Response(
        "Frontend bundle is not built. In development, run `cd frontend && npm run dev`.",
        media_type="text/plain",
        status_code=200,
    )


@app.get("/api/capabilities")
def capabilities() -> dict:
    model_dir = os.getenv("WHISPER_MODEL_PATH", "")
    asr_ready = False
    asr_version = None
    try:
        asr_version = importlib.metadata.version("faster-whisper")
        asr_ready = bool(model_dir and Path(model_dir).is_dir())
    except importlib.metadata.PackageNotFoundError:
        pass
    return {
        "asr": {
            "available": asr_ready,
            "package_version": asr_version,
            "model_path_configured": bool(model_dir and Path(model_dir).is_dir()),
            "note": "CPU int8 transcription is optional. A local model directory is required; diarization is not provided.",
        },
        "analysis": {
            "mode": "offline evidence rules + optional local Ollama action drafts",
            "cloud_api_required": False,
            "local_model_configured": bool(os.getenv("OLLAMA_MODEL", "").strip()),
            "local_model": os.getenv("OLLAMA_MODEL", "").strip() or None,
        },
        "review": {
            "required_key": True,
            "demo_key_hint": "demo-reviewer" if DEMO_REVIEWER_KEY == "demo-reviewer" else None,
        },
    }


@app.get("/api/exercises")
def list_exercises(db: Session = Depends(get_db)) -> list[dict]:
    rows = db.scalars(select(Exercise).order_by(Exercise.exercise_date.desc())).all()
    result = []
    for row in rows:
        result.append(
            {
                **_exercise_dict(row),
                "finding_count": len(
                    db.scalars(select(Finding).where(Finding.exercise_id == row.id)).all()
                ),
                "action_count": len(
                    db.scalars(
                        select(CorrectiveAction).where(CorrectiveAction.exercise_id == row.id)
                    ).all()
                ),
            }
        )
    return result


@app.post("/api/exercises", status_code=201)
def create_exercise(payload: ExerciseCreate, db: Session = Depends(get_db)) -> dict:
    if db.get(Exercise, payload.id):
        raise HTTPException(
            status_code=409,
            detail={"code": "EXERCISE_EXISTS", "message": "That exercise ID is already in use."},
        )
    exercise = Exercise(
        id=payload.id,
        title=payload.title,
        scenario=payload.scenario,
        exercise_date=payload.exercise_date.isoformat(),
        duration_minutes=payload.duration_minutes,
        objectives_json=_dump(payload.objectives),
        criteria_json=_dump(payload.criteria),
        evaluator_roles_json=_dump(payload.evaluator_roles),
        participants_json=_dump(payload.participants),
        milestones_json=_dump(payload.expected_milestones),
    )
    db.add(exercise)
    db.commit()
    return _exercise_dict(exercise)


@app.post("/api/demo/seed")
def seed_demo(db: Session = Depends(get_db)) -> dict:
    exercise = _seed_demo(db)
    analysis = analyze_exercise(db, exercise)
    return {"exercise_id": exercise.id, "analysis": analysis}


def _detail(db: Session, exercise: Exercise) -> dict:
    sources = db.scalars(
        select(Source).where(Source.exercise_id == exercise.id).order_by(Source.created_at)
    ).all()
    source_by_id = {source.id: source for source in sources}
    observations = db.scalars(
        select(Observation).where(Observation.exercise_id == exercise.id)
    ).all()
    observation_by_id = {observation.id: observation for observation in observations}
    source_fields = {s.id: {"source_id": s.id, "source_filename": s.filename} for s in sources}
    timeline = [
        {
            "id": row.id,
            "source_id": row.source_id,
            "source_filename": source_by_id[row.source_id].filename,
            "text": row.text,
            "event_time_raw": row.event_time_raw,
            "event_time_normalized": row.event_time_normalized,
            "time_confidence": row.time_confidence,
            "source_locator": row.source_locator,
            "observation_type": row.observation_type,
            "extraction_method": row.extraction_method,
            "recognition_confidence": row.recognition_confidence,
        }
        for row in observations
    ]
    timeline.sort(
        key=lambda row: (
            row["event_time_normalized"] is None,
            row["event_time_normalized"] or "",
            row["source_filename"],
            row["source_locator"],
        )
    )
    conflicts = []
    for row in observations:
        low = row.text.casefold()
        if "unresolved" in low and any(
            term in low for term in ("acknowledgement", "acknowledgment", "time")
        ):
            conflicts.append(
                {
                    "observation_id": row.id,
                    "source_id": row.source_id,
                    "source_filename": source_by_id[row.source_id].filename,
                    "source_locator": row.source_locator,
                    "description": "Evaluator timing conflict is explicitly marked unresolved: "
                    + row.text,
                }
            )
    findings_rows = db.scalars(
        select(Finding)
        .where(Finding.exercise_id == exercise.id)
        .order_by(Finding.category, Finding.created_at)
    ).all()
    findings = []
    for row in findings_rows:
        evidence_ids = _load(row.evidence_ids_json)
        evidence_labels = []
        cited_observations = [
            observation_by_id[item] for item in evidence_ids if item in observation_by_id
        ]
        for observation in cited_observations:
            source = source_by_id[observation.source_id]
            evidence_labels.append(
                f"{source.filename} · {observation.source_locator} · “{observation.text[:220]}”"
            )
        findings.append(
            {
                "id": row.id,
                "code": row.code,
                "title": row.title,
                "category": row.category,
                "objective_id": row.objective_id,
                "observation": row.observation,
                "interpretation": row.interpretation,
                "evidence_ids": evidence_ids,
                "evidence_labels": evidence_labels,
                "confidence": row.confidence,
                "status": row.status,
                "review_note": row.review_note,
                "reviewer": row.reviewer,
                "supporting_evidence": [
                    {
                        **source_fields[obs.source_id],
                        "observation_id": obs.id,
                        "source_locator": obs.source_locator,
                        "text": obs.text,
                        "event_time_normalized": obs.event_time_normalized,
                        "time_confidence": obs.time_confidence,
                    }
                    for obs in cited_observations
                ],
            }
        )
    actions_rows = db.scalars(
        select(CorrectiveAction)
        .where(CorrectiveAction.exercise_id == exercise.id)
        .order_by(CorrectiveAction.created_at)
    ).all()
    actions = [
        {
            "id": row.id,
            "finding_id": row.finding_id,
            "finding_title": next((f["title"] for f in findings if f["id"] == row.finding_id), ""),
            "title": row.title,
            "evidence_ids": _load(row.evidence_ids_json),
            "owner": row.owner,
            "priority": row.priority,
            "due_date": row.due_date,
            "acceptance_criteria": row.acceptance_criteria,
            "status": row.status,
            "reviewer_decision": row.reviewer_decision,
            "reviewer": row.reviewer,
            "closure_evidence": row.closure_evidence,
        }
        for row in actions_rows
    ]
    audit_rows = db.scalars(
        select(AuditEvent)
        .where(AuditEvent.exercise_id == exercise.id)
        .order_by(AuditEvent.created_at.desc())
    ).all()
    sources_data = [
        {
            "id": row.id,
            "filename": row.filename,
            "kind": row.kind,
            "mime_type": row.mime_type,
            "sha256": row.sha256,
            "provenance": _load(row.provenance_json),
            "observation_count": sum(1 for obs in observations if obs.source_id == row.id),
        }
        for row in sources
    ]
    return {
        "exercise": _exercise_dict(exercise),
        "sources": sources_data,
        "timeline": timeline,
        "timeline_conflicts": conflicts,
        "findings": findings,
        "actions": actions,
        "audit_events": [
            {
                "actor": row.actor,
                "action": row.action,
                "object_id": row.object_id,
                "details": _load(row.details_json),
                "created_at": row.created_at.isoformat(),
            }
            for row in audit_rows
        ],
    }


@app.get("/api/exercises/{exercise_id}")
def exercise_detail(exercise_id: str, db: Session = Depends(get_db)) -> dict:
    exercise = db.get(Exercise, exercise_id)
    if not exercise:
        raise HTTPException(
            status_code=404, detail={"code": "EXERCISE_NOT_FOUND", "message": "Exercise not found."}
        )
    return _detail(db, exercise)


@app.post("/api/exercises/{exercise_id}/evidence", status_code=201)
async def upload_evidence(
    exercise_id: str, files: list[UploadFile] = File(...), db: Session = Depends(get_db)
) -> dict:
    exercise = db.get(Exercise, exercise_id)
    if not exercise:
        raise HTTPException(status_code=404, detail="Exercise not found.")
    created = []
    for file in files:
        raw = await file.read(MAX_FILE_SIZE + 1)
        try:
            parsed = parse_evidence(
                file.filename or "evidence",
                file.content_type or "",
                raw,
                date.fromisoformat(exercise.exercise_date),
            )
        except EvidenceError as error:
            raise HTTPException(
                status_code=error.status_code,
                detail={"code": error.code, "message": error.message, "filename": file.filename},
            ) from error
        source = _store_parsed(
            db,
            exercise_id,
            file.filename or "evidence",
            file.content_type or "application/octet-stream",
            parsed,
            raw,
        )
        created.append(
            {
                "id": source.id,
                "filename": source.filename,
                "kind": source.kind,
                "observation_count": len(parsed.observations),
            }
        )
    db.commit()
    return {"sources": created, "message": f"Imported {len(created)} evidence file(s)."}


@app.post("/api/exercises/{exercise_id}/audio", status_code=201)
async def transcribe_audio(
    exercise_id: str, file: UploadFile = File(...), db: Session = Depends(get_db)
) -> dict:
    exercise = db.get(Exercise, exercise_id)
    if not exercise:
        raise HTTPException(status_code=404, detail="Exercise not found.")
    model_path = os.getenv("WHISPER_MODEL_PATH", "")
    try:
        from faster_whisper import WhisperModel
    except ImportError as exc:
        raise HTTPException(
            status_code=503,
            detail={
                "code": "ASR_UNAVAILABLE",
                "message": "Install requirements-asr.txt and configure WHISPER_MODEL_PATH to a local model folder.",
            },
        ) from exc
    if not model_path or not Path(model_path).is_dir():
        raise HTTPException(
            status_code=503,
            detail={
                "code": "ASR_MODEL_UNAVAILABLE",
                "message": "A local faster-whisper model directory is required; no model download is attempted.",
            },
        )
    raw = await file.read(MAX_FILE_SIZE + 1)
    if len(raw) > MAX_FILE_SIZE:
        raise HTTPException(
            status_code=413,
            detail={"code": "FILE_TOO_LARGE", "message": "Audio files are limited to 15 MB."},
        )
    if (file.filename or "").lower().rsplit(".", 1)[-1] not in {"wav", "mp3", "m4a", "flac", "ogg"}:
        raise HTTPException(
            status_code=415,
            detail={
                "code": "UNSUPPORTED_AUDIO",
                "message": "Use WAV, MP3, M4A, FLAC, or OGG audio.",
            },
        )
    try:
        with tempfile.NamedTemporaryFile(suffix=Path(file.filename or "audio.wav").suffix) as temp:
            temp.write(raw)
            temp.flush()
            model = WhisperModel(model_path, device="cpu", compute_type="int8")
            segments_iter, info = model.transcribe(temp.name, beam_size=5, vad_filter=True)
            segments = [
                {
                    "start": segment.start,
                    "end": segment.end,
                    "text": segment.text.strip(),
                    "confidence": None,
                }
                for segment in segments_iter
            ]
    except Exception as exc:
        raise HTTPException(
            status_code=422,
            detail={
                "code": "ASR_FAILED",
                "message": f"Local transcription failed: {type(exc).__name__}. Check model files and audio format.",
            },
        ) from exc
    model_version = importlib.metadata.version("faster-whisper")
    payload = {
        "model": f"faster-whisper {model_version} · {Path(model_path).name}",
        "language": info.language,
        "recording_started_at": None,
        "segments": segments,
        "uncertain_terms": [
            "Word-level confidence is not available in this integration; human transcript review required."
        ],
        "audio_sha256": hashlib.sha256(raw).hexdigest(),
    }
    json_bytes = json.dumps(payload, ensure_ascii=False).encode()
    parsed = parse_evidence(
        (Path(file.filename or "recording.wav").stem + ".json"),
        "application/json",
        json_bytes,
        date.fromisoformat(exercise.exercise_date),
    )
    parsed.kind = "transcript"
    source = _store_parsed(
        db, exercise_id, file.filename or "recording", file.content_type or "audio/*", parsed, raw
    )
    db.commit()
    return {
        "source_id": source.id,
        "filename": source.filename,
        "language": info.language,
        "model_version": model_version,
        "segment_count": len(segments),
        "warning": "Word confidence and speaker diarization are not provided; review transcript against audio.",
    }


@app.post("/api/exercises/{exercise_id}/transcripts", status_code=201)
def ingest_transcript(
    exercise_id: str, payload: TranscriptIngest, db: Session = Depends(get_db)
) -> dict:
    exercise = db.get(Exercise, exercise_id)
    if not exercise:
        raise HTTPException(status_code=404, detail="Exercise not found.")
    transcript_payload = {
        "model": payload.model_version,
        "language": payload.language,
        "segments": payload.segments or [{"start": 0, "end": 0, "text": payload.transcript}],
    }
    raw = json.dumps(transcript_payload, ensure_ascii=False).encode()
    parsed = parse_evidence(
        payload.source_name.rsplit(".", 1)[0] + ".json",
        "application/json",
        raw,
        date.fromisoformat(exercise.exercise_date),
    )
    parsed.kind = "transcript"
    source = _store_parsed(db, exercise_id, payload.source_name, "application/json", parsed, raw)
    db.commit()
    return {
        "source_id": source.id,
        "filename": source.filename,
        "observations": len(parsed.observations),
        "model_version": payload.model_version,
    }


@app.post("/api/exercises/{exercise_id}/analyze")
def analyze(exercise_id: str, db: Session = Depends(get_db)) -> dict:
    exercise = db.get(Exercise, exercise_id)
    if not exercise:
        raise HTTPException(status_code=404, detail="Exercise not found.")
    result = analyze_exercise(db, exercise)
    if "error" in result:
        raise HTTPException(
            status_code=422, detail={"code": result["error"], "message": result["message"]}
        )
    return result


@app.patch("/api/findings/{finding_id}")
def edit_finding(
    finding_id: str,
    payload: FindingEdit,
    x_reviewer_key: str | None = Header(default=None),
    db: Session = Depends(get_db),
) -> dict:
    _require_reviewer(x_reviewer_key)
    finding = db.get(Finding, finding_id)
    if not finding:
        raise HTTPException(status_code=404, detail="Finding not found.")
    if finding.status != "proposed":
        raise HTTPException(status_code=409, detail="Only proposed findings can be edited.")
    finding.title = payload.title
    finding.observation = payload.observation
    finding.interpretation = payload.interpretation
    finding.reviewer = payload.reviewer
    finding.updated_at = utcnow()
    _audit(db, finding.exercise_id, payload.reviewer, "finding_edited", finding.id, {})
    db.commit()
    return {"id": finding.id, "status": finding.status, "title": finding.title}


@app.post("/api/findings/{finding_id}/review")
def review_finding(
    finding_id: str,
    payload: FindingReview,
    x_reviewer_key: str | None = Header(default=None),
    db: Session = Depends(get_db),
) -> dict:
    _require_reviewer(x_reviewer_key)
    if payload.decision not in {"approved", "rejected"}:
        raise HTTPException(status_code=422, detail="Decision must be approved or rejected.")
    finding = db.get(Finding, finding_id)
    if not finding:
        raise HTTPException(status_code=404, detail="Finding not found.")
    if finding.status != "proposed":
        raise HTTPException(status_code=409, detail="This finding already has a reviewer decision.")
    finding.status = payload.decision
    finding.review_note = payload.note
    finding.reviewer = payload.reviewer
    finding.updated_at = utcnow()
    _audit(
        db,
        finding.exercise_id,
        payload.reviewer,
        f"finding_{payload.decision}",
        finding.id,
        {"note": payload.note},
    )
    db.commit()
    return {"id": finding.id, "status": finding.status, "reviewer": finding.reviewer}


@app.put("/api/actions/{action_id}")
def update_action(
    action_id: str,
    payload: ActionUpdate,
    x_reviewer_key: str | None = Header(default=None),
    db: Session = Depends(get_db),
) -> dict:
    _require_reviewer(x_reviewer_key)
    action = db.get(CorrectiveAction, action_id)
    if not action:
        raise HTTPException(status_code=404, detail="Corrective action not found.")
    if action.status == "closed":
        raise HTTPException(status_code=409, detail="Closed actions are immutable in this demo.")
    action.owner = payload.owner.strip() if payload.owner and payload.owner.strip() else None
    action.priority = payload.priority
    action.due_date = payload.due_date.isoformat() if payload.due_date else None
    action.acceptance_criteria = payload.acceptance_criteria
    action.reviewer = payload.reviewer
    action.updated_at = utcnow()
    _audit(
        db,
        action.exercise_id,
        payload.reviewer,
        "action_updated",
        action.id,
        {"owner": action.owner, "priority": action.priority, "due_date": action.due_date},
    )
    db.commit()
    return {"id": action.id, "owner": action.owner, "due_date": action.due_date}


@app.post("/api/actions/{action_id}/review")
def review_action(
    action_id: str,
    payload: ActionReview,
    x_reviewer_key: str | None = Header(default=None),
    db: Session = Depends(get_db),
) -> dict:
    _require_reviewer(x_reviewer_key)
    if payload.decision not in {"approved", "rejected"}:
        raise HTTPException(status_code=422, detail="Decision must be approved or rejected.")
    action = db.get(CorrectiveAction, action_id)
    if not action:
        raise HTTPException(status_code=404, detail="Corrective action not found.")
    finding = db.get(Finding, action.finding_id)
    if payload.decision == "approved" and (not action.owner or not action.due_date):
        raise HTTPException(
            status_code=422,
            detail={
                "code": "ACTION_INCOMPLETE",
                "message": "Set an accountable owner and due date before approving this action.",
            },
        )
    if payload.decision == "approved" and finding.status != "approved":
        raise HTTPException(
            status_code=409,
            detail={
                "code": "FINDING_NOT_APPROVED",
                "message": "Approve the linked finding before approving its corrective action.",
            },
        )
    if action.status == "closed":
        raise HTTPException(status_code=409, detail="Closed actions cannot be changed.")
    action.reviewer_decision = payload.decision
    action.status = "approved" if payload.decision == "approved" else "rejected"
    action.reviewer = payload.reviewer
    action.updated_at = utcnow()
    _audit(
        db,
        action.exercise_id,
        payload.reviewer,
        f"action_{payload.decision}",
        action.id,
        {"note": payload.note},
    )
    db.commit()
    return {"id": action.id, "status": action.status, "reviewer_decision": action.reviewer_decision}


@app.post("/api/actions/{action_id}/close")
def close_action(
    action_id: str,
    payload: ActionClosure,
    x_reviewer_key: str | None = Header(default=None),
    db: Session = Depends(get_db),
) -> dict:
    _require_reviewer(x_reviewer_key)
    action = db.get(CorrectiveAction, action_id)
    if not action:
        raise HTTPException(status_code=404, detail="Corrective action not found.")
    if action.reviewer_decision != "approved":
        raise HTTPException(status_code=409, detail="Only an approved action can be closed.")
    action.closure_evidence = payload.closure_evidence
    action.status = "closed"
    action.reviewer = payload.reviewer
    action.updated_at = utcnow()
    _audit(
        db,
        action.exercise_id,
        payload.reviewer,
        "action_closed",
        action.id,
        {"closure_evidence": payload.closure_evidence},
    )
    db.commit()
    return {"id": action.id, "status": action.status, "closure_evidence": action.closure_evidence}


@app.get("/api/exercises/{exercise_id}/report.pdf")
def report_pdf(exercise_id: str, db: Session = Depends(get_db)) -> Response:
    exercise = db.get(Exercise, exercise_id)
    if not exercise:
        raise HTTPException(status_code=404, detail="Exercise not found.")
    content = make_report_pdf(_detail(db, exercise))
    return Response(
        content=content,
        media_type="application/pdf",
        headers={"Content-Disposition": f'attachment; filename="{exercise_id}-AAR-IP.pdf"'},
    )


@app.get("/api/sources/{source_id}/download")
def download_source(source_id: str, db: Session = Depends(get_db)) -> Response:
    source = db.get(Source, source_id)
    if not source:
        raise HTTPException(status_code=404, detail="Source evidence not found.")
    payload = source.source_bytes
    media_type = source.mime_type
    if payload is None:
        payload = source.content_text.encode("utf-8")
        media_type = "text/plain; charset=utf-8"
    safe_filename = Path(source.filename).name.replace('"', "")
    return Response(
        content=payload,
        media_type=media_type,
        headers={"Content-Disposition": f'attachment; filename="{safe_filename}"'},
    )
