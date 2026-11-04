from __future__ import annotations

import asyncio
import hashlib
import hmac
import importlib.metadata
import json
import logging
import os
import tempfile
import threading
import time
import uuid
from contextlib import asynccontextmanager
from datetime import date
from pathlib import Path

from fastapi import Depends, FastAPI, File, HTTPException, Request, Response, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse, PlainTextResponse
from fastapi.staticfiles import StaticFiles
from sqlalchemy import select, text
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session
from starlette.middleware.trustedhost import TrustedHostMiddleware

from app import db as database
from app.auth import (
    SESSION_COOKIE,
    SESSION_MAX_AGE,
    AuthConfigurationError,
    Identity,
    authenticate,
    configured_users,
    cookie_secure,
    create_session,
    current_identity,
    resolve_session,
    session_secret,
)
from app.db import SessionLocal, get_db, init_db
from app.evidence import EvidenceError, ParsedEvidence, parse_evidence, safe_filename
from app.limits import RequestBodyLimitMiddleware
from app.models import (
    AuditEvent,
    CorrectiveAction,
    Exercise,
    ExerciseGrant,
    Finding,
    Observation,
    Source,
    utcnow,
)
from app.observability import METRICS, CorrelationMiddleware, configure_logging
from app.pipeline import analyze_exercise, objective_assessments
from app.reporting import make_report_pdf
from app.runtime_config import comma_separated, validate_runtime_config
from app.schemas import (
    ActionClosure,
    ActionReview,
    ActionUpdate,
    ExerciseAccessGrant,
    ExerciseCreate,
    FindingEdit,
    FindingReview,
    LoginRequest,
    ObjectivesUpdate,
    TranscriptIngest,
)
from app.upload_processing import (
    ScanResult,
    UploadProcessingFailure,
    process_upload_isolated,
    scan_bytes_isolated,
    scanner_readiness,
)

MAX_FILE_SIZE = 15 * 1024 * 1024
MAX_EVIDENCE_FILES = 10
MAX_TOTAL_UPLOAD_SIZE = 30 * 1024 * 1024
MAX_REQUEST_BODY_SIZE = MAX_TOTAL_UPLOAD_SIZE + 1 * 1024 * 1024
READ_ROLES = {"admin", "evaluator", "reviewer", "viewer"}
EDIT_ROLES = {"admin", "evaluator"}
REVIEW_ROLES = {"admin", "reviewer"}
_LOGIN_FAILURES: dict[str, tuple[int, float]] = {}
_LOGIN_WINDOW_SECONDS = 60
_LOGIN_MAX_FAILURES = 8
logger = logging.getLogger("drillloop")
configure_logging()
APP_VERSION = os.getenv("DRILLLOOP_BUILD_VERSION", "0.1.0")
APP_REVISION = os.getenv("DRILLLOOP_BUILD_REVISION", "unknown")


@asynccontextmanager
async def lifespan(_app: FastAPI):
    validate_runtime_config()
    init_db()
    logger.info(
        "application_started", extra={"fields": {"version": APP_VERSION, "revision": APP_REVISION}}
    )
    if os.getenv("DEMO_SEED", "0").lower() in {"1", "true", "yes"}:
        with SessionLocal() as db:
            exercise = _seed_demo(db)
            analyze_exercise(db, exercise)
            demo_owner = os.getenv("DRILLLOOP_DEMO_OWNER_ID", "")
            try:
                user = configured_users().get(demo_owner)
            except AuthConfigurationError:
                user = None
            if user:
                _create_exercise_grant(db, exercise, _identity_from_user(user))
                db.commit()
    try:
        yield
    finally:
        logger.info("application_stopped", extra={"fields": {"version": APP_VERSION}})


app = FastAPI(
    title="DrillLoop",
    version=APP_VERSION,
    description="Evidence-backed emergency exercise evaluation demo",
    lifespan=lifespan,
)
app.add_middleware(
    CORSMiddleware,
    allow_origins=comma_separated(
        "DRILLLOOP_CORS_ORIGINS",
        ()
        if os.getenv("DRILLLOOP_ENVIRONMENT", "local").casefold() not in {"local", "test"}
        else ("http://localhost:5173", "http://127.0.0.1:5173"),
    ),
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["Content-Type", "X-CSRF-Token"],
)
app.add_middleware(RequestBodyLimitMiddleware, max_bytes=MAX_REQUEST_BODY_SIZE)
app.add_middleware(CorrelationMiddleware)
_trusted_hosts = comma_separated("DRILLLOOP_TRUSTED_HOSTS")
if _trusted_hosts:
    app.add_middleware(TrustedHostMiddleware, allowed_hosts=_trusted_hosts)

FRONTEND_DIST = Path(__file__).resolve().parents[2] / "frontend" / "dist"
if (FRONTEND_DIST / "assets").is_dir():
    app.mount("/assets", StaticFiles(directory=FRONTEND_DIST / "assets"), name="assets")


@app.post("/api/auth/login")
def auth_login(payload: LoginRequest, request: Request, response: Response) -> dict:
    remote = request.client.host if request.client else "unknown"
    attempt_key = f"{remote}:{payload.username.casefold()}"
    now = time.monotonic()
    failures, reset_at = _LOGIN_FAILURES.get(attempt_key, (0, now + _LOGIN_WINDOW_SECONDS))
    if reset_at <= now:
        failures, reset_at = 0, now + _LOGIN_WINDOW_SECONDS
    if failures >= _LOGIN_MAX_FAILURES:
        raise HTTPException(
            status_code=429,
            detail={
                "code": "LOGIN_RATE_LIMITED",
                "message": "Too many failed sign-in attempts. Try again later.",
            },
        )
    try:
        users = configured_users()
    except AuthConfigurationError as exc:
        raise HTTPException(
            status_code=503, detail={"code": "AUTH_CONFIGURATION_INVALID", "message": str(exc)}
        ) from exc
    if not users or session_secret() is None:
        raise HTTPException(
            status_code=503,
            detail={
                "code": "AUTH_NOT_CONFIGURED",
                "message": "Named-user authentication is not configured.",
            },
        )
    user = authenticate(payload.username, payload.password)
    if user is None:
        _LOGIN_FAILURES[attempt_key] = (failures + 1, reset_at)
        logger.warning("authentication_failed")
        raise HTTPException(
            status_code=401,
            detail={
                "code": "INVALID_CREDENTIALS",
                "message": "The username or password is incorrect.",
            },
        )
    _LOGIN_FAILURES.pop(attempt_key, None)
    logger.info("authentication_succeeded", extra={"fields": {"role": user["role"]}})
    try:
        token, identity = create_session(user)
    except AuthConfigurationError as exc:
        raise HTTPException(
            status_code=503, detail={"code": "AUTH_CONFIGURATION_INVALID", "message": str(exc)}
        ) from exc
    response.set_cookie(
        SESSION_COOKIE,
        token,
        max_age=SESSION_MAX_AGE,
        httponly=True,
        secure=cookie_secure(),
        samesite="lax",
        path="/",
    )
    return {"identity": identity.public_dict(), "csrf_token": identity.csrf_token}


@app.get("/api/auth/session")
def auth_session(identity: Identity = Depends(current_identity)) -> dict:
    return {"identity": identity.public_dict(), "csrf_token": identity.csrf_token}


@app.post("/api/auth/logout")
def auth_logout(response: Response, _identity: Identity = Depends(current_identity)) -> dict:
    response.delete_cookie(
        SESSION_COOKIE, path="/", secure=cookie_secure(), httponly=True, samesite="lax"
    )
    return {"status": "signed_out"}


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


@app.middleware("http")
async def csrf_protection(request: Request, call_next):
    if (
        request.method in {"POST", "PUT", "PATCH", "DELETE"}
        and request.url.path != "/api/auth/login"
    ):
        identity = resolve_session(request.cookies.get(SESSION_COOKIE))
        if identity and not hmac.compare_digest(
            request.headers.get("X-CSRF-Token", ""), identity.csrf_token
        ):
            response = JSONResponse(
                status_code=403,
                content={
                    "detail": {
                        "code": "CSRF_TOKEN_REQUIRED",
                        "message": "Refresh the authenticated session before retrying this request.",
                    }
                },
            )
            _observe_database_pool()
            return response
    response = await call_next(request)
    _observe_database_pool()
    return response


def _observe_database_pool() -> None:
    pool = database.engine.pool
    try:
        checked_out = int(pool.checkedout())
        size = int(pool.size())
        overflow = int(pool.overflow())
    except (AttributeError, TypeError, ValueError):
        return
    METRICS.observe_database_pool(checked_out, size, max(0, overflow))


def _identity_from_user(user: dict[str, str]) -> Identity:
    return Identity(
        user_id=user["id"],
        username=user["username"],
        name=user["name"],
        role=user["role"],
        organization_id=user["organization_id"],
        csrf_token="",
    )


def _require_role(identity: Identity, allowed: set[str]) -> None:
    if identity.role not in allowed:
        logger.warning("authorization_denied", extra={"fields": {"role": identity.role}})
        raise HTTPException(
            status_code=403,
            detail={
                "code": "ROLE_FORBIDDEN",
                "message": "Your account role cannot perform this action.",
            },
        )


def _create_exercise_grant(db: Session, exercise: Exercise, identity: Identity) -> None:
    existing = db.scalar(
        select(ExerciseGrant).where(
            ExerciseGrant.exercise_id == exercise.id,
            ExerciseGrant.user_id == identity.user_id,
            ExerciseGrant.organization_id == identity.organization_id,
        )
    )
    if existing is None:
        db.add(
            ExerciseGrant(
                id=str(uuid.uuid4()),
                exercise_id=exercise.id,
                user_id=identity.user_id,
                organization_id=identity.organization_id,
                access_role=identity.role,
            )
        )


def _exercise_for_user(
    db: Session, exercise_id: str, identity: Identity, allowed_roles: set[str]
) -> Exercise:
    _require_role(identity, allowed_roles)
    exercise = db.get(Exercise, exercise_id)
    if not exercise:
        raise HTTPException(status_code=404, detail="Exercise not found.")
    grant = db.scalar(
        select(ExerciseGrant.id).where(
            ExerciseGrant.exercise_id == exercise_id,
            ExerciseGrant.user_id == identity.user_id,
            ExerciseGrant.organization_id == identity.organization_id,
        )
    )
    if grant is None:
        raise HTTPException(status_code=404, detail="Exercise not found.")
    return exercise


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
    scan_status: str = "not_scanned",
) -> Source:
    source = Source(
        id=str(uuid.uuid4()),
        exercise_id=exercise_id,
        filename=safe_filename(filename),
        kind=parsed.kind,
        mime_type=mime_type or "application/octet-stream",
        sha256=hashlib.sha256(content_bytes).hexdigest(),
        content_text=parsed.content_text,
        source_bytes=content_bytes,
        provenance_json=_dump(parsed.provenance),
        scan_status=scan_status,
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
                    "evaluation_rule": {
                        "type": "elapsed_time",
                        "threshold_seconds": 60,
                        "start_terms": ["primary utility power supply failed"],
                        "completion_terms": ["essential circuits were restored"],
                        "finding_code": "POWER_RESTORATION_DELAY",
                        "finding_title": "Essential power restoration exceeded the exercise target",
                    },
                },
                {
                    "id": "OBJ-02",
                    "text": "Communicate outage status and obtain unit acknowledgement within three minutes.",
                    "evaluation_rule": {
                        "type": "elapsed_time",
                        "threshold_seconds": 180,
                        "start_terms": [
                            "request for each inpatient unit to acknowledge",
                            "outage acknowledgement was requested",
                        ],
                        "completion_terms": ["acknowledged the outage by runner"],
                        "completion_claim_terms": ["watch shows acknowledgement at"],
                        "finding_code": "COMMUNICATION_ACK_DELAY",
                        "finding_title": "Unit acknowledgement exceeded the three-minute objective",
                    },
                },
                {
                    "id": "OBJ-03",
                    "text": "Activate patient-care continuity procedures and preserve medication cold-chain records.",
                    "evaluation_rule": {
                        "type": "event_presence",
                        "terms": ["cold-chain relocation procedure"],
                        "finding_code": "COLD_CHAIN_PROCEDURE_COMPLETED",
                        "finding_title": "Emergency cold-chain procedure completed",
                    },
                },
                {
                    "id": "OBJ-04",
                    "text": "Capture and reconcile response start and arrival timestamps in the incident log.",
                    "evaluation_rule": {
                        "type": "reported_duration",
                        "start_terms": ["primary utility power supply failed"],
                        "completion_terms": ["facilities technician arrived at the switch room"],
                        "claim_terms": ["incident log recorded a facilities response time"],
                        "finding_code": "RESPONSE_TIME_DISCREPANCY",
                        "finding_title": "Reported response time conflicts with source timestamps",
                    },
                },
                {
                    "id": "OBJ-05",
                    "text": "Record an accountable owner for each improvement action.",
                    "evaluation_rule": {
                        "type": "required_field",
                        "field_terms": ["owner"],
                        "missing_terms": ["owner field was left blank"],
                        "finding_code": "ACTION_OWNER_MISSING",
                        "finding_title": "Improvement action owner is not recorded",
                    },
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


def _database_ready() -> None:
    try:
        with SessionLocal() as db:
            db.execute(text("SELECT 1"))
    except SQLAlchemyError as exc:
        raise HTTPException(
            status_code=503,
            detail={
                "code": "DATABASE_NOT_READY",
                "message": "The application database is not ready.",
            },
        ) from exc


@app.get("/api/live")
def live() -> dict:
    return {"status": "live"}


@app.get("/api/ready")
def readiness() -> dict:
    _database_ready()
    scanner = None
    if os.getenv("DRILLLOOP_UPLOAD_SCAN_MODE", "disabled").casefold() == "required":
        try:
            scanner = scanner_readiness()
        except UploadProcessingFailure as exc:
            raise HTTPException(
                status_code=503,
                detail={"code": exc.code, "message": exc.message},
            ) from exc
    return {
        "status": "ready",
        "app": "DrillLoop",
        "version": APP_VERSION,
        "revision": APP_REVISION,
        "mode": "local-first",
        "scanner": scanner,
    }


@app.get("/api/health")
def health() -> dict:
    return readiness()


@app.get("/api/metrics", response_class=PlainTextResponse)
def metrics(identity: Identity = Depends(current_identity)) -> Response:
    _require_role(identity, {"admin"})
    return PlainTextResponse(METRICS.prometheus(), media_type="text/plain; version=0.0.4")


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
            "mode": "offline deterministic objective rules",
            "cloud_api_required": False,
        },
        "review": {
            "required_identity": True,
            "review_roles": ["admin", "reviewer"],
        },
        "synthetic_demo_seed_enabled": os.getenv("DRILLLOOP_ENABLE_DEMO_SEED", "0").casefold()
        in {"1", "true", "yes"},
    }


@app.get("/api/exercises")
def list_exercises(
    identity: Identity = Depends(current_identity), db: Session = Depends(get_db)
) -> list[dict]:
    grant_ids = select(ExerciseGrant.exercise_id).where(
        ExerciseGrant.user_id == identity.user_id,
        ExerciseGrant.organization_id == identity.organization_id,
    )
    rows = db.scalars(
        select(Exercise).where(Exercise.id.in_(grant_ids)).order_by(Exercise.exercise_date.desc())
    ).all()
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
def create_exercise(
    payload: ExerciseCreate,
    identity: Identity = Depends(current_identity),
    db: Session = Depends(get_db),
) -> dict:
    _require_role(identity, EDIT_ROLES)
    if db.get(Exercise, payload.id):
        grant = db.scalar(
            select(ExerciseGrant.id).where(
                ExerciseGrant.exercise_id == payload.id,
                ExerciseGrant.user_id == identity.user_id,
                ExerciseGrant.organization_id == identity.organization_id,
            )
        )
        if grant is None:
            raise HTTPException(status_code=404, detail="Exercise not found.")
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
    db.flush()
    _create_exercise_grant(db, exercise, identity)
    _audit(db, exercise.id, identity.name, "exercise_created", exercise.id, {})
    db.commit()
    return _exercise_dict(exercise)


@app.put("/api/exercises/{exercise_id}/objectives")
def update_objectives(
    exercise_id: str,
    payload: ObjectivesUpdate,
    identity: Identity = Depends(current_identity),
    db: Session = Depends(get_db),
) -> dict:
    exercise = _exercise_for_user(db, exercise_id, identity, EDIT_ROLES)
    has_findings = (
        db.scalar(select(Finding.id).where(Finding.exercise_id == exercise_id).limit(1)) is not None
    )
    has_analysis = (
        db.scalar(
            select(AuditEvent.id)
            .where(AuditEvent.exercise_id == exercise_id, AuditEvent.action == "analysis_completed")
            .limit(1)
        )
        is not None
    )
    if has_findings or has_analysis:
        raise HTTPException(
            status_code=409,
            detail={
                "code": "OBJECTIVES_LOCKED_AFTER_ANALYSIS",
                "message": "Objectives are locked after analysis starts. Create a new exercise to preserve prior findings and reviewer decisions.",
            },
        )
    exercise.objectives_json = _dump(payload.objectives)
    exercise.criteria_json = _dump(payload.criteria)
    _audit(
        db,
        exercise.id,
        identity.name,
        "objectives_updated",
        exercise.id,
        {"objective_count": len(payload.objectives)},
    )
    db.commit()
    return _exercise_dict(exercise)


@app.get("/api/configured-users")
def list_configured_users(identity: Identity = Depends(current_identity)) -> list[dict[str, str]]:
    _require_role(identity, EDIT_ROLES)
    return [
        {
            "user_id": user["id"],
            "username": user["username"],
            "name": user["name"],
            "role": user["role"],
        }
        for user in configured_users().values()
        if user["organization_id"] == identity.organization_id
    ]


@app.get("/api/exercises/{exercise_id}/access")
def list_exercise_access(
    exercise_id: str,
    identity: Identity = Depends(current_identity),
    db: Session = Depends(get_db),
) -> list[dict[str, str]]:
    exercise = _exercise_for_user(db, exercise_id, identity, EDIT_ROLES)
    users = configured_users()
    grants = db.scalars(
        select(ExerciseGrant)
        .where(
            ExerciseGrant.exercise_id == exercise.id,
            ExerciseGrant.organization_id == identity.organization_id,
        )
        .order_by(ExerciseGrant.user_id)
    ).all()
    return [
        {
            "user_id": grant.user_id,
            "username": users[grant.user_id]["username"],
            "name": users[grant.user_id]["name"],
            "role": users[grant.user_id]["role"],
        }
        for grant in grants
        if grant.user_id in users
    ]


@app.post("/api/exercises/{exercise_id}/access", status_code=201)
def grant_exercise_access(
    exercise_id: str,
    payload: ExerciseAccessGrant,
    identity: Identity = Depends(current_identity),
    db: Session = Depends(get_db),
) -> dict[str, str]:
    exercise = _exercise_for_user(db, exercise_id, identity, EDIT_ROLES)
    user = configured_users().get(payload.user_id)
    if user is None or user["organization_id"] != identity.organization_id:
        raise HTTPException(
            status_code=404, detail="Configured user not found in this organization."
        )
    grant = db.scalar(
        select(ExerciseGrant).where(
            ExerciseGrant.exercise_id == exercise.id,
            ExerciseGrant.user_id == user["id"],
            ExerciseGrant.organization_id == identity.organization_id,
        )
    )
    if grant is None:
        db.add(
            ExerciseGrant(
                id=str(uuid.uuid4()),
                exercise_id=exercise.id,
                user_id=user["id"],
                organization_id=identity.organization_id,
                access_role=user["role"],
            )
        )
        _audit(
            db,
            exercise.id,
            identity.name,
            "exercise_access_granted",
            user["id"],
            {"role": user["role"]},
        )
        db.commit()
    return {"user_id": user["id"], "name": user["name"], "role": user["role"]}


@app.delete("/api/exercises/{exercise_id}/access/{user_id}")
def revoke_exercise_access(
    exercise_id: str,
    user_id: str,
    identity: Identity = Depends(current_identity),
    db: Session = Depends(get_db),
) -> dict[str, str]:
    exercise = _exercise_for_user(db, exercise_id, identity, EDIT_ROLES)
    if user_id == identity.user_id:
        raise HTTPException(status_code=409, detail="You cannot revoke your own exercise access.")
    grant = db.scalar(
        select(ExerciseGrant).where(
            ExerciseGrant.exercise_id == exercise.id,
            ExerciseGrant.user_id == user_id,
            ExerciseGrant.organization_id == identity.organization_id,
        )
    )
    if grant is None:
        raise HTTPException(status_code=404, detail="Exercise access grant not found.")
    db.delete(grant)
    _audit(db, exercise.id, identity.name, "exercise_access_revoked", user_id, {})
    db.commit()
    return {"user_id": user_id, "status": "revoked"}


@app.post("/api/demo/seed")
def seed_demo(
    identity: Identity = Depends(current_identity), db: Session = Depends(get_db)
) -> dict:
    _require_role(identity, EDIT_ROLES)
    if os.getenv("DRILLLOOP_ENABLE_DEMO_SEED", "0").casefold() not in {"1", "true", "yes"}:
        raise HTTPException(status_code=404, detail="Synthetic demo seeding is disabled.")
    exercise = _seed_demo(db)
    _create_exercise_grant(db, exercise, identity)
    analysis = analyze_exercise(db, exercise)
    db.commit()
    return {"id": exercise.id, "analysis": analysis}


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
            "scan_status": row.scan_status,
            "observation_count": sum(1 for obs in observations if obs.source_id == row.id),
        }
        for row in sources
    ]
    return {
        "exercise": _exercise_dict(exercise),
        "objective_assessments": objective_assessments(db, exercise),
        "analysis_locked": bool(findings_rows)
        or any(row.action == "analysis_completed" for row in audit_rows),
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
def exercise_detail(
    exercise_id: str,
    identity: Identity = Depends(current_identity),
    db: Session = Depends(get_db),
) -> dict:
    exercise = _exercise_for_user(db, exercise_id, identity, READ_ROLES)
    return _detail(db, exercise)


@app.post("/api/exercises/{exercise_id}/evidence", status_code=201)
async def upload_evidence(
    exercise_id: str,
    files: list[UploadFile] = File(...),
    identity: Identity = Depends(current_identity),
    db: Session = Depends(get_db),
) -> dict:
    exercise = _exercise_for_user(db, exercise_id, identity, EDIT_ROLES)
    if len(files) > MAX_EVIDENCE_FILES:
        raise HTTPException(
            status_code=413,
            detail={
                "code": "TOO_MANY_FILES",
                "message": "Upload at most 10 evidence files at once.",
            },
        )
    uploaded: list[tuple[UploadFile, bytes]] = []
    total_size = 0
    for file in files:
        raw = await file.read(MAX_FILE_SIZE + 1)
        total_size += len(raw)
        if len(raw) > MAX_FILE_SIZE:
            raise HTTPException(
                status_code=413,
                detail={"code": "FILE_TOO_LARGE", "message": "Files are limited to 15 MB."},
            )
        if total_size > MAX_TOTAL_UPLOAD_SIZE:
            raise HTTPException(
                status_code=413,
                detail={
                    "code": "UPLOAD_TOO_LARGE",
                    "message": "A batch is limited to 30 MB total.",
                },
            )
        uploaded.append((file, raw))

    processed: list[tuple[UploadFile, bytes, ParsedEvidence, ScanResult, float]] = []
    for file, raw in uploaded:
        processing_started = time.perf_counter()
        cancellation_event = threading.Event()
        try:
            parsed, scan_result = await asyncio.to_thread(
                process_upload_isolated,
                file.filename or "evidence",
                file.content_type or "",
                raw,
                date.fromisoformat(exercise.exercise_date),
                cancellation_event=cancellation_event,
            )
        except asyncio.CancelledError:
            cancellation_event.set()
            logger.info(
                "upload_processing_cancelled",
                extra={"fields": {"filename": safe_filename(file.filename)}},
            )
            raise
        except (EvidenceError, UploadProcessingFailure) as error:
            if isinstance(error, UploadProcessingFailure):
                scan_state = {
                    "MALWARE_REJECTED": "rejected",
                    "SCANNER_TIMEOUT": "timeout",
                    "SCANNER_UNAVAILABLE": "unavailable",
                    "SCANNER_NOT_READY": "unavailable",
                    "SCANNER_SIGNATURES_STALE": "stale",
                    "SCANNER_SIGNATURES_UNKNOWN": "stale",
                    "SCANNER_FAILED": "error",
                    "QUARANTINE_UNAVAILABLE": "unavailable",
                    "QUARANTINE_CONFIGURATION_INVALID": "error",
                }.get(error.code, "error")
                scan_state = error.details.get("scan_status", scan_state)
                scanner_details = error.details
            else:
                scan_state = "not_reached"
                scanner_details = {}
            attempt_id = str(uuid.uuid4())
            _audit(
                db,
                exercise.id,
                identity.name,
                "upload_rejected",
                attempt_id,
                {
                    "filename": safe_filename(file.filename),
                    "size_bytes": len(raw),
                    "scan_status": scan_state,
                    "processing_status": "rejected",
                    "error_code": error.code,
                    "scanner_version": scanner_details.get("scanner_version"),
                    "signature_timestamp": scanner_details.get("signature_timestamp"),
                    "scan_duration_seconds": scanner_details.get("scan_duration_seconds"),
                    "scanner_reply": scanner_details.get("scanner_reply"),
                },
            )
            db.commit()
            METRICS.observe_upload("rejected", scan_state, time.perf_counter() - processing_started)
            logger.warning(
                "upload_rejected",
                extra={
                    "fields": {
                        "error_code": error.code,
                        "scan_status": scan_state,
                        "scanner_version": scanner_details.get("scanner_version"),
                        "signature_timestamp": scanner_details.get("signature_timestamp"),
                        "scan_duration_seconds": scanner_details.get("scan_duration_seconds"),
                        "http_status": error.status_code,
                    }
                },
            )
            headers = (
                {"Retry-After": str(error.retry_after_seconds)}
                if isinstance(error, UploadProcessingFailure)
                and error.retry_after_seconds is not None
                else None
            )
            raise HTTPException(
                status_code=error.status_code,
                detail={
                    "code": error.code,
                    "message": error.message,
                    "filename": safe_filename(file.filename),
                },
                headers=headers,
            ) from error

        processed.append((file, raw, parsed, scan_result, time.perf_counter() - processing_started))

    # Persist only after every file in this request has passed scan and extraction.
    # A retry after a capacity/scanner 503 can therefore never duplicate a partial batch.
    created = []
    committed: list[tuple[Source, ParsedEvidence, ScanResult, float]] = []
    for file, raw, parsed, scan_result, processing_duration in processed:
        source = _store_parsed(
            db,
            exercise_id,
            file.filename or "evidence",
            file.content_type or "application/octet-stream",
            parsed,
            raw,
            scan_result.status,
        )
        committed.append((source, parsed, scan_result, processing_duration))
        created.append(
            {
                "id": source.id,
                "filename": source.filename,
                "kind": source.kind,
                "observation_count": len(parsed.observations),
            }
        )
        _audit(
            db,
            exercise.id,
            identity.name,
            "evidence_uploaded",
            source.id,
            {
                "sha256": source.sha256,
                "scan_status": scan_result.status,
                "processing_status": "accepted",
                "scanner_version": scan_result.engine_version,
                "signature_timestamp": scan_result.signature_timestamp,
                "scan_duration_seconds": scan_result.duration_seconds,
                "observation_count": len(parsed.observations),
            },
        )
    db.commit()
    for source, parsed, scan_result, processing_duration in committed:
        METRICS.observe_upload("accepted", scan_result.status, processing_duration)
        logger.info(
            "upload_processed",
            extra={
                "fields": {
                    "source_id": source.id,
                    "scan_status": scan_result.status,
                    "scanner_version": scan_result.engine_version,
                    "signature_timestamp": scan_result.signature_timestamp,
                    "scan_duration_ms": round(scan_result.duration_seconds * 1000, 2),
                    "observation_count": len(parsed.observations),
                    "processing_ms": round(processing_duration * 1000, 2),
                }
            },
        )
    return {"sources": created, "message": f"Imported {len(created)} evidence file(s)."}


@app.post("/api/exercises/{exercise_id}/audio", status_code=201)
async def transcribe_audio(
    exercise_id: str,
    file: UploadFile = File(...),
    identity: Identity = Depends(current_identity),
    db: Session = Depends(get_db),
) -> dict:
    exercise = _exercise_for_user(db, exercise_id, identity, EDIT_ROLES)
    if os.getenv("DRILLLOOP_ENVIRONMENT", "local").casefold() == "production":
        raise HTTPException(
            status_code=503,
            detail={
                "code": "ASR_WORKER_UNAVAILABLE",
                "message": "Audio transcription is disabled until an isolated production ASR worker is configured.",
            },
        )
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
    try:
        scan_status = await asyncio.to_thread(scan_bytes_isolated, raw)
    except UploadProcessingFailure as error:
        raise HTTPException(
            status_code=error.status_code,
            detail={"code": error.code, "message": error.message},
        ) from error
    audio_filename = safe_filename(file.filename or "audio.wav")
    if audio_filename.lower().rsplit(".", 1)[-1] not in {"wav", "mp3", "m4a", "flac", "ogg"}:
        raise HTTPException(
            status_code=415,
            detail={
                "code": "UNSUPPORTED_AUDIO",
                "message": "Use WAV, MP3, M4A, FLAC, or OGG audio.",
            },
        )
    try:
        with tempfile.NamedTemporaryFile(suffix=Path(audio_filename).suffix) as temp:
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
        (Path(audio_filename).stem + ".json"),
        "application/json",
        json_bytes,
        date.fromisoformat(exercise.exercise_date),
    )
    parsed.kind = "transcript"
    source = _store_parsed(
        db,
        exercise_id,
        audio_filename,
        file.content_type or "audio/*",
        parsed,
        raw,
        scan_status,
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
    exercise_id: str,
    payload: TranscriptIngest,
    identity: Identity = Depends(current_identity),
    db: Session = Depends(get_db),
) -> dict:
    exercise = _exercise_for_user(db, exercise_id, identity, EDIT_ROLES)
    transcript_payload = {
        "model": payload.model_version,
        "language": payload.language,
        "segments": payload.segments or [{"start": 0, "end": 0, "text": payload.transcript}],
    }
    raw = json.dumps(transcript_payload, ensure_ascii=False).encode()
    try:
        parsed = parse_evidence(
            payload.source_name.rsplit(".", 1)[0] + ".json",
            "application/json",
            raw,
            date.fromisoformat(exercise.exercise_date),
        )
    except EvidenceError as error:
        raise HTTPException(
            status_code=error.status_code,
            detail={"code": error.code, "message": error.message},
        ) from error
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
def analyze(
    exercise_id: str,
    identity: Identity = Depends(current_identity),
    db: Session = Depends(get_db),
) -> dict:
    exercise = _exercise_for_user(db, exercise_id, identity, EDIT_ROLES)
    started = time.perf_counter()
    try:
        result = analyze_exercise(db, exercise)
    finally:
        METRICS.observe_analysis(time.perf_counter() - started)
    if "error" in result:
        raise HTTPException(
            status_code=422, detail={"code": result["error"], "message": result["message"]}
        )
    _audit(
        db,
        exercise.id,
        "system",
        "analysis_completed",
        exercise.id,
        {"candidate_count": result["candidate_count"]},
    )
    db.commit()
    return result


@app.patch("/api/findings/{finding_id}")
def edit_finding(
    finding_id: str,
    payload: FindingEdit,
    identity: Identity = Depends(current_identity),
    db: Session = Depends(get_db),
) -> dict:
    _require_role(identity, EDIT_ROLES)
    finding = db.get(Finding, finding_id)
    if not finding:
        raise HTTPException(status_code=404, detail="Finding not found.")
    _exercise_for_user(db, finding.exercise_id, identity, EDIT_ROLES)
    if finding.status != "proposed":
        raise HTTPException(status_code=409, detail="Only proposed findings can be edited.")
    finding.title = payload.title
    finding.observation = payload.observation
    finding.interpretation = payload.interpretation
    finding.reviewer = identity.name
    finding.updated_at = utcnow()
    _audit(db, finding.exercise_id, identity.name, "finding_edited", finding.id, {})
    db.commit()
    return {"id": finding.id, "status": finding.status, "title": finding.title}


@app.post("/api/findings/{finding_id}/review")
def review_finding(
    finding_id: str,
    payload: FindingReview,
    identity: Identity = Depends(current_identity),
    db: Session = Depends(get_db),
) -> dict:
    _require_role(identity, REVIEW_ROLES)
    if payload.decision not in {"approved", "rejected"}:
        raise HTTPException(status_code=422, detail="Decision must be approved or rejected.")
    finding = db.get(Finding, finding_id)
    if not finding:
        raise HTTPException(status_code=404, detail="Finding not found.")
    _exercise_for_user(db, finding.exercise_id, identity, REVIEW_ROLES)
    if finding.status != "proposed":
        raise HTTPException(status_code=409, detail="This finding already has a reviewer decision.")
    finding.status = payload.decision
    finding.review_note = payload.note
    finding.reviewer = identity.name
    finding.updated_at = utcnow()
    _audit(
        db,
        finding.exercise_id,
        identity.name,
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
    identity: Identity = Depends(current_identity),
    db: Session = Depends(get_db),
) -> dict:
    _require_role(identity, EDIT_ROLES)
    action = db.get(CorrectiveAction, action_id)
    if not action:
        raise HTTPException(status_code=404, detail="Corrective action not found.")
    _exercise_for_user(db, action.exercise_id, identity, EDIT_ROLES)
    if action.status == "closed":
        raise HTTPException(status_code=409, detail="Closed actions are immutable in this demo.")
    if payload.title is not None:
        action.title = payload.title.strip()
    action.owner = payload.owner.strip() if payload.owner and payload.owner.strip() else None
    action.priority = payload.priority
    action.due_date = payload.due_date.isoformat() if payload.due_date else None
    action.acceptance_criteria = payload.acceptance_criteria
    action.reviewer = identity.name
    action.updated_at = utcnow()
    _audit(
        db,
        action.exercise_id,
        identity.name,
        "action_updated",
        action.id,
        {
            "title": action.title,
            "owner": action.owner,
            "priority": action.priority,
            "due_date": action.due_date,
        },
    )
    db.commit()
    return {
        "id": action.id,
        "title": action.title,
        "owner": action.owner,
        "due_date": action.due_date,
    }


@app.post("/api/actions/{action_id}/review")
def review_action(
    action_id: str,
    payload: ActionReview,
    identity: Identity = Depends(current_identity),
    db: Session = Depends(get_db),
) -> dict:
    _require_role(identity, REVIEW_ROLES)
    if payload.decision not in {"approved", "rejected"}:
        raise HTTPException(status_code=422, detail="Decision must be approved or rejected.")
    action = db.get(CorrectiveAction, action_id)
    if not action:
        raise HTTPException(status_code=404, detail="Corrective action not found.")
    _exercise_for_user(db, action.exercise_id, identity, REVIEW_ROLES)
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
    action.reviewer = identity.name
    action.updated_at = utcnow()
    _audit(
        db,
        action.exercise_id,
        identity.name,
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
    identity: Identity = Depends(current_identity),
    db: Session = Depends(get_db),
) -> dict:
    _require_role(identity, REVIEW_ROLES)
    action = db.get(CorrectiveAction, action_id)
    if not action:
        raise HTTPException(status_code=404, detail="Corrective action not found.")
    _exercise_for_user(db, action.exercise_id, identity, REVIEW_ROLES)
    if action.reviewer_decision != "approved":
        raise HTTPException(status_code=409, detail="Only an approved action can be closed.")
    action.closure_evidence = payload.closure_evidence
    action.status = "closed"
    action.reviewer = identity.name
    action.updated_at = utcnow()
    _audit(
        db,
        action.exercise_id,
        identity.name,
        "action_closed",
        action.id,
        {"closure_evidence": payload.closure_evidence},
    )
    db.commit()
    return {"id": action.id, "status": action.status, "closure_evidence": action.closure_evidence}


@app.get("/api/exercises/{exercise_id}/report.pdf")
def report_pdf(
    exercise_id: str,
    identity: Identity = Depends(current_identity),
    db: Session = Depends(get_db),
) -> Response:
    exercise = _exercise_for_user(db, exercise_id, identity, READ_ROLES)
    content = make_report_pdf(_detail(db, exercise))
    return Response(
        content=content,
        media_type="application/pdf",
        headers={"Content-Disposition": f'attachment; filename="{exercise_id}-AAR-IP.pdf"'},
    )


@app.get("/api/sources/{source_id}/download")
def download_source(
    source_id: str,
    identity: Identity = Depends(current_identity),
    db: Session = Depends(get_db),
) -> Response:
    source = db.get(Source, source_id)
    if not source:
        raise HTTPException(status_code=404, detail="Source evidence not found.")
    _exercise_for_user(db, source.exercise_id, identity, READ_ROLES)
    payload = source.source_bytes
    media_type = source.mime_type
    if payload is None:
        payload = source.content_text.encode("utf-8")
        media_type = "text/plain; charset=utf-8"
    attachment_filename = safe_filename(source.filename).replace('"', "")
    return Response(
        content=payload,
        media_type=media_type,
        headers={"Content-Disposition": f'attachment; filename="{attachment_filename}"'},
    )
