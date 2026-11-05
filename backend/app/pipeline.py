from __future__ import annotations

import json
import re
import time
import uuid
from datetime import date, datetime

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import CorrectiveAction, Exercise, Finding, Observation, utcnow

_TIME_RE = re.compile(r"\b(\d{1,2}:\d{2}(?::\d{2})?)\b")
_DURATION_RE = re.compile(
    r"\b(\d+(?:\.\d+)?|zero|one|two|three|four|five|six|seven|eight|nine|ten)\s*"
    r"(seconds?|minutes?|hours?)\b",
    re.IGNORECASE,
)
_NUMBER_WORDS = {
    "zero": 0,
    "one": 1,
    "two": 2,
    "three": 3,
    "four": 4,
    "five": 5,
    "six": 6,
    "seven": 7,
    "eight": 8,
    "nine": 9,
    "ten": 10,
}


def _json(value: object) -> str:
    return json.dumps(value, ensure_ascii=False)


def _terms(rule: dict, name: str) -> list[str]:
    value = rule.get(name, [])
    if not isinstance(value, list):
        return []
    return [item.strip().casefold() for item in value if isinstance(item, str) and item.strip()]


def _matches(row: Observation, terms: list[str]) -> bool:
    text = row.text.casefold()
    return bool(terms) and any(term in text for term in terms)


def _matching_rows(rows: list[Observation], terms: list[str]) -> list[Observation]:
    return [row for row in rows if _matches(row, terms)]


def _row_time(row: Observation) -> datetime | None:
    if not row.event_time_normalized or row.time_confidence in {"unknown", "uncertain"}:
        return None
    try:
        return datetime.fromisoformat(row.event_time_normalized)
    except ValueError:
        return None


def _grouped_times(rows: list[Observation]) -> dict[datetime, list[Observation]]:
    groups: dict[datetime, list[Observation]] = {}
    for row in rows:
        value = _row_time(row)
        if value is not None:
            groups.setdefault(value, []).append(row)
    return groups


def _clock_claims(
    rows: list[Observation], terms: list[str], exercise_date: date
) -> dict[datetime, list[Observation]]:
    claims: dict[datetime, list[Observation]] = {}
    for row in _matching_rows(rows, terms):
        for match in _TIME_RE.finditer(row.text):
            value = match.group(1)
            fmt = "%H:%M:%S" if value.count(":") == 2 else "%H:%M"
            try:
                parsed = datetime.combine(exercise_date, datetime.strptime(value, fmt).time())
            except ValueError:
                continue
            claims.setdefault(parsed, []).append(row)
    return claims


def _duration_seconds(rows: list[Observation], terms: list[str]) -> dict[int, list[Observation]]:
    results: dict[int, list[Observation]] = {}
    for row in _matching_rows(rows, terms):
        for match in _DURATION_RE.finditer(row.text):
            number_text, unit = match.groups()
            amount = _NUMBER_WORDS.get(number_text.casefold())
            if amount is None:
                try:
                    amount = float(number_text)
                except ValueError:
                    continue
            multiplier = 1 if unit.casefold().startswith("second") else 60
            if unit.casefold().startswith("hour"):
                multiplier = 3600
            seconds = round(float(amount) * multiplier)
            results.setdefault(seconds, []).append(row)
    return results


def _evidence_rows(*groups: dict[object, list[Observation]]) -> list[Observation]:
    seen: set[str] = set()
    result: list[Observation] = []
    for group in groups:
        for rows in group.values():
            for row in rows:
                if row.id not in seen:
                    seen.add(row.id)
                    result.append(row)
    return result


def _evidence_refs(rows: list[Observation]) -> list[dict]:
    return [
        {
            "observation_id": row.id,
            "source_id": row.source_id,
            "source_locator": row.source_locator,
            "source_wording": row.text,
            "timestamp": row.event_time_normalized,
            "time_confidence": row.time_confidence,
        }
        for row in rows
    ]


def _base_assessment(objective: dict) -> dict:
    objective_id = objective.get("id")
    return {
        "objective_id": objective_id if isinstance(objective_id, str) else None,
        "objective_text": objective.get("text", "")
        if isinstance(objective.get("text"), str)
        else "",
        "state": "needs_review",
        "rule_type": None,
        "threshold_seconds": None,
        "elapsed_seconds": [],
        "evidence": [],
        "unknowns": [],
        "conflicts": [],
    }


def _duration_threshold(objective: dict, rule: dict) -> int | None:
    explicit = rule.get("threshold_seconds")
    if isinstance(explicit, int) and explicit >= 0:
        return explicit
    candidates = [objective.get("text", ""), objective.get("success_criteria", "")]
    criteria = objective.get("criteria", [])
    if isinstance(criteria, list):
        candidates.extend(item for item in criteria if isinstance(item, str))
    values: set[int] = set()
    for text in candidates:
        if not isinstance(text, str):
            continue
        for amount_text, unit in _DURATION_RE.findall(text):
            amount = _NUMBER_WORDS.get(amount_text.casefold())
            if amount is None:
                try:
                    amount = float(amount_text)
                except ValueError:
                    continue
            multiplier = 1 if unit.casefold().startswith("second") else 60
            if unit.casefold().startswith("hour"):
                multiplier = 3600
            values.add(round(float(amount) * multiplier))
    return next(iter(values)) if len(values) == 1 else None


def _make_candidate(
    objective: dict,
    rule: dict,
    assessment: dict,
    rows: list[Observation],
    *,
    failure: bool,
    observation_detail: str,
    interpretation_detail: str,
) -> dict:
    objective_id = assessment["objective_id"] or "unknown"
    generated_suffix = "NOT_MET" if failure else "MET"
    code = rule.get("finding_code")
    if not isinstance(code, str) or not code.strip():
        slug = re.sub(r"[^A-Za-z0-9]+", "_", objective_id).strip("_").upper()[:48]
        code = f"OBJECTIVE_{slug}_{generated_suffix}"
    title = rule.get("finding_title")
    if not isinstance(title, str) or not title.strip():
        title = f"Objective {objective_id}: target {'not met' if failure else 'met'}"

    citations = " | ".join(f"{row.source_id} · {row.source_locator}: “{row.text}”" for row in rows)
    observation = (
        f"Source wording: {citations}. {observation_detail}" if citations else observation_detail
    )
    interpretation = (
        f"Objective {objective_id}: {assessment['objective_text']} "
        f"{interpretation_detail} Reviewer decision: pending."
    )
    return {
        "code": code,
        "title": title,
        "category": "improvement" if failure else "strength",
        "objective_id": assessment["objective_id"],
        "observation": observation,
        "interpretation": interpretation,
        "evidence": rows,
        "confidence": "medium" if assessment["conflicts"] else "high",
        "action": f"Evaluator review of objective {objective_id} against the cited evidence.",
        "acceptance": f"An authorized evaluator records a decision for objective {objective_id} and cites the reviewed evidence.",
    }


def _elapsed_assessment(
    rows: list[Observation], objective: dict, rule: dict, exercise_date: date
) -> tuple[dict, dict | None]:
    result = _base_assessment(objective)
    result["rule_type"] = "elapsed_time"
    threshold = _duration_threshold(objective, rule)
    result["threshold_seconds"] = threshold
    if threshold is None:
        result["unknowns"].append("No single explicit time threshold was provided.")
        return result, None
    start_terms = _terms(rule, "start_terms")
    completion_terms = _terms(rule, "completion_terms")
    if not start_terms or not completion_terms:
        result["unknowns"].append(
            "Start and completion event terms are required to measure elapsed time."
        )
        return result, None

    start_rows = _matching_rows(rows, start_terms)
    completion_rows = _matching_rows(rows, completion_terms)
    starts = _grouped_times(start_rows)
    completions = _grouped_times(completion_rows)
    claimed_completions = _clock_claims(rows, _terms(rule, "completion_claim_terms"), exercise_date)
    all_completions = {**completions}
    for value, supporting_rows in claimed_completions.items():
        all_completions.setdefault(value, []).extend(supporting_rows)

    evidence = _evidence_rows(starts, all_completions)
    result["evidence"] = _evidence_refs(evidence)
    if not starts:
        result["state"] = "insufficient_information"
        result["unknowns"].append(
            "No source-matched start event with a usable timestamp was found."
        )
        if start_rows:
            result["evidence"] = _evidence_refs(start_rows)
            result["unknowns"].append("Matching start evidence has missing or uncertain time.")
        return result, None
    if len(starts) != 1:
        result["state"] = "conflicting_evidence"
        result["conflicts"].append(
            "More than one distinct start timestamp matches the objective rule."
        )
        return result, None
    if not all_completions:
        result["state"] = "insufficient_information"
        result["unknowns"].append(
            "No source-matched completion event with a usable timestamp was found."
        )
        if completion_rows:
            result["unknowns"].append("Matching completion evidence has missing or uncertain time.")
        return result, None

    start_time = next(iter(starts))
    if any((start_time.tzinfo is None) != (value.tzinfo is None) for value in all_completions):
        result["state"] = "insufficient_information"
        result["unknowns"].append(
            "Timestamp timezone information is inconsistent; elapsed time was not inferred."
        )
        return result, None
    elapsed = sorted({round((value - start_time).total_seconds()) for value in all_completions})
    result["elapsed_seconds"] = elapsed
    if not elapsed or any(value < 0 for value in elapsed):
        result["state"] = "conflicting_evidence"
        result["conflicts"].append("A completion timestamp precedes the matched start timestamp.")
        return result, None

    outcomes = {value <= threshold for value in elapsed}
    if len(outcomes) > 1:
        result["state"] = "conflicting_evidence"
        result["conflicts"].append(
            "Conflicting completion timestamps produce different threshold outcomes."
        )
        return result, None
    failure = not next(iter(outcomes))
    has_conflicting_values = len(all_completions) > 1
    result["state"] = (
        ("confirmed_failure_with_conflict" if failure else "confirmed_success_with_conflict")
        if has_conflicting_values
        else ("confirmed_failure" if failure else "confirmed_success")
    )
    if has_conflicting_values:
        result["conflicts"].append(
            "Multiple source-supported completion timestamps are present; all produce the same threshold result."
        )
    observation_detail = (
        f"Calculated elapsed time(s): {', '.join(str(value) for value in elapsed)} seconds."
    )
    interpretation_detail = (
        f"The objective threshold is {threshold} seconds. Calculated elapsed time(s): "
        f"{', '.join(str(value) for value in elapsed)} seconds; "
        f"the target was {'exceeded' if failure else 'met'}."
    )
    if result["conflicts"]:
        interpretation_detail += " Conflicting source times remain visible for evaluator review."
    candidate = _make_candidate(
        objective,
        rule,
        result,
        evidence,
        failure=failure,
        observation_detail=observation_detail,
        interpretation_detail=interpretation_detail,
    )
    return result, candidate


def _reported_duration_assessment(
    rows: list[Observation], objective: dict, rule: dict, exercise_date: date
) -> tuple[dict, dict | None]:
    result = _base_assessment(objective)
    result["rule_type"] = "reported_duration"
    starts = _grouped_times(_matching_rows(rows, _terms(rule, "start_terms")))
    completions = _grouped_times(_matching_rows(rows, _terms(rule, "completion_terms")))
    claims = _duration_seconds(rows, _terms(rule, "claim_terms"))
    evidence = _evidence_rows(starts, completions, claims)
    result["evidence"] = _evidence_refs(evidence)
    if len(starts) != 1 or len(completions) != 1 or not claims:
        result["state"] = "insufficient_information"
        result["unknowns"].append(
            "One start time, one completion time, and a source-stated duration are required for comparison."
        )
        return result, None
    start_time = next(iter(starts))
    completion_time = next(iter(completions))
    if (start_time.tzinfo is None) != (completion_time.tzinfo is None):
        result["state"] = "insufficient_information"
        result["unknowns"].append("Timestamp timezone information is inconsistent.")
        return result, None
    measured = round((completion_time - start_time).total_seconds())
    reported = list(claims)
    if measured < 0:
        result["state"] = "conflicting_evidence"
        result["conflicts"].append("The completion timestamp precedes the start timestamp.")
        return result, None
    if len(reported) != 1:
        result["state"] = "conflicting_evidence"
        result["conflicts"].append("The source records contain more than one reported duration.")
        return result, None
    claimed = reported[0]
    failure = claimed != measured
    result["elapsed_seconds"] = [measured]
    result["reported_seconds"] = claimed
    result["state"] = "confirmed_failure" if failure else "confirmed_success"
    candidate = _make_candidate(
        objective,
        rule,
        result,
        evidence,
        failure=failure,
        observation_detail=f"Calculated interval: {measured} seconds; source-stated interval: {claimed} seconds.",
        interpretation_detail=(
            f"The source-stated interval ({claimed} seconds) "
            f"{'does not match' if failure else 'matches'} the interval calculated from cited timestamps ({measured} seconds)."
        ),
    )
    return result, candidate


def _presence_assessment(
    rows: list[Observation], objective: dict, rule: dict
) -> tuple[dict, dict | None]:
    result = _base_assessment(objective)
    result["rule_type"] = "event_presence"
    matched = _matching_rows(rows, _terms(rule, "terms"))
    result["evidence"] = _evidence_refs(matched)
    if not matched:
        result["state"] = "insufficient_information"
        result["unknowns"].append(
            "No matching evidence was found; absence is not treated as objective failure."
        )
        return result, None
    result["state"] = "confirmed_success"
    candidate = _make_candidate(
        objective,
        rule,
        result,
        matched,
        failure=False,
        observation_detail="The cited source wording matches the configured event criterion.",
        interpretation_detail="The configured event-presence criterion is supported by the cited source wording.",
    )
    return result, candidate


def _required_field_assessment(
    rows: list[Observation], objective: dict, rule: dict
) -> tuple[dict, dict | None]:
    result = _base_assessment(objective)
    result["rule_type"] = "required_field"
    missing = _matching_rows(rows, _terms(rule, "missing_terms"))
    present = _matching_rows(rows, _terms(rule, "present_terms"))
    if missing and present:
        result["state"] = "conflicting_evidence"
        result["evidence"] = _evidence_refs([*missing, *present])
        result["conflicts"].append(
            "Sources explicitly report both the required field missing and present."
        )
        return result, None
    if missing:
        result["state"] = "confirmed_failure"
        evidence = missing
        failure = True
    elif present:
        result["state"] = "confirmed_success"
        evidence = present
        failure = False
    else:
        result["state"] = "insufficient_information"
        result["unknowns"].append(
            "No source explicitly confirms whether the required field is present or missing."
        )
        return result, None
    result["evidence"] = _evidence_refs(evidence)
    candidate = _make_candidate(
        objective,
        rule,
        result,
        evidence,
        failure=failure,
        observation_detail="The required field state is stated directly in the cited evidence.",
        interpretation_detail=(
            "The cited evidence explicitly reports the required field missing."
            if failure
            else "The cited evidence explicitly reports the required field present."
        ),
    )
    return result, candidate


def _evaluate_all(session: Session, exercise: Exercise) -> list[dict]:
    rows = list(
        session.scalars(select(Observation).where(Observation.exercise_id == exercise.id)).all()
    )
    try:
        exercise_date = date.fromisoformat(exercise.exercise_date)
    except ValueError:
        exercise_date = None
    outcomes = []
    objectives = json.loads(exercise.objectives_json)
    if not isinstance(objectives, list):
        return outcomes
    for objective in objectives:
        if not isinstance(objective, dict):
            continue
        rule = objective.get("evaluation_rule") or objective.get("rule")
        if not isinstance(rule, dict):
            assessment = _base_assessment(objective)
            assessment["unknowns"].append(
                "No explicit deterministic evaluation rule is configured for this objective."
            )
            outcomes.append({"assessment": assessment, "candidate": None})
            continue
        rule_type = rule.get("type")
        if rule_type == "elapsed_time":
            assessment, candidate = _elapsed_assessment(
                rows, objective, rule, exercise_date or date.min
            )
        elif rule_type == "reported_duration":
            assessment, candidate = _reported_duration_assessment(
                rows, objective, rule, exercise_date or date.min
            )
        elif rule_type == "event_presence":
            assessment, candidate = _presence_assessment(rows, objective, rule)
        elif rule_type == "required_field":
            assessment, candidate = _required_field_assessment(rows, objective, rule)
        else:
            assessment = _base_assessment(objective)
            assessment["rule_type"] = str(rule_type) if rule_type else None
            assessment["unknowns"].append("The configured rule type is unsupported.")
            candidate = None
        outcomes.append({"assessment": assessment, "candidate": candidate})
    return outcomes


def objective_assessments(session: Session, exercise: Exercise) -> list[dict]:
    return [item["assessment"] for item in _evaluate_all(session, exercise)]


def candidate_findings(session: Session, exercise: Exercise) -> list[dict]:
    return [
        item["candidate"]
        for item in _evaluate_all(session, exercise)
        if item["candidate"] is not None
    ]


def _make_action(session: Session, exercise: Exercise, finding: Finding, candidate: dict) -> None:
    existing = session.scalar(
        select(CorrectiveAction).where(CorrectiveAction.finding_id == finding.id)
    )
    if existing:
        if existing.reviewer_decision == "pending" and existing.status == "proposed":
            existing.title = candidate["action"]
            existing.evidence_ids_json = finding.evidence_ids_json
            existing.acceptance_criteria = candidate["acceptance"]
            existing.updated_at = utcnow()
        return
    session.add(
        CorrectiveAction(
            id=str(uuid.uuid4()),
            exercise_id=exercise.id,
            finding_id=finding.id,
            title=candidate["action"],
            evidence_ids_json=finding.evidence_ids_json,
            owner=None,
            priority="medium",
            due_date=None,
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
    outcomes = _evaluate_all(session, exercise)
    candidates = [item["candidate"] for item in outcomes if item["candidate"] is not None]
    candidate_codes = {item["code"] for item in candidates}
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
            if existing.status in {"proposed", "stale"}:
                existing.status = "proposed"
                existing.title = candidate["title"]
                existing.category = candidate["category"]
                existing.objective_id = candidate.get("objective_id")
                existing.observation = candidate["observation"]
                existing.interpretation = candidate["interpretation"]
                existing.evidence_ids_json = _json(list(dict.fromkeys(row.id for row in evidence)))
                existing.confidence = candidate["confidence"]
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

    for finding in session.scalars(select(Finding).where(Finding.exercise_id == exercise.id)).all():
        if finding.status == "proposed" and finding.code not in candidate_codes:
            finding.status = "stale"
            finding.updated_at = utcnow()

    session.commit()
    assessments = [item["assessment"] for item in outcomes]
    unresolved = sum(1 for item in assessments if not item["state"].startswith("confirmed_"))
    return {
        "status": "completed_with_unknowns" if unresolved else "completed",
        "mode": "offline_objective_rules",
        "stages": [
            "objective rule validation",
            "timestamp and duration calculation",
            "source-level evidence matching",
            "conflict and uncertainty classification",
            "proposed finding and action drafting",
        ],
        "candidate_count": len(candidates),
        "new_findings": new_count,
        "latency_ms": round((time.perf_counter() - started) * 1000, 2),
        "model_status": "No model response is used to determine findings or measurements.",
        "local_model_latency_ms": None,
        "objective_assessments": assessments,
        "warning": "All findings remain proposed for authorized human review. Unknown or conflicting objectives are not converted into failures.",
    }
