"""Phase 4C.4 contract checks on disposable databases with fictional evidence."""

from __future__ import annotations

import json
import os
import threading
import uuid
from concurrent.futures import ThreadPoolExecutor
from contextlib import contextmanager
from functools import partial
from io import BytesIO
from pathlib import Path

import pytest
from alembic import command
from app import ai_candidates, main
from app import db as database
from app.ai_evaluation import AiService
from app.db import SessionLocal
from app.models import (
    AiCandidate,
    AiCandidatePromotion,
    AiCandidateRequest,
    AuditEvent,
    CorrectiveAction,
    Exercise,
    Finding,
    Observation,
)
from fastapi.testclient import TestClient
from pypdf import PdfReader
from sqlalchemy import create_engine, select, text, update
from sqlalchemy.exc import IntegrityError, OperationalError
from sqlalchemy.orm import Session
from test_ai_candidates import (
    CANDIDATES,
    EXERCISE,
    ID,
    OBJECTIVES,
    WORDING,
    add_transcript,
    configure_provider,
    create_exercise,
    entry,
    grant,
    login,
    persisted,
    prepare,
    review,
    upload_text,
)

FIELDS = {
    "title": "Fictional backup panel handoff documented",
    "observation": WORDING,
    "interpretation": "The log documents the exercise handoff. Its event time remains unknown.",
    "category": "strength",
    "objective_id": "OBJ",
    "confirmed": True,
}
PG_TEST_URL = os.getenv("DRILLLOOP_PROMOTION_TEST_POSTGRES_URL")
RULE = {"type": "event_presence", "terms": ["backup panel handoff"]}


@contextmanager
def disposable_database():
    if not PG_TEST_URL:
        root = Path(os.environ["DRILLLOOP_TEST_DB_ROOT"])
        engine = database.create_database_engine(
            f"sqlite:///{root / f'test-{uuid.uuid4().hex}.sqlite3'}"
        )
        try:
            yield engine
        finally:
            engine.dispose()
        return

    bootstrap = create_engine(PG_TEST_URL)
    schema = f"drillloop_promotion_test_{uuid.uuid4().hex}"
    with bootstrap.begin() as connection:
        connection.execute(text(f"CREATE SCHEMA {schema}"))
    engine = create_engine(PG_TEST_URL, connect_args={"options": f"-csearch_path={schema}"})
    try:
        yield engine
    finally:
        engine.dispose()
        with bootstrap.begin() as connection:
            connection.execute(text(f"DROP SCHEMA {schema} CASCADE"))
        bootstrap.dispose()


@pytest.fixture
def promotion_client(request):
    if not PG_TEST_URL:
        yield request.getfixturevalue("client")
        return
    with disposable_database() as engine:
        database.migrate_database(engine)
        previous = database.engine
        database.engine = engine
        SessionLocal.configure(bind=engine)
        try:
            with TestClient(main.app) as client:
                login(client, "test-admin")
                yield client
        finally:
            SessionLocal.configure(bind=previous)
            database.engine = previous


def accept(client, key="save-1"):
    _, candidate_id = persisted(client, key)
    url = f"{CANDIDATES}/{candidate_id}"
    assert review(client, url, "accepted_for_consideration", key=key).status_code == 200
    return url


def promote(client, url, *, version='"2"', key="promote-1", **fields):
    headers = {}
    if version is not None:
        headers["If-Match"] = version
    if key is not None:
        headers["Idempotency-Key"] = key
    return client.post(f"{url}/promote", json={**FIELDS, **fields}, headers=headers)


def assert_no_promotions():
    with SessionLocal() as db:
        assert not db.scalars(select(Finding)).all()
        assert not db.scalars(select(CorrectiveAction)).all()
        assert not db.scalars(select(AiCandidatePromotion)).all()
        assert not db.scalars(
            select(AuditEvent).where(AuditEvent.action == ai_candidates.PROMOTED)
        ).all()
        assert not db.scalars(
            select(AiCandidateRequest).where(AiCandidateRequest.operation == "promote")
        ).all()


@pytest.mark.parametrize("decision", ["approved", "rejected"])
def test_promotion_persists_without_ai_and_uses_independent_finding_review(
    promotion_client, decision
):
    client = promotion_client
    provider = prepare(client)
    grant(client, "test-reviewer")
    url = accept(client)
    assert_no_promotions()
    reviewer = TestClient(main.app)
    login(reviewer, "test-reviewer")
    main.app.state.ai_evaluation = AiService(None)
    response = promote(reviewer, url)
    assert response.status_code == 201, response.text
    assert response.headers["cache-control"] == "no-store"
    outcome = response.json()
    finding_id = outcome["finding_id"]
    assert outcome["finding_status"] == "proposed" and outcome["version"] == 3
    detail = client.get(EXERCISE).json()
    (finding,) = detail["findings"]
    assert finding["id"] == finding_id and finding["source_candidate_id"] == outcome["id"]
    assert finding["status"] == "proposed" and finding["reviewer"] is None
    assert finding["review_note"] == "" and finding["confidence"] == "unrated"
    assert all(
        finding[name] == FIELDS[name]
        for name in ("title", "observation", "interpretation", "category", "objective_id")
    )
    (citation,) = finding["supporting_evidence"]
    assert citation["text"] == WORDING and citation["source_locator"] == "segment 1 · 4.00–7.00s"
    assert citation["event_time_raw"] is None and citation["event_time_normalized"] is None
    assert detail["actions"] == []
    candidate = client.get(url).json()
    assert candidate["reviewer_decision"] == "accepted_for_consideration"
    assert candidate["linked_finding"]["id"] == finding_id
    assert candidate["promoted"] and client.get(CANDIDATES).json()["candidates"][0]["promoted"]
    assert [event["operation"] for event in candidate["history"]] == [
        "ai_candidate_saved",
        "ai_candidate_reviewed",
        "ai_candidate_promoted",
    ]
    event = candidate["history"][-1]
    assert event["actor_user_id"] == "test-reviewer" and event["finding_id"] == finding_id
    assert event["wording_confirmed"] and event["request_id"] == response.headers["x-request-id"]
    assert candidate["evidence"][0]["observation_id"] == finding["evidence_ids"][0]
    assert provider.calls == 1
    assert promote(reviewer, url).json() == outcome
    assert (
        promote(reviewer, url, title="Different confirmed title").json()["detail"]["code"]
        == "IDEMPOTENCY_CONFLICT"
    )
    assert (
        promote(reviewer, url, key="different", version='"3"').json()["detail"]["code"]
        == "CANDIDATE_ALREADY_PROMOTED"
    )
    assert review(client, url, "rejected", version=3, key="closed").status_code == 409

    with TestClient(main.app) as restarted:
        login(restarted, "test-reviewer")
        assert restarted.get(url).json() == candidate
        assert client.post(f"{EXERCISE}/analyze").status_code == 200
        assert client.get(EXERCISE).json()["findings"] == [finding]
        decided = restarted.post(
            f"/api/findings/{finding_id}/review",
            json={"decision": decision, "note": "Separate fictional finding decision."},
        )
        assert decided.status_code == 200, decided.text
        assert restarted.get(url).json()["linked_finding"]["status"] == decision
        assert promote(restarted, url).json() == outcome
        report = restarted.get(f"{EXERCISE}/report.pdf")
        assert report.status_code == 200 and report.content.startswith(b"%PDF-")
        report_text = " ".join(
            page.extract_text() for page in PdfReader(BytesIO(report.content)).pages
        )
        assert "Human-confirmed interpretation" in report_text
        assert f"Source AI candidate: {outcome['id']}" in report_text
        assert "fictional-transcript.json" in report_text
        detail = restarted.get(EXERCISE).json()
        assert detail["actions"] == []
        assert any(
            event["action"] == f"finding_{decision}" and event["object_id"] == finding_id
            for event in detail["audit_events"]
        )
    assert client.delete(f"{EXERCISE}/access/test-reviewer").status_code == 200
    assert promote(reviewer, url).status_code == 404


@pytest.mark.parametrize("decision", [None, "rejected", "more_evidence_required"])
def test_unaccepted_candidates_cannot_be_promoted(promotion_client, decision):
    client = promotion_client
    prepare(client)
    _, candidate_id = persisted(client)
    url = f"{CANDIDATES}/{candidate_id}"
    if decision:
        assert (
            review(
                client, url, decision, note="Additional fictional evidence.", key="decide"
            ).status_code
            == 200
        )
    response = promote(client, url, version='"2"' if decision else '"1"')
    assert response.status_code == 409
    assert response.json()["detail"]["code"] == "CANDIDATE_PROMOTION_INELIGIBLE"
    assert_no_promotions()


def test_headers_payload_and_live_access_checks(promotion_client, monkeypatch):
    client = promotion_client
    prepare(client)
    url = accept(client)
    assert promote(client, url, key=None).status_code == 428
    assert promote(client, url, version=None).status_code == 428
    assert promote(client, url, version="2").status_code == 422
    assert promote(client, url, version='"1"').status_code == 412
    for invalid in (
        {"title": "    "},
        {"interpretation": "Text\x00with null"},
        {"confirmed": False},
        {"confirmed": 1},
        {"category": "neutral"},
        {"objective_id": "OTHER"},
        {"reviewer": "forged"},
        {"evidence_ids": ["arbitrary"]},
        {"status": "approved"},
        {"event_time": "10:24"},
        {"cause": "Unverified cause"},
        {"owner": "Invented"},
        {"due_date": "2026-12-01"},
    ):
        assert promote(client, url, **invalid).status_code == 422
    for user, expected in [
        ("test-evaluator", 403),
        ("test-viewer", 403),
        ("other-admin", 404),
        ("test-reviewer", 404),
    ]:
        if user in {"test-evaluator", "test-viewer"}:
            grant(client, user)
        stranger = TestClient(main.app)
        login(stranger, user)
        assert promote(stranger, url).status_code == expected
    grant(client, "test-reviewer")
    reviewer = TestClient(main.app)
    login(reviewer, "test-reviewer", csrf=False)
    assert promote(reviewer, url).json()["detail"]["code"] == "CSRF_TOKEN_REQUIRED"
    assert promote(TestClient(main.app), url).status_code == 401
    create_exercise(client, "FICTIONAL-PROMOTION-OTHER")
    assert promote(client, url.replace(ID, "FICTIONAL-PROMOTION-OTHER")).status_code == 404
    login(reviewer, "test-reviewer")
    assert client.delete(f"{EXERCISE}/access/test-reviewer").status_code == 200
    assert promote(reviewer, url).status_code == 404
    users = json.loads(os.environ["DRILLLOOP_USERS_JSON"])
    monkeypatch.setenv(
        "DRILLLOOP_USERS_JSON",
        json.dumps([user for user in users if user["id"] != "test-reviewer"]),
    )
    assert promote(reviewer, url).status_code == 401
    assert_no_promotions()


@pytest.mark.parametrize(
    "change", ["missing", "fabricated", "cross_exercise", "objective", "original"]
)
def test_invalid_citations_and_stale_context_fail_closed(promotion_client, monkeypatch, change):
    client = promotion_client
    prepare(client)
    url = accept(client)
    candidate = client.get(url).json()
    citation = candidate["evidence"][0]
    if change in {"missing", "fabricated"}:
        original = ai_candidates._snapshot

        def altered(row):
            snapshot = original(row)
            evidence = (
                []
                if change == "missing"
                else [snapshot.evidence[0].model_copy(update={"text": "Fabricated wording."})]
            )
            return snapshot.model_copy(update={"evidence": evidence})

        monkeypatch.setattr(ai_candidates, "_snapshot", altered)
    elif change == "cross_exercise":
        create_exercise(client, "FICTIONAL-PROMOTION-OTHER")
        other_source = add_transcript(
            client, WORDING, exercise="/api/exercises/FICTIONAL-PROMOTION-OTHER"
        )
        with SessionLocal.begin() as db:
            db.get(Observation, citation["observation_id"]).source_id = other_source
    elif change == "objective":
        with SessionLocal.begin() as db:
            db.get(Exercise, ID).objectives_json = json.dumps(
                [{"id": "OBJ", "text": "Changed fictional objective."}]
            )
    else:
        with SessionLocal.begin() as db:
            db.get(main.Source, citation["source_id"]).source_bytes = None
    result = promote(client, url)
    assert result.status_code == 409, result.text
    if change != "missing":
        assert result.json()["detail"]["code"] == "AI_CANDIDATE_STALE"
        stale = client.get(url).json()
        assert stale["freshness"] == "stale" and stale["version"] == 3
        assert {"objective": "objective_changed", "original": "source_unavailable"}.get(
            change, "citation_invalid"
        ) in stale["stale_reasons"]
        assert stale["history"][-1]["operation"] == "ai_candidate_invalidated"
    assert_no_promotions()


@pytest.mark.parametrize(
    "kind,unknowns",
    [
        ("relevant_observation", ("cause_verification",)),
        ("relevant_observation", ("event_identity",)),
        ("contradiction", ()),
    ],
)
def test_ambiguous_cause_identity_and_discrepancy_remain_reviewable(
    promotion_client, kind, unknowns
):
    client = promotion_client
    create_exercise(client)
    first = "Fictional exercise observer thought the panel might have affected the dispatch log."
    second = (
        "Fictional controller reported that the dispatch log was available during the exercise."
    )
    upload_text(client, "fictional-contrasting-notes.txt", first, second)
    cites = [(1, first), (2, second)] if kind == "contradiction" else [(1, first)]
    configure_provider(entry(*cites, kind=kind, unknowns=unknowns))
    url = accept(client)
    assert client.get(url).json()["promotion_block_reason"]
    denied = promote(client, url)
    assert (
        denied.status_code == 409
        and denied.json()["detail"]["code"] == "CANDIDATE_PROMOTION_INELIGIBLE"
    )
    assert_no_promotions()


def test_corroboration_preserves_both_originals_and_uncertain_ocr_time(promotion_client):
    client = promotion_client
    create_exercise(client)
    upload_text(client, "fictional-log.txt", WORDING)
    second = "The fictional evaluator also recorded the handoff in the exercise notes."
    source_id = add_transcript(client, second)
    with SessionLocal.begin() as db:
        db.execute(
            update(Observation)
            .where(Observation.source_id == source_id)
            .values(
                extraction_method="ocr",
                time_confidence="uncertain",
                source_locator="page 3",
                event_time_raw="14:11",
                event_time_normalized=None,
            )
        )
    configure_provider(entry((1, WORDING), (2, second), kind="corroboration"))
    url = accept(client)
    assert client.get(url).json()["kind"] == "corroboration"
    assert promote(client, url).status_code == 201
    (finding,) = client.get(EXERCISE).json()["findings"]
    assert len(finding["evidence_ids"]) == 2
    ocr = next(cite for cite in finding["supporting_evidence"] if cite["source_id"] == source_id)
    assert ocr["event_time_raw"] == "14:11" and ocr["event_time_normalized"] is None
    assert (ocr["source_locator"], ocr["text"], ocr["time_confidence"]) == (
        "page 3",
        second,
        "uncertain",
    )


def test_audit_write_failure_and_verification_outage_roll_back(promotion_client, monkeypatch):
    client = promotion_client
    prepare(client)
    url = accept(client)

    def outage(*_args, **_kwargs):
        raise OperationalError("fictional fixture unavailable", None, None)

    with monkeypatch.context() as failed:
        failed.setattr(ai_candidates, "load_evidence", outage)
        assert promote(client, url).status_code == 503
    with monkeypatch.context() as failed:
        failed.setattr(ai_candidates, "_audit", outage)
        assert promote(client, url).status_code == 503
    assert client.get(url).headers["etag"] == '"2"'
    assert_no_promotions()
    assert promote(client, url).status_code == 201


def test_distinct_candidates_and_existing_rule_findings_do_not_duplicate(promotion_client):
    client = promotion_client
    objectives = [
        *OBJECTIVES,
        {
            "id": "RULE",
            "text": "Check for the fictional panel completion note.",
            "evaluation_rule": {"type": "event_presence", "terms": ["panel checkout completed"]},
        },
    ]
    create_exercise(client, objectives=objectives)
    checkout = "The fictional evaluator recorded that panel checkout completed."
    add_transcript(client, WORDING, checkout)
    configure_provider(entry((2, checkout), objective="RULE"))
    rule_candidate = accept(client)
    assert (
        promote(client, rule_candidate, objective_id="RULE").json()["detail"]["code"]
        == "FINDING_DUPLICATE"
    )
    assert client.post(f"{EXERCISE}/analyze").status_code == 200
    before = client.get(EXERCISE).json()["findings"]
    assert len(before) == 1 and before[0]["objective_id"] == "RULE"
    assert (
        promote(client, rule_candidate, objective_id="RULE").json()["detail"]["code"]
        == "FINDING_DUPLICATE"
    )
    configure_provider(entry((1, WORDING)))
    first, second = accept(client, "first"), accept(client, "second")
    assert promote(client, first).status_code == 201
    assert (
        promote(
            client, second, key="later", title="Different wording over the same citation"
        ).json()["detail"]["code"]
        == "FINDING_DUPLICATE"
    )
    assert client.post(f"{EXERCISE}/analyze").status_code == 200
    after = client.get(EXERCISE).json()["findings"]
    assert len(after) == 2
    assert next(finding for finding in after if finding["objective_id"] == "RULE") == before[0]
    assert all(finding["status"] == "proposed" for finding in after)


def test_matching_wording_allows_distinct_supporting_observations(promotion_client):
    client = promotion_client
    create_exercise(client)
    second_wording = "The fictional night dispatcher logged a second backup panel handoff."
    add_transcript(client, WORDING, second_wording)
    configure_provider(entry((1, WORDING)))
    first = accept(client, "first")
    configure_provider(entry((2, second_wording)))
    second = accept(client, "second")

    assert promote(client, first).status_code == 201
    result = promote(client, second, key="promote-second", observation=second_wording)
    assert result.status_code == 201, result.text
    one, two = client.get(EXERCISE).json()["findings"]
    assert one["title"] == two["title"]
    assert set(one["evidence_ids"]).isdisjoint(two["evidence_ids"])


def test_new_rule_result_does_not_duplicate_promoted_evidence(promotion_client):
    client = promotion_client
    rule = {
        "type": "elapsed_time",
        "start_terms": ["panel drill began"],
        "completion_terms": ["panel drill ended"],
        "threshold_seconds": 60,
    }
    create_exercise(client, objectives=[{**OBJECTIVES[0], "evaluation_rule": rule}])
    start = "The fictional panel drill began."
    upload_text(client, "fictional-start.txt", f"09:00 {start}")
    configure_provider(entry((1, start), unknowns=("completion_record",)))
    url = accept(client)
    result = promote(
        client,
        url,
        title="Fictional panel drill start recorded",
        observation=start,
        interpretation="The source records the start. It gives no completion time.",
    )
    assert result.status_code == 201, result.text
    before = client.get(EXERCISE).json()["findings"]

    upload_text(client, "fictional-end.txt", "09:02 The fictional panel drill ended.")
    for _ in range(2):
        analysis = client.post(f"{EXERCISE}/analyze").json()
        assert analysis["objective_assessments"][0]["state"] == "confirmed_failure"
        assert analysis["new_findings"] == 0
    detail = client.get(EXERCISE).json()
    assert detail["findings"] == before
    assert detail["actions"] == []


def test_rule_conflict_blocks_a_one_sided_advisory_candidate(promotion_client):
    client = promotion_client
    rule = {
        "type": "required_field",
        "present_terms": ["signature was present"],
        "missing_terms": ["signature was absent"],
    }
    create_exercise(client, objectives=[{**OBJECTIVES[0], "evaluation_rule": rule}])
    present = "The fictional controller said the signature was present."
    absent = "The fictional evaluator said the signature was absent."
    add_transcript(client, present, absent)
    configure_provider(entry((1, present)))
    url = accept(client)

    result = promote(
        client,
        url,
        title="Fictional signature report",
        observation=present,
        interpretation="One source reports the signature present.",
    )
    assert result.status_code == 409, result.text
    assert result.json()["detail"]["code"] == "CANDIDATE_PROMOTION_INELIGIBLE"
    assert_no_promotions()


@pytest.mark.parametrize(
    "opponent", ["promotion", "shared_evidence", "candidate_review", "evidence", "analysis"]
)
def test_serialization_under_exercise_lock(promotion_client, monkeypatch, opponent):
    client = promotion_client
    if opponent == "analysis":
        create_exercise(client, objectives=[{**OBJECTIVES[0], "evaluation_rule": RULE}])
        add_transcript(client, WORDING)
        configure_provider(entry((1, WORDING)))
    else:
        prepare(client)
    url = accept(client)
    competing_url = accept(client, "shared-evidence") if opponent == "shared_evidence" else url
    grant(client, "test-reviewer")
    reviewer = TestClient(main.app)
    login(reviewer, "test-reviewer")
    held = threading.Event()
    release = threading.Event()
    competing = threading.Event()
    authorize = ai_candidates._exercise_for_user

    def signal_authorization(*args, **kwargs):
        if kwargs.get("lock"):
            competing.set()
        return authorize(*args, **kwargs)

    def holding(function):
        def call(*args, **kwargs):
            held.set()
            assert release.wait(5)
            return function(*args, **kwargs)

        return call

    def promotion_check(*args, **kwargs):
        if not held.is_set():
            return holding(check_duplicate)(*args, **kwargs)
        return check_duplicate(*args, **kwargs)

    if opponent == "evidence":
        monkeypatch.setattr(
            main, "invalidate_changed_candidates", holding(main.invalidate_changed_candidates)
        )
        first_op = partial(add_transcript, client, "New fictional evidence for the exercise.")
    elif opponent == "analysis":
        monkeypatch.setattr(main, "analyze_exercise", holding(main.analyze_exercise))
        first_op = partial(client.post, f"{EXERCISE}/analyze")
    else:
        check_duplicate = ai_candidates._check_duplicate_finding
        monkeypatch.setattr(ai_candidates, "_check_duplicate_finding", promotion_check)
        first_op = partial(promote, client, url)
    second_op = (
        (lambda: review(reviewer, url, "rejected", version=2))
        if opponent == "candidate_review"
        else (lambda: promote(reviewer, competing_url, key="other-actor-and-key"))
    )
    with ThreadPoolExecutor(max_workers=2) as pool:
        first = pool.submit(first_op)
        try:
            assert held.wait(5)
            monkeypatch.setattr(ai_candidates, "_exercise_for_user", signal_authorization)
            second = pool.submit(second_op)
            assert competing.wait(5)
        finally:
            release.set()
        first_result, second_result = first.result(8), second.result(8)
    status = second_result.status_code
    detail = client.get(EXERCISE).json()
    if opponent == "evidence":
        assert status == 412
        assert_no_promotions()
    elif opponent == "analysis":
        assert first_result.status_code == 200 and status == 409
        assert second_result.json()["detail"]["code"] == "FINDING_DUPLICATE"
        assert len(detail["findings"]) == 1 and detail["findings"][0]["source_candidate_id"] is None
    else:
        assert first_result.status_code == 201
        if opponent == "shared_evidence":
            assert status == 409 and second_result.json()["detail"]["code"] == "FINDING_DUPLICATE"
        else:
            assert status == 412
        assert len(detail["findings"]) == 1 and detail["findings"][0]["status"] == "proposed"
        assert detail["actions"] == []


def test_populated_upgrade_preserves_history_and_enforces_same_exercise():
    with disposable_database() as engine:
        config = database._alembic_config()
        with engine.begin() as connection:
            config.attributes["connection"] = connection
            command.upgrade(config, "c2a4e93b1f70")
        with Session(engine) as db, db.begin():
            for identifier in ["FICTIONAL-A", "FICTIONAL-B"]:
                db.add(
                    Exercise(
                        id=identifier,
                        organization_id="fictional-org",
                        title="Fictional fixture",
                        scenario="Fictional fixture",
                        exercise_date="2026-11-20",
                        duration_minutes=20,
                        objectives_json="[]",
                        criteria_json="[]",
                        evaluator_roles_json="[]",
                        participants_json="[]",
                        milestones_json="[]",
                    )
                )
            db.flush()
            db.add(
                AiCandidate(
                    id="candidate",
                    exercise_id="FICTIONAL-A",
                    organization_id="fictional-org",
                    issuance_id="issued",
                    snapshot_json="{}",
                )
            )
            for identifier, scope in [("local", "FICTIONAL-A"), ("foreign", "FICTIONAL-B")]:
                db.add(
                    Finding(
                        id=identifier,
                        exercise_id=scope,
                        code=identifier,
                        title="Fictional finding",
                        category="strength",
                        observation="Fictional observation",
                        interpretation="Fictional interpretation",
                        evidence_ids_json="[]",
                    )
                )
            db.flush()
            for version, operation in enumerate(["save", "review"], start=1):
                db.add(
                    AiCandidateRequest(
                        exercise_id="FICTIONAL-A",
                        organization_id="fictional-org",
                        actor_user_id="fixture",
                        operation=operation,
                        key=operation,
                        request_hash="fixture",
                        candidate_id="candidate",
                        applied_version=version,
                    )
                )
                db.add(
                    AuditEvent(
                        id=operation,
                        exercise_id="FICTIONAL-A",
                        object_id="candidate",
                        actor="fixture",
                        action=f"ai_candidate_{operation}",
                        candidate_version=version,
                    )
                )
        database.migrate_database(engine)
        database.init_db(engine)
        with Session(engine) as db:
            assert db.get(AiCandidate, "candidate").snapshot_json == "{}"
            assert sorted(db.scalars(select(AiCandidateRequest.operation)).all()) == [
                "review",
                "save",
            ]
            assert len(db.scalars(select(Finding)).all()) == 2
            assert len(db.scalars(select(AuditEvent)).all()) == 2
            assert not db.scalars(select(AiCandidatePromotion)).all()
        link = {
            "exercise_id": "FICTIONAL-A",
            "organization_id": "fictional-org",
            "candidate_id": "candidate",
        }
        with pytest.raises(IntegrityError), Session(engine) as db, db.begin():
            db.add(AiCandidatePromotion(**link, finding_id="foreign"))
        with Session(engine) as db, db.begin():
            db.add(AiCandidatePromotion(**link, finding_id="local"))
        with pytest.raises(IntegrityError), Session(engine) as db, db.begin():
            db.delete(db.get(Finding, "local"))
        with pytest.raises(IntegrityError), Session(engine) as db, db.begin():
            db.add(AiCandidatePromotion(**link, finding_id="local"))
