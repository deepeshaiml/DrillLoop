"""Versioned evidence snapshots and signed, ephemeral AI suggestion handoffs."""

from __future__ import annotations

import hashlib
import hmac
import json
import re
import time
import uuid
from dataclasses import dataclass, field
from datetime import datetime

from pydantic import Field, ValidationError
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.ai_evaluation import (
    MAX_RECORDS,
    PROMPT_VERSION,
    Advisory,
    AiContext,
    AiFailure,
    AiResult,
    Citation,
    ModelAnswer,
    ProviderReply,
    StrictModel,
    Suggestion,
    contains_workflow_override,
    read_context,
    validate_suggestions,
)
from app.auth import Identity, _b64, _unb64, session_secret
from app.models import Exercise, Source, utcnow

CONTEXT_VERSION = 1
VALIDATOR_VERSION = "phase4c-v1"
SNAPSHOT_VERSION = 1
TOKEN_TTL_SECONDS = 15 * 60
MAX_SAVE_TOKEN = 65_536
MAX_CONTEXT_INPUT = 32_768
TOKEN_FORMAT = re.compile(r"[A-Za-z0-9_-]+\.[A-Za-z0-9_-]{43}")


def fingerprint(value: object) -> str:
    serialized = json.dumps(
        value, sort_keys=True, separators=(",", ":"), ensure_ascii=False, allow_nan=False
    )
    return hashlib.sha256(serialized.encode()).hexdigest()


class GenerationProvenance(StrictModel):
    provider: str
    model: str
    model_digest: str | None = None
    prompt_version: str = PROMPT_VERSION
    validator_version: str = VALIDATOR_VERSION
    context_version: int = CONTEXT_VERSION
    generated_at: datetime
    requested_by_user_id: str


class SavedCitation(Citation):
    text: str = Field(min_length=1, max_length=360)
    source_sha256: str
    observation_fingerprint: str
    recognition_confidence: float | None
    ocr_page: int | None = None
    ocr_engine: str | None = None
    ocr_engine_version: str | None = None
    ocr_language: str | None = None


class CandidateSnapshot(Advisory):
    schema_version: int = SNAPSHOT_VERSION
    objective_text: str = Field(min_length=4, max_length=2000)
    objective_fingerprint: str
    context_fingerprint: str
    evidence: list[SavedCitation] = Field(max_length=4)
    counterevidence: list[SavedCitation] = Field(max_length=4)
    provenance: GenerationProvenance


class SaveClaim(StrictModel):
    issuance_id: str
    exercise_id: str
    organization_id: str
    objective_id: str
    expires_at: int
    context_fingerprint: str
    suggestion_fingerprint: str
    provenance: GenerationProvenance
    entries: ModelAnswer


@dataclass(frozen=True)
class SourceContext:
    filename: str
    kind: str
    mime_type: str
    sha256: str
    scan_status: str
    original_available: bool
    provenance: dict

    @classmethod
    def load(cls, row) -> SourceContext:
        filename, kind, media_type, sha256, scan_status, available, provenance_json = row
        provenance = json.loads(provenance_json)
        if not isinstance(provenance, dict):
            raise ValueError("Invalid stored source provenance")
        return cls(filename, kind, media_type, sha256, scan_status, bool(available), provenance)

    def as_values(self) -> list:
        return [
            self.filename,
            self.kind,
            self.mime_type,
            self.sha256,
            self.scan_status,
            self.original_available,
            self.provenance,
        ]


@dataclass
class EvidenceContext:
    ai: AiContext | None
    definition_hashes: dict[str, str]
    context_hash: str | None
    sources: dict[str, SourceContext]
    observations: dict[str, str]
    original_issues: dict[str, bool] = field(default_factory=dict)

    def original_is_current(self, db: Session, exercise: Exercise, source_id: str) -> bool:
        if source_id not in self.original_issues:
            original = db.execute(
                select(Source.source_bytes, Source.sha256).where(
                    Source.exercise_id == exercise.id, Source.id == source_id
                )
            ).one_or_none()
            self.original_issues[source_id] = bool(
                original
                and original.source_bytes
                and hashlib.sha256(original.source_bytes).hexdigest() == original.sha256
            )
        return self.original_issues[source_id]

    def citation(self, cite: Citation) -> SavedCitation:
        source = self.sources[cite.source_id]
        provenance = source.provenance if cite.extraction_method == "ocr" else {}
        page = (
            re.match(r"page (\d+)\b", cite.source_locator)
            if cite.extraction_method == "ocr"
            else None
        )

        def ocr_text(key: str) -> str | None:
            value = provenance.get(key)
            return value[:120] if isinstance(value, str) else None

        return SavedCitation(
            **cite.model_dump(),
            source_sha256=source.sha256,
            observation_fingerprint=self.observations[cite.observation_id],
            recognition_confidence=self.ai.observation_provenance[cite.observation_id][2],
            ocr_page=int(page[1]) if page else None,
            ocr_engine=ocr_text("ocr_engine"),
            ocr_engine_version=ocr_text("ocr_engine_version"),
            ocr_language=ocr_text("ocr_language"),
        )


def load_evidence(
    db: Session,
    exercise: Exercise,
    max_input_bytes: int = MAX_CONTEXT_INPUT,
    *,
    allow_incomplete: bool = False,
) -> EvidenceContext:
    """Read with the caller holding the exercise context lock."""
    definitions = json.loads(exercise.objectives_json)
    definition_hashes = {}
    if not isinstance(definitions, list):
        definitions = []
    for item in definitions:
        if (
            not isinstance(item, dict)
            or not isinstance(item.get("id"), str)
            or not item["id"].strip()
            or item["id"] in definition_hashes
            or not isinstance(item.get("text"), str)
            or len(item["text"].strip()) < 4
            or len(item["text"]) > 2000
        ):
            if allow_incomplete:
                return EvidenceContext(None, {}, None, {}, {})
            raise AiFailure(
                422, "AI_INVALID_OBJECTIVES", "Use unique objective IDs and valid objective text."
            )
        definition_hashes[item["id"]] = fingerprint(item)

    try:
        ai = read_context(db, exercise, max_input_bytes)
    except AiFailure as error:
        if allow_incomplete and error.code in {"AI_OBJECTIVES_REQUIRED", "AI_EVIDENCE_REQUIRED"}:
            return EvidenceContext(None, definition_hashes, None, {}, {})
        raise

    rows = db.execute(
        select(
            Source.id,
            Source.filename,
            Source.kind,
            Source.mime_type,
            Source.sha256,
            Source.scan_status,
            func.length(Source.source_bytes) > 0,
            Source.provenance_json,
        )
        .where(Source.exercise_id == exercise.id)
        .order_by(Source.created_at, Source.id)
        .limit(MAX_RECORDS + 1)
    )
    sources = {row[0]: SourceContext.load(row[1:]) for row in rows}
    if ai.context_limited or len(sources) > MAX_RECORDS:
        return EvidenceContext(ai, definition_hashes, None, sources, {})

    source_fingerprints = {
        source_id: fingerprint(source.as_values()) for source_id, source in sources.items()
    }
    observations = {
        cite.observation_id: fingerprint(
            [
                cite.model_dump(),
                ai.observation_provenance[cite.observation_id],
                source_fingerprints[cite.source_id],
            ]
        )
        for cite in ai.records
    }
    context_hash = fingerprint(
        {
            "context_version": CONTEXT_VERSION,
            "prompt_version": PROMPT_VERSION,
            "validator_version": VALIDATOR_VERSION,
            "exercise_date": exercise.exercise_date,
            "objectives": list(definition_hashes.items()),
            "sources": list(source_fingerprints.items()),
            "observations": list(observations.items()),
        }
    )
    return EvidenceContext(ai, definition_hashes, context_hash, sources, observations)


def _suggestion_values(suggestion: Suggestion) -> dict:
    return suggestion.model_dump(exclude={"save_token", "status", "reviewer_decision"})


def _token_key() -> bytes:
    key = session_secret()
    if key is None:
        raise AiFailure(503, "AI_SAVE_UNAVAILABLE", "The suggestion signing key is unavailable.")
    return hmac.digest(key, b"drillloop:ai-candidate-save:v1", "sha256")


def attach_save_tokens(
    exercise_id: str,
    identity: Identity,
    context: EvidenceContext,
    answer: ModelAnswer,
    result: AiResult,
    eligible: set[str],
) -> None:
    if context.context_hash is None:
        return
    generated = utcnow()
    for suggestion in result.suggestions:
        objective = suggestion.objective_id
        if objective not in eligible or any(
            not cite.source_locator.strip()
            or not context.sources[cite.source_id].original_available
            for cite in suggestion.evidence + suggestion.counterevidence
        ):
            continue
        claim = SaveClaim(
            issuance_id=str(uuid.uuid4()),
            exercise_id=exercise_id,
            organization_id=identity.organization_id,
            objective_id=objective,
            expires_at=int(generated.timestamp()) + TOKEN_TTL_SECONDS,
            context_fingerprint=context.context_hash,
            suggestion_fingerprint=fingerprint(_suggestion_values(suggestion)),
            provenance=GenerationProvenance(
                provider=result.provider,
                model=result.model,
                generated_at=generated,
                requested_by_user_id=identity.user_id,
            ),
            entries=ModelAnswer(
                suggestions=[item for item in answer.suggestions if item.objective_id == objective]
            ),
        )
        body = _b64(claim.model_dump_json().encode())
        signature = _b64(hmac.digest(_token_key(), body.encode("ascii"), "sha256"))
        token = f"{body}.{signature}"
        if len(token) <= MAX_SAVE_TOKEN:
            suggestion.save_token = token


def verify_token(token: str, exercise: Exercise, identity: Identity) -> SaveClaim:
    invalid = AiFailure(
        422, "AI_SAVE_TOKEN_INVALID", "Generate a new eligible suggestion before saving."
    )
    if not TOKEN_FORMAT.fullmatch(token):
        raise invalid
    body, signature = token.split(".")
    expected = _b64(hmac.digest(_token_key(), body.encode("ascii"), "sha256"))
    if not hmac.compare_digest(signature, expected):
        raise invalid
    try:
        claim = SaveClaim.model_validate_json(_unb64(body))
    except (ValidationError, ValueError):
        raise invalid from None
    if (
        claim.exercise_id != exercise.id
        or claim.organization_id != exercise.organization_id
        or claim.provenance.requested_by_user_id != identity.user_id
    ):
        raise AiFailure(404, "AI_SUGGESTION_NOT_FOUND", "Suggestion not found.")
    return claim


def validate_save(
    db: Session,
    exercise: Exercise,
    claim: SaveClaim,
) -> CandidateSnapshot:
    if claim.expires_at <= int(time.time()):
        raise AiFailure(
            422, "AI_SAVE_TOKEN_EXPIRED", "Generate the suggestion again before saving."
        )
    context = load_evidence(db, exercise, allow_incomplete=True)
    if (
        claim.provenance.validator_version != VALIDATOR_VERSION
        or claim.provenance.prompt_version != PROMPT_VERSION
        or claim.provenance.context_version != CONTEXT_VERSION
        or context.context_hash != claim.context_fingerprint
    ):
        raise AiFailure(
            409, "AI_CONTEXT_CHANGED", "Exercise evidence or objectives changed. Generate again."
        )

    result, eligible = validate_suggestions(
        context.ai, claim.entries, ProviderReply(""), claim.provenance.model, 0
    )
    suggestion = next((s for s in result.suggestions if s.objective_id == claim.objective_id), None)
    if (
        suggestion is None
        or claim.objective_id not in eligible
        or fingerprint(_suggestion_values(suggestion)) != claim.suggestion_fingerprint
        or any(
            not cite.source_locator.strip()
            for cite in suggestion.evidence + suggestion.counterevidence
        )
    ):
        raise AiFailure(
            422, "AI_CITATIONS_INVALID", "The suggestion is missing complete, valid citations."
        )
    if any(
        not context.original_is_current(db, exercise, cite.source_id)
        for cite in suggestion.evidence + suggestion.counterevidence
    ):
        raise AiFailure(409, "AI_SOURCE_UNAVAILABLE", "A cited original is missing or has changed.")
    return CandidateSnapshot(
        **suggestion.model_dump(
            exclude={"save_token", "status", "reviewer_decision", "evidence", "counterevidence"}
        ),
        objective_text=context.ai.objectives[claim.objective_id],
        objective_fingerprint=context.definition_hashes[claim.objective_id],
        context_fingerprint=claim.context_fingerprint,
        evidence=[context.citation(cite) for cite in suggestion.evidence],
        counterevidence=[context.citation(cite) for cite in suggestion.counterevidence],
        provenance=claim.provenance,
    )


def stale_reasons(
    db: Session,
    exercise: Exercise,
    snapshot: CandidateSnapshot,
    context: EvidenceContext,
) -> list[str]:
    reasons = []
    provenance = snapshot.provenance
    if (
        provenance.validator_version != VALIDATOR_VERSION
        or provenance.prompt_version != PROMPT_VERSION
        or provenance.context_version != CONTEXT_VERSION
    ):
        reasons.append("validator_changed")
    if context.definition_hashes.get(snapshot.objective_id) != snapshot.objective_fingerprint:
        reasons.append("objective_changed")
    citations = snapshot.evidence + snapshot.counterevidence
    if any(not context.original_is_current(db, exercise, cite.source_id) for cite in citations):
        reasons.append("source_unavailable")
    current_citations = (
        {cite.observation_id: cite for cite in context.ai.records} if context.ai else {}
    )
    if any(
        context.observations.get(cite.observation_id) != cite.observation_fingerprint
        or cite != context.citation(current_citations[cite.observation_id])
        or contains_workflow_override(current_citations[cite.observation_id].text)
        for cite in citations
    ):
        reasons.append("citation_invalid")
    if context.context_hash != snapshot.context_fingerprint:
        reasons.append("context_changed")
    return reasons
