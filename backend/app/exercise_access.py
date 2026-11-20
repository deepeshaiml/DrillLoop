from __future__ import annotations

import json
import logging
import uuid

from fastapi import HTTPException
from sqlalchemy import select
from sqlalchemy.exc import OperationalError
from sqlalchemy.orm import Session

from app.auth import Identity
from app.models import AuditEvent, Exercise, ExerciseGrant

READ_ROLES = {"admin", "evaluator", "reviewer", "viewer"}
EDIT_ROLES = {"admin", "evaluator"}
REVIEW_ROLES = {"admin", "reviewer"}
logger = logging.getLogger("drillloop")


def begin_exercise_write(db: Session) -> None:
    """SQLite has no row locks. Acquire its write reservation before reading context."""
    if db.get_bind().dialect.name == "sqlite":
        try:
            db.connection().exec_driver_sql("BEGIN IMMEDIATE")
        except OperationalError as exc:
            raise HTTPException(
                status_code=503,
                detail={
                    "code": "EXERCISE_BUSY",
                    "message": "Exercise data is temporarily unavailable. Retry shortly.",
                },
            ) from exc


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


def _exercise_for_user(
    db: Session,
    exercise_id: str,
    identity: Identity,
    allowed_roles: set[str],
    *,
    lock: bool = False,
) -> Exercise:
    _require_role(identity, allowed_roles)
    if lock:
        begin_exercise_write(db)
    query = select(Exercise).where(
        Exercise.id == exercise_id, Exercise.organization_id == identity.organization_id
    )
    if lock:
        query = query.with_for_update()
    exercise = db.scalar(query.execution_options(populate_existing=True))
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
    db: Session,
    exercise_id: str,
    actor: str,
    action: str,
    object_id: str,
    details: dict,
    *,
    candidate_version: int | None = None,
) -> None:
    db.add(
        AuditEvent(
            id=str(uuid.uuid4()),
            exercise_id=exercise_id,
            actor=actor,
            action=action,
            object_id=object_id,
            details_json=json.dumps(details, ensure_ascii=False),
            candidate_version=candidate_version,
        )
    )
