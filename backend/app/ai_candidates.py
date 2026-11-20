"""Exercise-scoped advisory candidate API and transaction handling."""

from __future__ import annotations

import json
import logging
import re
import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, Header, HTTPException, Path, Query, Request, Response
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from fastapi.routing import APIRoute
from pydantic import ValidationError
from sqlalchemy import Select, select, update
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from app.ai_evaluation import AiFailure, AiResult
from app.auth import Identity, current_identity
from app.candidate_evidence import (
    CandidateSnapshot,
    EvidenceContext,
    attach_save_tokens,
    fingerprint,
    load_evidence,
    stale_reasons,
    validate_save,
    verify_token,
)
from app.db import SessionLocal, get_db
from app.exercise_access import EDIT_ROLES, READ_ROLES, REVIEW_ROLES, _audit, _exercise_for_user
from app.models import AiCandidate, AiCandidateRequest, AuditEvent, Exercise, utcnow
from app.observability import server_request_id_context
from app.schemas import CandidateReview, CandidateSave

logger = logging.getLogger("drillloop.ai_candidates")
SAVED = "ai_candidate_saved"
REVIEWED = "ai_candidate_reviewed"
INVALIDATED = "ai_candidate_invalidated"
TRANSITIONS = {
    "pending_review": {"accepted_for_consideration", "rejected", "more_evidence_required"},
    "more_evidence_required": {"accepted_for_consideration", "rejected"},
    "accepted_for_consideration": {"more_evidence_required", "rejected"},
    "rejected": set(),
}


def _verification_unavailable() -> AiFailure:
    return AiFailure(
        503,
        "AI_VERIFICATION_UNAVAILABLE",
        "Evidence verification is temporarily unavailable. Retry shortly.",
    )


def _request_validation_message(error: RequestValidationError) -> str:
    for issue in error.errors():
        if issue["type"] == "value_error":
            # Only the application's fixed review validators use custom value errors.
            return issue["msg"].removeprefix("Value error, ")
    return "Check the candidate request fields, pagination bounds and save token length."


class CandidateRoute(APIRoute):
    def get_route_handler(self):
        handle = super().get_route_handler()

        async def protected(request: Request) -> Response:
            try:
                response = await handle(request)
            except RequestValidationError as error:
                # FastAPI normally echoes the invalid input, which can include a signed token.
                response = JSONResponse(
                    status_code=422,
                    content={
                        "detail": {
                            "code": "AI_REQUEST_INVALID",
                            "message": _request_validation_message(error),
                        }
                    },
                )
            except HTTPException as error:
                response = JSONResponse(
                    status_code=error.status_code,
                    content={"detail": error.detail},
                    headers=error.headers,
                )
            except (AiFailure, SQLAlchemyError) as error:
                failure = error if isinstance(error, AiFailure) else _verification_unavailable()
                response = JSONResponse(
                    status_code=failure.status,
                    content={"detail": {"code": failure.code, "message": failure.message}},
                )
            return response

        return protected


router = APIRouter(prefix="/api/exercises/{exercise_id}", route_class=CandidateRoute)
IdempotencyHeader = Annotated[str | None, Header(alias="Idempotency-Key")]
VersionHeader = Annotated[str | None, Header(alias="If-Match")]
CandidateId = Annotated[str, Path(max_length=36)]


def _evidence(db: Session, exercise: Exercise, **kwargs) -> EvidenceContext:
    try:
        return load_evidence(db, exercise, **kwargs)
    except (ValueError, RecursionError, KeyError) as error:
        raise _verification_unavailable() from error


def _find(db: Session, scope: Exercise, candidate_id: str) -> AiCandidate:
    row = db.scalar(_scope(scope).where(AiCandidate.id == candidate_id))
    if row is None:
        raise HTTPException(status_code=404, detail="Candidate not found.")
    return row


def _scope(exercise: Exercise) -> Select:
    return select(AiCandidate).where(
        AiCandidate.exercise_id == exercise.id,
        AiCandidate.organization_id == exercise.organization_id,
    )


def _idem_key(key: str | None) -> str:
    if key is None:
        raise AiFailure(428, "IDEMPOTENCY_KEY_REQUIRED", "Supply an Idempotency-Key header.")
    if not re.fullmatch(r"[A-Za-z0-9._:-]{1,128}", key):
        raise AiFailure(
            422, "INVALID_IDEMPOTENCY_KEY", "Use 1–128 letters, digits or . _ : - in the key."
        )
    return key


def _idem_scope(exercise: Exercise, identity: Identity, operation: str, key: str | None) -> dict:
    return dict(
        exercise_id=exercise.id,
        organization_id=exercise.organization_id,
        actor_user_id=identity.user_id,
        operation=operation,
        key=_idem_key(key),
    )


def _replay(db: Session, scope: dict, request_hash: str) -> AiCandidateRequest | None:
    entry = db.get(AiCandidateRequest, scope)
    if entry is not None and entry.request_hash != request_hash:
        raise AiFailure(
            409, "IDEMPOTENCY_CONFLICT", "This key was already used for a different request."
        )
    return entry


def _record(
    db: Session,
    scope: dict,
    request_hash: str,
    row: AiCandidate,
    version: int,
    decision: str | None = None,
) -> None:
    db.add(
        AiCandidateRequest(
            **scope,
            request_hash=request_hash,
            candidate_id=row.id,
            applied_version=version,
            decision=decision,
        )
    )


def _event(
    db: Session,
    row: AiCandidate,
    version: int,
    action: str,
    actor: Identity | None,
    **details,
) -> None:
    _audit(
        db,
        row.exercise_id,
        actor.name if actor else "system",
        action,
        row.id,
        {
            "actor_user_id": actor.user_id if actor else None,
            "organization_id": row.organization_id,
            "request_id": server_request_id_context.get(),
            **details,
        },
        candidate_version=version,
    )


def _snapshot(row: AiCandidate) -> CandidateSnapshot:
    try:
        return CandidateSnapshot.model_validate_json(row.snapshot_json)
    except ValidationError as error:
        raise _verification_unavailable() from error


def _check_version() -> AiFailure:
    return AiFailure(
        412, "CANDIDATE_VERSION_MISMATCH", "Candidate changed. Reload it before reviewing."
    )


def _cas(db: Session, row: AiCandidate, **changes) -> int:
    version = row.version + 1
    result = db.execute(
        update(AiCandidate)
        .where(
            AiCandidate.id == row.id,
            AiCandidate.exercise_id == row.exercise_id,
            AiCandidate.organization_id == row.organization_id,
            AiCandidate.version == row.version,
            AiCandidate.review_state == row.review_state,
            AiCandidate.freshness == row.freshness,
        )
        .values(version=version, updated_at=utcnow(), **changes)
    )
    if result.rowcount != 1:
        raise _check_version()
    return version


def _refresh(
    db: Session,
    exercise: Exercise,
    row: AiCandidate,
    snapshot: CandidateSnapshot,
    context: EvidenceContext,
) -> None:
    if row.freshness == "stale":
        return
    reasons = stale_reasons(db, exercise, snapshot, context)
    if reasons:
        version = _cas(
            db, row, freshness="stale", stale_at=utcnow(), stale_reasons_json=json.dumps(reasons)
        )
        _event(
            db,
            row,
            version,
            INVALIDATED,
            None,
            prior_freshness="current",
            new_freshness="stale",
            reasons=reasons,
        )


def invalidate_changed_candidates(db: Session, exercise: Exercise) -> None:
    """Run under the same lock and transaction as a source or objective write."""
    rows = db.scalars(_scope(exercise).where(AiCandidate.freshness == "current")).all()
    if rows:
        try:
            db.flush()
            context = _evidence(db, exercise, allow_incomplete=True)
            for row in rows:
                _refresh(db, exercise, row, _snapshot(row), context)
        except (AiFailure, SQLAlchemyError) as error:
            failure = error if isinstance(error, AiFailure) else _verification_unavailable()
            raise HTTPException(
                status_code=failure.status,
                detail={"code": failure.code, "message": failure.message},
            ) from None


def _summary(row: AiCandidate, snapshot: CandidateSnapshot) -> dict:
    return {
        "id": row.id,
        "exercise_id": row.exercise_id,
        "organization_id": row.organization_id,
        "objective_id": snapshot.objective_id,
        "kind": snapshot.kind,
        "assessment": snapshot.assessment,
        "status": "proposed",
        "review_state": row.review_state,
        "freshness": row.freshness,
        "stale_at": row.stale_at,
        "stale_reasons": json.loads(row.stale_reasons_json),
        "version": row.version,
        "created_at": row.created_at,
        "updated_at": row.updated_at,
    }


def _history(row: AiCandidate) -> Select:
    return select(AuditEvent).where(
        AuditEvent.exercise_id == row.exercise_id,
        AuditEvent.object_id == row.id,
        AuditEvent.candidate_version.is_not(None),
        AuditEvent.action.in_([SAVED, REVIEWED, INVALIDATED]),
    )


def _event_dict(event: AuditEvent) -> dict:
    return {
        "id": event.id,
        "operation": event.action,
        "actor": event.actor,
        "candidate_id": event.object_id,
        "exercise_id": event.exercise_id,
        "timestamp": event.created_at,
        "version": event.candidate_version,
        **json.loads(event.details_json),
    }


@router.post("/ai-suggestions")
async def ai_suggestions(
    exercise_id: str,
    request: Request,
    identity: Identity = Depends(current_identity),
) -> AiResult:
    with SessionLocal() as db:
        _exercise_for_user(db, exercise_id, identity, EDIT_ROLES)
    context: EvidenceContext | None = None

    def load(max_input_bytes: int):
        nonlocal context
        with SessionLocal() as db:
            exercise = _exercise_for_user(db, exercise_id, identity, EDIT_ROLES, lock=True)
            context = _evidence(db, exercise, max_input_bytes=max_input_bytes)
            return context.ai

    def handoff(answer, result, eligible):
        if context is not None:
            attach_save_tokens(exercise_id, identity, context, answer, result, eligible)

    return await request.app.state.ai_evaluation.generate(load, handoff)


@router.post("/ai-candidates", status_code=201)
def save_candidate(
    exercise_id: str,
    payload: CandidateSave,
    request: Request,
    idempotency_key: IdempotencyHeader = None,
    identity: Identity = Depends(current_identity),
    db: Session = Depends(get_db),
) -> dict:
    exercise = _exercise_for_user(db, exercise_id, identity, EDIT_ROLES, lock=True)
    scope = _idem_scope(exercise, identity, "save", idempotency_key)
    request_hash = fingerprint(payload.model_dump())
    if replay := _replay(db, scope, request_hash):
        return {"id": replay.candidate_id, "version": replay.applied_version}

    try:
        claim = verify_token(payload.save_token, exercise, identity)
        existing = db.scalar(_scope(exercise).where(AiCandidate.issuance_id == claim.issuance_id))
        if existing is not None:
            _record(db, scope, request_hash, existing, 1)
            db.commit()
            return {"id": existing.id, "version": 1}

        service = request.app.state.ai_evaluation
        if service.configuration_error:
            raise AiFailure(503, "AI_UNAVAILABLE", "The local AI configuration is unavailable.")
        if service.settings is None:
            raise AiFailure(503, "AI_DISABLED", "AI assistance is disabled for this workspace.")
        try:
            snapshot = validate_save(db, exercise, claim)
        except (ValueError, RecursionError, KeyError) as error:
            raise _verification_unavailable() from error
    except AiFailure as error:
        if error.status in {409, 422}:
            logger.info(
                "ai_candidate_save_validation_failed",
                extra={
                    "fields": {
                        "code": error.code,
                        "exercise_id": exercise.id,
                        "organization_id": exercise.organization_id,
                        "actor_user_id": identity.user_id,
                    }
                },
            )
        raise

    row = AiCandidate(
        id=str(uuid.uuid4()),
        exercise_id=exercise.id,
        organization_id=exercise.organization_id,
        issuance_id=claim.issuance_id,
        snapshot_json=snapshot.model_dump_json(),
    )
    db.add(row)
    db.flush()
    _record(db, scope, request_hash, row, row.version)
    _event(db, row, row.version, SAVED, identity, prior_state=None, new_state=row.review_state)
    db.commit()
    return {"id": row.id, "version": row.version}


@router.get("/ai-candidates")
def list_candidates(
    exercise_id: str,
    limit: Annotated[int, Query(ge=1, le=50)] = 20,
    after: Annotated[str | None, Query(max_length=36)] = None,
    identity: Identity = Depends(current_identity),
    db: Session = Depends(get_db),
) -> dict:
    exercise = _exercise_for_user(db, exercise_id, identity, READ_ROLES, lock=True)
    query = _scope(exercise)
    if after is not None:
        query = query.where(AiCandidate.id > after)
    rows = db.scalars(query.order_by(AiCandidate.id).limit(limit + 1)).all()
    candidates = []
    context = None
    for row in rows[:limit]:
        snapshot = _snapshot(row)
        if row.freshness == "current":
            if context is None:
                context = _evidence(db, exercise, allow_incomplete=True)
            _refresh(db, exercise, row, snapshot, context)
        candidates.append(_summary(row, snapshot))
    db.commit()
    return {
        "candidates": candidates,
        "next_after": rows[limit - 1].id if len(rows) > limit else None,
    }


@router.get("/ai-candidates/{candidate_id}")
def candidate_detail(
    exercise_id: str,
    candidate_id: CandidateId,
    response: Response,
    history_after_version: Annotated[int, Query(ge=0, le=2_147_483_647)] = 0,
    history_limit: Annotated[int, Query(ge=1, le=50)] = 20,
    identity: Identity = Depends(current_identity),
    db: Session = Depends(get_db),
) -> dict:
    exercise = _exercise_for_user(db, exercise_id, identity, READ_ROLES, lock=True)
    row = _find(db, exercise, candidate_id)
    snapshot = _snapshot(row)
    if row.freshness == "current":
        _refresh(db, exercise, row, snapshot, _evidence(db, exercise, allow_incomplete=True))
        db.flush()
    events = db.scalars(
        _history(row)
        .where(AuditEvent.candidate_version > history_after_version)
        .order_by(AuditEvent.candidate_version)
        .limit(history_limit + 1)
    ).all()
    latest = db.scalar(
        _history(row)
        .where(AuditEvent.action == REVIEWED)
        .order_by(AuditEvent.candidate_version.desc())
        .limit(1)
    )
    latest_decision = _event_dict(latest) if latest else None
    response.headers["ETag"] = f'"{row.version}"'
    result = {
        **snapshot.model_dump(mode="json"),
        **_summary(row, snapshot),
        "reviewer_decision": latest_decision["new_state"] if latest_decision else None,
        "latest_decision": latest_decision,
        "history": [_event_dict(event) for event in events[:history_limit]],
        "next_history_after_version": (
            events[history_limit - 1].candidate_version if len(events) > history_limit else None
        ),
    }
    db.commit()
    return result


@router.post("/ai-candidates/{candidate_id}/review")
def review_candidate(
    exercise_id: str,
    candidate_id: CandidateId,
    payload: CandidateReview,
    if_match: VersionHeader = None,
    idempotency_key: IdempotencyHeader = None,
    identity: Identity = Depends(current_identity),
    db: Session = Depends(get_db),
) -> dict:
    exercise = _exercise_for_user(db, exercise_id, identity, REVIEW_ROLES, lock=True)
    row = _find(db, exercise, candidate_id)
    scope = _idem_scope(exercise, identity, "review", idempotency_key)
    request_hash = fingerprint([row.id, if_match, payload.model_dump()])
    if replay := _replay(db, scope, request_hash):
        return {
            "id": replay.candidate_id,
            "version": replay.applied_version,
            "decision": replay.decision,
        }
    if if_match is None:
        raise AiFailure(
            428, "CANDIDATE_VERSION_REQUIRED", "Supply If-Match with the current quoted version."
        )
    if not re.fullmatch(r'"[1-9][0-9]{0,9}"', if_match):
        raise AiFailure(
            422, "INVALID_CANDIDATE_VERSION", "If-Match must be a quoted positive integer."
        )

    was_current = row.freshness == "current"
    if was_current:
        _refresh(db, exercise, row, _snapshot(row), _evidence(db, exercise, allow_incomplete=True))
    if was_current and row.freshness == "stale":
        db.commit()
        raise AiFailure(409, "AI_CANDIDATE_STALE", "Evidence changed. This candidate is read-only.")
    if if_match != f'"{row.version}"':
        raise _check_version()
    if row.freshness == "stale":
        raise AiFailure(409, "AI_CANDIDATE_STALE", "Evidence changed. This candidate is read-only.")
    previous = row.review_state
    if payload.decision not in TRANSITIONS[previous]:
        raise AiFailure(
            409,
            "INVALID_CANDIDATE_TRANSITION",
            "This decision is unavailable in the current state.",
        )

    version = _cas(db, row, review_state=payload.decision)
    _record(db, scope, request_hash, row, version, payload.decision)
    _event(
        db,
        row,
        version,
        REVIEWED,
        identity,
        prior_state=previous,
        new_state=payload.decision,
        note=payload.note,
    )
    db.commit()
    return {"id": row.id, "version": version, "decision": payload.decision}
