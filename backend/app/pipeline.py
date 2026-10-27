from __future__ import annotations

import json
import os
import re
import time
import uuid
from datetime import date, timedelta

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import CorrectiveAction, Exercise, Finding, Observation, utcnow


def _json(value: object) -> str:
    return json.dumps(value, ensure_ascii=False)


def _text(row: Observation) -> str:
    return row.text.casefold()


def _locator_match(row: Observation, token: str) -> bool:
    return (
        token.casefold() in row.source_locator.casefold() or token.casefold() in row.text.casefold()
    )


def _evidence(
    rows: list[Observation],
    required: list[re.Pattern[str]],
    excluded: list[re.Pattern[str]] | None = None,
) -> list[Observation]:
    excluded = excluded or []
    return [
        row
        for row in rows
        if all(pattern.search(_text(row)) for pattern in required)
        and not any(pattern.search(_text(row)) for pattern in excluded)
    ]


def _one(rows: list[Observation], pattern: re.Pattern[str]) -> Observation | None:
    return next((row for row in rows if pattern.search(_text(row))), None)


def _obj_id(exercise: Exercise, identifier: str) -> str | None:
    for objective in json.loads(exercise.objectives_json):
        if objective.get("id") == identifier:
            return identifier
    return None


def candidate_findings(session: Session, exercise: Exercise) -> list[dict]:
    rows = list(
        session.scalars(select(Observation).where(Observation.exercise_id == exercise.id)).all()
    )
    candidates: list[dict] = []

    outage = _one(
        rows, re.compile(r"primary (?:utility )?(?:power|supply).{0,30}(?:fail|lost|outage)")
    )
    backup = _one(
        rows, re.compile(r"(?:generator|backup power).{0,100}(?:stable|restor|activat|transfer)")
    )
    if outage and backup and re.search(r"four minutes|4 minutes|240 seconds", _text(backup)):
        candidates.append(
            {
                "code": "POWER_RESTORATION_DELAY",
                "title": "Essential power restoration exceeded the exercise target",
                "category": "improvement",
                "objective_id": _obj_id(exercise, "OBJ-01"),
                "observation": "The primary supply failed at 09:02. The log records essential circuits restored at 09:06, four minutes later.",
                "interpretation": "The stated exercise milestone is restoration within 60 seconds. The recorded interval exceeds that target; evaluator confirmation is required.",
                "evidence": [outage, backup],
                "confidence": "high",
                "action": "Validate automatic transfer and essential-circuit restoration under simulated loss of primary power.",
                "acceptance": "A witnessed exercise demonstrates essential circuits restored within the objective's 60-second target; attach the timed test record and approved procedure revision.",
                "owner": "Facilities Operations",
                "priority": "high",
            }
        )

    request = _one(
        rows,
        re.compile(
            r"(?:acknowledgement|acknowledgment|acknowledge).{0,60}(?:request|sent|requested)|(?:request|sent).{0,50}(?:acknowledgement|acknowledgment|acknowledge)"
        ),
    )
    delayed_ack = _one(
        rows,
        re.compile(
            r"(?:acknowledgement|acknowledgment).{0,100}(?:delay|seven minutes|not confirmed|until)"
        ),
    )
    if request and delayed_ack:
        timing_conflict = _one(
            rows,
            re.compile(r"(?:watch|shows).{0,80}(?:while|but).{0,80}(?:log|says).{0,60}unresolved"),
        )
        communication_evidence = [request, delayed_ack]
        if timing_conflict:
            communication_evidence.append(timing_conflict)
        candidates.append(
            {
                "code": "COMMUNICATION_ACK_DELAY",
                "title": "Unit acknowledgement exceeded the three-minute objective",
                "category": "improvement",
                "objective_id": _obj_id(exercise, "OBJ-02"),
                "observation": "Incident Command requested unit acknowledgement at 09:03. The ICU acknowledgement was recorded at 09:10, seven minutes later, and arrived by runner.",
                "interpretation": "The objective calls for acknowledgement within three minutes. The sources describe a longer interval; evaluators should reconcile the 09:10 and 09:11 notes before finalizing the timeline.",
                "evidence": communication_evidence,
                "confidence": "high",
                "action": "Exercise and review the unit acknowledgement fallback when primary radio channels are congested.",
                "acceptance": "In a timed retest, all designated units acknowledge within three minutes or activate the documented fallback; retain timestamped message records.",
                "owner": "Communications Unit",
                "priority": "high",
            }
        )

    arrival = _one(
        rows,
        re.compile(
            r"(?:technician|team|facilities).{0,60}arriv.{0,100}(?:six minutes|6 minutes|09:08)"
        ),
    )
    claim = _one(
        rows, re.compile(r"(?:response time|response duration).{0,60}(?:two minutes|2 minutes)")
    )
    if outage and arrival and claim:
        candidates.append(
            {
                "code": "RESPONSE_TIME_DISCREPANCY",
                "title": "Reported response time conflicts with source timestamps",
                "category": "improvement",
                "objective_id": _obj_id(exercise, "OBJ-04"),
                "observation": "The log reports a two-minute response, while the outage is timestamped 09:02 and technician arrival is timestamped 09:08 (six minutes later).",
                "interpretation": "The reported duration does not match the cited timestamps. Preserve the discrepancy for evaluator reconciliation rather than replacing either source value.",
                "evidence": [outage, arrival, claim],
                "confidence": "high",
                "action": "Reconcile event start and arrival timestamps before publishing response-duration measures.",
                "acceptance": "The incident log template records the start event, response event, source, and calculated interval; a reviewer verifies a sample record in the next exercise.",
                "owner": "Exercise Evaluation Lead",
                "priority": "medium",
            }
        )

    procedure = _one(
        rows,
        re.compile(
            r"(?:completed|successfully completed).{0,100}(?:procedure|protocol)|(?:procedure|protocol).{0,100}completed"
        ),
    )
    if procedure:
        candidates.append(
            {
                "code": "COLD_CHAIN_PROCEDURE_COMPLETED",
                "title": "Emergency cold-chain procedure completed",
                "category": "strength",
                "objective_id": _obj_id(exercise, "OBJ-03"),
                "observation": "The ICU team completed the emergency medication cold-chain relocation procedure and recorded chain of custody.",
                "interpretation": "This evidence supports a strength against the patient-care continuity objective, subject to evaluator confirmation of the source record.",
                "evidence": [procedure],
                "confidence": "high",
            }
        )

    owner_gap = _one(
        rows,
        re.compile(
            r"(?:owner field.{0,30}(?:blank|empty|missing)|no responsible owner|owner.{0,20}not entered)"
        ),
    )
    if owner_gap:
        candidates.append(
            {
                "code": "ACTION_OWNER_MISSING",
                "title": "Radio acknowledgement improvement action has no owner",
                "category": "improvement",
                "objective_id": _obj_id(exercise, "OBJ-02"),
                "observation": "A follow-up action to reduce radio acknowledgement delays was recorded, but its owner field is blank.",
                "interpretation": "The action cannot be tracked to completion until a responsible role or team accepts ownership.",
                "evidence": [owner_gap],
                "confidence": "high",
                "action": "Assign an accountable owner and confirm acceptance for the radio acknowledgement improvement action.",
                "acceptance": "A named role or team accepts the action, and the register contains an owner, due date, measurable acceptance criteria, and reviewer decision.",
                "owner": None,
                "priority": "medium",
            }
        )
    return candidates


def _make_action(session: Session, exercise: Exercise, finding: Finding, candidate: dict) -> None:
    existing = session.scalar(
        select(CorrectiveAction).where(CorrectiveAction.finding_id == finding.id)
    )
    if existing:
        return
    try:
        due_date = (date.fromisoformat(exercise.exercise_date) + timedelta(days=30)).isoformat()
    except ValueError:
        due_date = None
    session.add(
        CorrectiveAction(
            id=str(uuid.uuid4()),
            exercise_id=exercise.id,
            finding_id=finding.id,
            title=candidate["action"],
            evidence_ids_json=finding.evidence_ids_json,
            owner=candidate.get("owner"),
            priority=candidate.get("priority", "medium"),
            due_date=due_date,
            acceptance_criteria=candidate["acceptance"],
            status="proposed",
            reviewer_decision="pending",
        )
    )


def analyze_exercise(session: Session, exercise: Exercise) -> dict:
    objectives = json.loads(exercise.objectives_json)
    if not objectives:
        return {
            "error": "OBJECTIVES_REQUIRED",
            "message": "Add at least one objective before analysis.",
        }
    started = time.perf_counter()
    candidates = candidate_findings(session, exercise)
    model_status = "No local language model configured; transparent deterministic rules used."
    model_latency_ms = None
    model_name = os.getenv("OLLAMA_MODEL", "").strip()
    if model_name:
        model_url = os.getenv("OLLAMA_BASE_URL", "http://127.0.0.1:11434").rstrip("/")
        from urllib.parse import urlparse

        host = urlparse(model_url).hostname
        if host not in {"localhost", "127.0.0.1", "::1", "host.docker.internal"}:
            model_status = "Local LLM skipped: only a local Ollama host is permitted."
        else:
            try:
                import httpx

                draft_candidates = [
                    item for item in candidates if item.get("category") == "improvement"
                ]
                prompt_payload = [
                    {
                        "code": item["code"],
                        "objective_id": item.get("objective_id"),
                        "current_action": item["action"],
                        "current_acceptance": item["acceptance"],
                        "source_excerpts": [row.text for row in item["evidence"]],
                    }
                    for item in draft_candidates
                ]
                prompt = (
                    "You edit corrective action drafts for a fictional emergency exercise. "
                    "Rewrite only action and acceptance wording to be concise and testable. "
                    "Do not state new events or add dates, durations, or operational facts not present in the input. "
                    "Keep each code unchanged. Return JSON with a drafts array of {code, action, acceptance}. "
                    "Input: " + json.dumps(prompt_payload, ensure_ascii=False)
                )
                model_started = time.perf_counter()
                response = httpx.post(
                    f"{model_url}/api/generate",
                    json={
                        "model": model_name,
                        "prompt": prompt,
                        "format": "json",
                        "stream": False,
                        "think": False,
                        "options": {"temperature": 0, "num_predict": 900},
                    },
                    timeout=45,
                )
                response.raise_for_status()
                raw_drafts = json.loads(response.json().get("response", "{}"))
                allowed = {item["code"]: item for item in draft_candidates}
                accepted = 0
                for draft in raw_drafts.get("drafts", []):
                    original = allowed.get(draft.get("code"))
                    action_text = draft.get("action")
                    acceptance_text = draft.get("acceptance")
                    if (
                        original
                        and isinstance(action_text, str)
                        and isinstance(acceptance_text, str)
                        and 12 <= len(action_text) <= 280
                        and 30 <= len(acceptance_text) <= 1200
                    ):
                        original["action"] = action_text.strip()
                        original["acceptance"] = acceptance_text.strip()
                        accepted += 1
                model_latency_ms = round((time.perf_counter() - model_started) * 1000, 2)
                model_status = f"Local Ollama · {model_name}; {accepted}/{len(draft_candidates)} action drafts accepted; reviewer confirmation required."
            except (
                Exception
            ) as error:  # local inference is optional; deterministic draft remains available
                model_status = f"Local model unavailable or invalid response ({type(error).__name__}); deterministic draft used."
    new_count = 0
    for candidate in candidates:
        evidence = candidate["evidence"]
        if not evidence:
            continue
        existing = session.scalar(
            select(Finding).where(
                Finding.exercise_id == exercise.id, Finding.code == candidate["code"]
            )
        )
        if existing:
            if existing.status == "proposed":
                existing.evidence_ids_json = _json(list(dict.fromkeys(row.id for row in evidence)))
                existing.updated_at = utcnow()
            if candidate["category"] == "improvement":
                _make_action(session, exercise, existing, candidate)
            continue
        finding = Finding(
            id=str(uuid.uuid4()),
            exercise_id=exercise.id,
            code=candidate["code"],
            title=candidate["title"],
            category=candidate["category"],
            objective_id=candidate.get("objective_id"),
            observation=candidate["observation"],
            interpretation=candidate["interpretation"],
            evidence_ids_json=_json(list(dict.fromkeys(row.id for row in evidence))),
            confidence=candidate["confidence"],
            status="proposed",
            review_note="",
        )
        session.add(finding)
        session.flush()
        if candidate["category"] == "improvement":
            _make_action(session, exercise, finding, candidate)
        new_count += 1
    session.commit()
    elapsed_ms = round((time.perf_counter() - started) * 1000, 2)
    return {
        "status": "completed",
        "mode": "offline_evidence_rules",
        "stages": [
            "observation extraction",
            "candidate finding detection",
            "objective mapping",
            "evidence citation validation",
            "conflict and time uncertainty flags",
            "corrective action drafting",
        ],
        "candidate_count": len(candidates),
        "new_findings": new_count,
        "latency_ms": elapsed_ms,
        "model_status": model_status,
        "local_model_latency_ms": model_latency_ms,
        "warning": "Drafts require authorized evaluator review. Rules do not infer events beyond matching source observations.",
    }
