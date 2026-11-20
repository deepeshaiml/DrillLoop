from __future__ import annotations

from datetime import UTC, datetime

from sqlalchemy import (
    CheckConstraint,
    DateTime,
    ForeignKey,
    ForeignKeyConstraint,
    Index,
    Integer,
    LargeBinary,
    String,
    Text,
    UniqueConstraint,
    text,
)
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


def utcnow() -> datetime:
    return datetime.now(UTC)


class Base(DeclarativeBase):
    pass


class Exercise(Base):
    __tablename__ = "exercises"
    __table_args__ = (Index("ux_exercises_id_organization", "id", "organization_id", unique=True),)

    id: Mapped[str] = mapped_column(String(80), primary_key=True)
    organization_id: Mapped[str] = mapped_column(String(120), server_default=text("''"))
    title: Mapped[str] = mapped_column(String(200))
    scenario: Mapped[str] = mapped_column(Text)
    exercise_date: Mapped[str] = mapped_column(String(20))
    duration_minutes: Mapped[int] = mapped_column(Integer)
    objectives_json: Mapped[str] = mapped_column(Text)
    criteria_json: Mapped[str] = mapped_column(Text)
    evaluator_roles_json: Mapped[str] = mapped_column(Text)
    participants_json: Mapped[str] = mapped_column(Text)
    milestones_json: Mapped[str] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class ExerciseGrant(Base):
    __tablename__ = "exercise_grants"
    __table_args__ = (UniqueConstraint("exercise_id", "user_id", name="uq_exercise_grant_user"),)

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    exercise_id: Mapped[str] = mapped_column(ForeignKey("exercises.id"), index=True)
    user_id: Mapped[str] = mapped_column(String(120), index=True)
    organization_id: Mapped[str] = mapped_column(String(120), index=True)
    access_role: Mapped[str] = mapped_column(String(24))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class Source(Base):
    __tablename__ = "sources"

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    exercise_id: Mapped[str] = mapped_column(ForeignKey("exercises.id"), index=True)
    filename: Mapped[str] = mapped_column(String(255))
    kind: Mapped[str] = mapped_column(String(40))
    mime_type: Mapped[str] = mapped_column(String(120), default="application/octet-stream")
    sha256: Mapped[str] = mapped_column(String(64))
    content_text: Mapped[str] = mapped_column(Text, default="")
    source_bytes: Mapped[bytes | None] = mapped_column(LargeBinary, nullable=True)
    provenance_json: Mapped[str] = mapped_column(Text, default="{}")
    scan_status: Mapped[str] = mapped_column(
        String(24), nullable=False, default="not_scanned", server_default=text("'not_scanned'")
    )
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class Observation(Base):
    __tablename__ = "observations"

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    exercise_id: Mapped[str] = mapped_column(ForeignKey("exercises.id"), index=True)
    source_id: Mapped[str] = mapped_column(ForeignKey("sources.id"), index=True)
    text: Mapped[str] = mapped_column(Text)
    event_time_raw: Mapped[str | None] = mapped_column(String(80), nullable=True)
    event_time_normalized: Mapped[str | None] = mapped_column(String(40), nullable=True)
    time_confidence: Mapped[str] = mapped_column(String(20), default="unknown")
    source_locator: Mapped[str] = mapped_column(String(160), default="")
    observation_type: Mapped[str] = mapped_column(String(40), default="note")
    extraction_method: Mapped[str] = mapped_column(String(40), default="parser")
    recognition_confidence: Mapped[float | None] = mapped_column(nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class Finding(Base):
    __tablename__ = "findings"
    __table_args__ = (Index("ux_findings_exercise_id_id", "exercise_id", "id", unique=True),)

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    exercise_id: Mapped[str] = mapped_column(ForeignKey("exercises.id"), index=True)
    code: Mapped[str] = mapped_column(String(80))
    title: Mapped[str] = mapped_column(String(240))
    category: Mapped[str] = mapped_column(String(24))  # strength | improvement
    objective_id: Mapped[str | None] = mapped_column(String(80), nullable=True)
    observation: Mapped[str] = mapped_column(Text)
    interpretation: Mapped[str] = mapped_column(Text)
    evidence_ids_json: Mapped[str] = mapped_column(Text)
    confidence: Mapped[str] = mapped_column(String(20), default="medium")
    status: Mapped[str] = mapped_column(String(24), default="proposed")
    review_note: Mapped[str] = mapped_column(Text, default="")
    reviewer: Mapped[str | None] = mapped_column(String(120), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class CorrectiveAction(Base):
    __tablename__ = "corrective_actions"

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    exercise_id: Mapped[str] = mapped_column(ForeignKey("exercises.id"), index=True)
    finding_id: Mapped[str] = mapped_column(ForeignKey("findings.id"), index=True)
    title: Mapped[str] = mapped_column(String(240))
    evidence_ids_json: Mapped[str] = mapped_column(Text)
    owner: Mapped[str | None] = mapped_column(String(160), nullable=True)
    priority: Mapped[str] = mapped_column(String(20), default="medium")
    due_date: Mapped[str | None] = mapped_column(String(20), nullable=True)
    acceptance_criteria: Mapped[str] = mapped_column(Text)
    status: Mapped[str] = mapped_column(String(24), default="proposed")
    reviewer_decision: Mapped[str] = mapped_column(String(24), default="pending")
    reviewer: Mapped[str | None] = mapped_column(String(120), nullable=True)
    closure_evidence: Mapped[str] = mapped_column(Text, default="")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class AuditEvent(Base):
    __tablename__ = "audit_events"
    __table_args__ = (
        Index(
            "ux_audit_events_candidate_version",
            "exercise_id",
            "object_id",
            "candidate_version",
            unique=True,
        ),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    exercise_id: Mapped[str] = mapped_column(ForeignKey("exercises.id"), index=True)
    actor: Mapped[str] = mapped_column(String(120))
    action: Mapped[str] = mapped_column(String(80))
    object_id: Mapped[str] = mapped_column(String(80))
    details_json: Mapped[str] = mapped_column(Text, default="{}")
    candidate_version: Mapped[int | None] = mapped_column(Integer)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class AiCandidate(Base):
    __tablename__ = "ai_candidates"
    __table_args__ = (
        ForeignKeyConstraint(
            ["exercise_id", "organization_id"],
            ["exercises.id", "exercises.organization_id"],
            ondelete="RESTRICT",
            name="fk_ai_candidate_exercise_owner",
        ),
        CheckConstraint(
            "review_state IN ('pending_review', 'accepted_for_consideration', 'rejected', 'more_evidence_required')",
            name="ck_ai_candidate_review_state",
        ),
        CheckConstraint(
            "(freshness = 'current' AND stale_at IS NULL) OR (freshness = 'stale' AND stale_at IS NOT NULL)",
            name="ck_ai_candidate_freshness",
        ),
        CheckConstraint("version >= 1", name="ck_ai_candidate_version"),
        Index("ux_ai_candidates_scope", "exercise_id", "organization_id", "id", unique=True),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    exercise_id: Mapped[str] = mapped_column(String(80))
    organization_id: Mapped[str] = mapped_column(String(120))
    issuance_id: Mapped[str] = mapped_column(String(36), unique=True)
    # Immutable generation snapshot, validated with CandidateSnapshot.
    snapshot_json: Mapped[str] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    review_state: Mapped[str] = mapped_column(String(32), default="pending_review")
    freshness: Mapped[str] = mapped_column(String(8), default="current")
    stale_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    stale_reasons_json: Mapped[str] = mapped_column(Text, default="[]")
    version: Mapped[int] = mapped_column(Integer, default=1)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class AiCandidatePromotion(Base):
    __tablename__ = "ai_candidate_promotions"
    __table_args__ = (
        ForeignKeyConstraint(
            ["exercise_id", "organization_id", "candidate_id"],
            ["ai_candidates.exercise_id", "ai_candidates.organization_id", "ai_candidates.id"],
            ondelete="RESTRICT",
            name="fk_ai_candidate_promotion_candidate_scope",
        ),
        ForeignKeyConstraint(
            ["exercise_id", "finding_id"],
            ["findings.exercise_id", "findings.id"],
            ondelete="RESTRICT",
            name="fk_ai_candidate_promotion_finding_scope",
        ),
    )

    candidate_id: Mapped[str] = mapped_column(String(36), primary_key=True)
    exercise_id: Mapped[str] = mapped_column(String(80))
    organization_id: Mapped[str] = mapped_column(String(120))
    finding_id: Mapped[str] = mapped_column(String(36), unique=True)


class AiCandidateRequest(Base):
    __tablename__ = "ai_candidate_requests"
    __table_args__ = (
        ForeignKeyConstraint(
            ["exercise_id", "organization_id", "candidate_id"],
            ["ai_candidates.exercise_id", "ai_candidates.organization_id", "ai_candidates.id"],
            ondelete="RESTRICT",
            name="fk_ai_candidate_request_candidate_scope",
        ),
        CheckConstraint(
            "operation IN ('save', 'review', 'promote')", name="ck_ai_candidate_request_operation"
        ),
        CheckConstraint("applied_version >= 1", name="ck_ai_candidate_request_version"),
    )

    exercise_id: Mapped[str] = mapped_column(String(80), primary_key=True)
    organization_id: Mapped[str] = mapped_column(String(120), primary_key=True)
    actor_user_id: Mapped[str] = mapped_column(String(120), primary_key=True)
    operation: Mapped[str] = mapped_column(String(8), primary_key=True)
    key: Mapped[str] = mapped_column(String(128), primary_key=True)
    request_hash: Mapped[str] = mapped_column(String(64))
    candidate_id: Mapped[str] = mapped_column(String(36))
    applied_version: Mapped[int] = mapped_column(Integer)
    decision: Mapped[str | None] = mapped_column(String(32))
