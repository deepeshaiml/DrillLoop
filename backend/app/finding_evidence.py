"""Source citation checks shared by finding approval and candidate promotion."""

import json

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models import Observation, Source


def stored_evidence_ids(value: str) -> set[str]:
    ids = json.loads(value)
    if not isinstance(ids, list) or not all(isinstance(item, str) for item in ids):
        raise ValueError("Invalid finding citations")
    return set(ids)


def has_source_support(db: Session, exercise_id: str, evidence_ids_json: str) -> bool:
    try:
        evidence_ids = json.loads(evidence_ids_json)
    except (json.JSONDecodeError, RecursionError):
        return False
    if not isinstance(evidence_ids, list) or not evidence_ids:
        return False
    if any(
        not isinstance(item, str)
        or not 1 <= len(item) <= 36
        or item != item.strip()
        or not item.isprintable()
        for item in evidence_ids
    ):
        return False
    if len(set(evidence_ids)) != len(evidence_ids):
        return False

    scoped_observations = (
        select(Observation.source_locator, Observation.text, Source.filename)
        .join(Source, Source.id == Observation.source_id)
        .where(
            Observation.exercise_id == exercise_id,
            Source.exercise_id == exercise_id,
            Source.scan_status.in_(("clean", "not_scanned")),
            # The original download route uses retained text for legacy sources without bytes.
            func.coalesce(
                func.length(Source.source_bytes), func.length(func.trim(Source.content_text))
            )
            > 0,
        )
        .with_for_update(read=True, of=(Observation, Source))
    )
    # Keep large evidence lists within database bind-parameter limits.
    for offset in range(0, len(evidence_ids), 500):
        batch = evidence_ids[offset : offset + 500]
        citations = db.execute(scoped_observations.where(Observation.id.in_(batch))).all()
        if len(citations) != len(batch) or any(
            not (locator.strip() and wording.strip() and filename.strip())
            for locator, wording, filename in citations
        ):
            return False
    return True
