from __future__ import annotations

import json
import os
from concurrent.futures import ThreadPoolExecutor, TimeoutError
from threading import Event

import pytest
from app import main
from app.db import SessionLocal
from app.models import AuditEvent, CorrectiveAction, Exercise, Finding, Observation, Source
from fastapi.testclient import TestClient
from sqlalchemy import insert, select

EXERCISE = "/api/exercises/HOSP-PO-2026-01"
NOTE = "Reviewed the fictional exercise record."


def sign_in(client: TestClient, username: str) -> None:
    login = client.post(
        "/api/auth/login",
        json={"username": username, "password": "test-only-password-for-suite"},
    )
    assert login.status_code == 200, login.text
    client.headers["X-CSRF-Token"] = login.json()["csrf_token"]


@pytest.fixture
def finding_review(client):
    seeded = client.post("/api/demo/seed")
    assert seeded.status_code == 200, seeded.text
    detail = client.get(EXERCISE).json()
    finding = next(row for row in detail["findings"] if row["code"] == "POWER_RESTORATION_DELAY")
    action = next(row for row in detail["actions"] if row["finding_id"] == finding["id"])
    update = client.put(
        f"/api/actions/{action['id']}",
        json={
            "owner": "Fictional Facilities",
            "due_date": "2026-11-15",
            "acceptance_criteria": "Record a fictional restoration retest.",
        },
    )
    assert update.status_code == 200, update.text
    grant = client.post(f"{EXERCISE}/access", json={"user_id": "test-reviewer"})
    assert grant.status_code == 201, grant.text
    with TestClient(main.app) as reviewer:
        sign_in(reviewer, "test-reviewer")
        yield reviewer, finding, action


def review(client, finding, decision="approved", note=NOTE):
    return client.post(
        f"/api/findings/{finding['id']}/review", json={"decision": decision, "note": note}
    )


def snapshot(finding, action):
    with SessionLocal() as db:
        finding_row = (
            db.execute(select(Finding.__table__).where(Finding.id == finding["id"]))
            .mappings()
            .one()
        )
        action_row = (
            db.execute(
                select(CorrectiveAction.__table__).where(CorrectiveAction.id == action["id"])
            )
            .mappings()
            .one()
        )
        audit_rows = (
            db.execute(
                select(AuditEvent.__table__)
                .where(AuditEvent.exercise_id == finding_row["exercise_id"])
                .order_by(AuditEvent.id)
            )
            .mappings()
            .all()
        )
        return finding_row, action_row, audit_rows


def assert_review_denied(client, finding, action, before):
    assert before[0]["status"] == "proposed"
    result = client.post(f"/api/actions/{action['id']}/review", json={"decision": "approved"})
    assert result.status_code == 409, result.text
    assert result.json()["detail"]["code"] == "FINDING_NOT_APPROVED"
    assert snapshot(finding, action) == before


@pytest.mark.parametrize(
    "invalid_evidence",
    [
        pytest.param("[]", id="empty"),
        pytest.param('["missing"]', id="dangling"),
        pytest.param("not JSON", id="malformed-json"),
        pytest.param('{"id": "first"}', id="not-a-list"),
        pytest.param('[["first"]]', id="malformed-id"),
        pytest.param('["first", 1]', id="mixed-invalid-type"),
        pytest.param('["first", "missing"]', id="mixed-dangling"),
        pytest.param('["first", "first"]', id="duplicate"),
        pytest.param('["first", "  "]', id="blank"),
        pytest.param(json.dumps(["first", "x" * 37]), id="oversize"),
        pytest.param(r'["first", "\u0000"]', id="embedded-nul"),
        pytest.param(r'["first", "\ud800"]', id="unpaired-surrogate"),
    ],
)
def test_approval_requires_evidence(client, finding_review, invalid_evidence):
    reviewer, finding, action = finding_review
    with SessionLocal.begin() as db:
        db.get_one(Finding, finding["id"]).evidence_ids_json = invalid_evidence.replace(
            '"first"', json.dumps(finding["evidence_ids"][0])
        )
    before = snapshot(finding, action)

    response = review(reviewer, finding)

    assert response.status_code == 422, response.text
    assert response.json()["detail"]["code"] == "FINDING_EVIDENCE_REQUIRED"
    assert_review_denied(client, finding, action, before)


@pytest.mark.parametrize(
    "change",
    [
        "foreign-observation",
        "foreign-source",
        "deleted",
        "unavailable",
        "scan-rejected",
        "no-locator",
    ],
)
def test_approval_requires_current_scoped_sources(client, finding_review, change):
    reviewer, finding, action = finding_review
    if change in {"foreign-observation", "foreign-source"}:
        created = client.post(
            "/api/exercises",
            json={
                "id": "FICTIONAL-OTHER",
                "title": "Fictional second exercise",
                "scenario": "Separate exercise with independent evidence.",
                "exercise_date": "2026-10-16",
                "duration_minutes": 30,
            },
        )
        assert created.status_code == 201, created.text
    with SessionLocal.begin() as db:
        observation = db.get_one(Observation, finding["evidence_ids"][0])
        source = db.get_one(Source, observation.source_id)
        if change == "foreign-observation":
            observation.exercise_id = "FICTIONAL-OTHER"
            # Keep its source in scope to check the observation predicate independently.
        elif change == "foreign-source":
            source.exercise_id = "FICTIONAL-OTHER"
        elif change == "deleted":
            db.delete(observation)
        elif change == "unavailable":
            source.source_bytes = None
            source.content_text = ""
        elif change == "scan-rejected":
            source.scan_status = "rejected"
        elif change == "no-locator":
            observation.source_locator = " \t"
    before = snapshot(finding, action)

    response = review(reviewer, finding)

    assert response.status_code == 422, response.text
    assert response.json()["detail"]["code"] == "FINDING_EVIDENCE_REQUIRED"
    assert_review_denied(client, finding, action, before)


def test_approval_checks_citations_after_the_first_batch(client, finding_review):
    reviewer, finding, action = finding_review
    with SessionLocal.begin() as db:
        first = db.get_one(Observation, finding["evidence_ids"][0])
        extra_ids = [f"fictional-citation-{index}" for index in range(500)]
        db.execute(
            insert(Observation),
            [
                {
                    "id": observation_id,
                    "exercise_id": first.exercise_id,
                    "source_id": first.source_id,
                    "source_locator": "row 2",
                    "text": "Fictional batch test record.",
                }
                for observation_id in extra_ids
            ],
        )
        citation_ids = [*finding["evidence_ids"], *extra_ids]
        db.get_one(Finding, finding["id"]).evidence_ids_json = json.dumps(
            [*citation_ids, "missing"]
        )
    before = snapshot(finding, action)

    denied = review(reviewer, finding)

    assert denied.status_code == 422
    assert denied.json()["detail"]["code"] == "FINDING_EVIDENCE_REQUIRED"
    assert_review_denied(client, finding, action, before)
    with SessionLocal.begin() as db:
        db.get_one(Finding, finding["id"]).evidence_ids_json = json.dumps(citation_ids)
    assert review(reviewer, finding).status_code == 200
    assert json.loads(snapshot(finding, action)[0]["evidence_ids_json"]) == citation_ids


@pytest.mark.parametrize("legacy", [False, True], ids=["seeded", "retained-source-text"])
def test_approval_preserves_citations_human_review_and_action_prerequisite(
    client, finding_review, legacy
):
    reviewer, finding, action = finding_review
    if legacy:
        with SessionLocal.begin() as db:
            observation = db.get_one(Observation, finding["evidence_ids"][0])
            source = db.get_one(Source, observation.source_id)
            assert source.content_text.strip()
            source.source_bytes = None
    before = snapshot(finding, action)
    assert_review_denied(client, finding, action, before)

    response = review(reviewer, finding)

    assert response.status_code == 200, response.text
    assert response.json() == {
        "id": finding["id"],
        "status": "approved",
        "reviewer": "Fixture Reviewer",
    }
    detail = client.get(EXERCISE).json()
    approved = next(row for row in detail["findings"] if row["id"] == finding["id"])
    assert approved["evidence_ids"] == finding["evidence_ids"]
    assert approved["supporting_evidence"] == finding["supporting_evidence"]
    finding_row, action_row, audit = snapshot(finding, action)
    assert finding_row["review_note"] == NOTE
    assert finding_row["evidence_ids_json"] == before[0]["evidence_ids_json"]
    assert action_row == before[1]
    (event,) = [row for row in audit if row["object_id"] == finding["id"]]
    assert (event["action"], event["actor"]) == ("finding_approved", "Fixture Reviewer")
    assert json.loads(event["details_json"]) == {"note": NOTE}
    assert (
        client.post(
            f"/api/actions/{action['id']}/review", json={"decision": "approved"}
        ).status_code
        == 200
    )


def test_rejection_preserves_human_decision_without_citations(client, finding_review):
    reviewer, finding, action = finding_review
    with SessionLocal.begin() as db:
        db.get_one(Finding, finding["id"]).evidence_ids_json = "[]"

    rejected = review(reviewer, finding, "rejected")

    assert rejected.status_code == 200, rejected.text
    assert rejected.json()["reviewer"] == "Fixture Reviewer"
    before = snapshot(finding, action)
    assert before[0]["status"] == "rejected"
    assert before[0]["review_note"] == NOTE
    (event,) = [row for row in before[2] if row["object_id"] == finding["id"]]
    assert (event["action"], event["actor"]) == ("finding_rejected", "Fixture Reviewer")
    assert json.loads(event["details_json"]) == {"note": NOTE}
    assert review(reviewer, finding).status_code == 409
    blocked = client.post(f"/api/actions/{action['id']}/review", json={"decision": "approved"})
    assert blocked.status_code == 409
    assert blocked.json()["detail"]["code"] == "FINDING_NOT_APPROVED"
    assert snapshot(finding, action) == before


@pytest.mark.parametrize(
    ("username", "status"),
    [(None, 401), ("test-viewer", 403), ("test-reviewer", 404), ("other-admin", 404)],
    ids=["anonymous", "viewer-with-grant", "revoked-reviewer", "other-organization-reviewer"],
)
def test_finding_approval_requires_live_review_authority(
    client, finding_review, monkeypatch, username, status
):
    reviewer, finding, action = finding_review
    if username == "test-viewer":
        grant = client.post(f"{EXERCISE}/access", json={"user_id": username})
        assert grant.status_code == 201
    elif username == "test-reviewer":
        assert client.delete(f"{EXERCISE}/access/{username}").status_code == 200
    elif username == "other-admin":
        users = json.loads(os.environ["DRILLLOOP_USERS_JSON"])
        next(user for user in users if user["username"] == username)["role"] = "reviewer"
        monkeypatch.setenv("DRILLLOOP_USERS_JSON", json.dumps(users))
    before = snapshot(finding, action)

    with TestClient(main.app) as caller:
        if username is not None and username != "test-reviewer":
            sign_in(caller, username)
        result = review(reviewer if username == "test-reviewer" else caller, finding)

    assert result.status_code == status, result.text
    assert_review_denied(client, finding, action, before)


def test_competing_review_decisions_commit_only_one_audit_event(
    client, finding_review, monkeypatch
):
    reviewer, finding, action = finding_review
    approval_checked = Event()
    release_approval = Event()
    rejection_started = Event()
    original_support = main._finding_has_source_support
    original_write = main._finding_for_write

    def pause_approval(db, row):
        supported = original_support(db, row)
        approval_checked.set()
        assert release_approval.wait(timeout=5)
        return supported

    def observe_write(db, finding_id, identity, roles):
        if identity.name == "Fixture Administrator":
            rejection_started.set()
        return original_write(db, finding_id, identity, roles)

    monkeypatch.setattr(main, "_finding_has_source_support", pause_approval)
    monkeypatch.setattr(main, "_finding_for_write", observe_write)
    before = snapshot(finding, action)
    with ThreadPoolExecutor(max_workers=2) as pool:
        approval = pool.submit(review, reviewer, finding)
        try:
            assert approval_checked.wait(timeout=3)
            rejection = pool.submit(review, client, finding, "rejected", "Competing decision.")
            assert rejection_started.wait(timeout=3)
            with pytest.raises(TimeoutError):
                rejection.result(timeout=0.15)
        finally:
            release_approval.set()
        assert approval.result(timeout=5).status_code == 200
        assert rejection.result(timeout=5).status_code == 409

    finding_row, action_row, audit = snapshot(finding, action)
    assert (finding_row["status"], finding_row["reviewer"], finding_row["review_note"]) == (
        "approved",
        "Fixture Reviewer",
        NOTE,
    )
    assert action_row == before[1]
    (event,) = [row for row in audit if row not in before[2]]
    assert (event["action"], event["actor"], event["object_id"]) == (
        "finding_approved",
        "Fixture Reviewer",
        finding["id"],
    )


def test_approval_rechecks_evidence_after_in_progress_exercise_write(
    client, finding_review, monkeypatch
):
    reviewer, finding, action = finding_review
    review_started = Event()
    original_write = main._finding_for_write

    def observe_write(*args):
        review_started.set()
        return original_write(*args)

    monkeypatch.setattr(main, "_finding_for_write", observe_write)
    before = snapshot(finding, action)
    with ThreadPoolExecutor(max_workers=1) as pool:
        with SessionLocal.begin() as db:
            main.begin_exercise_write(db)
            exercise_id = before[0]["exercise_id"]
            db.scalar(select(Exercise).where(Exercise.id == exercise_id).with_for_update())
            db.delete(db.get_one(Observation, finding["evidence_ids"][0]))
            db.flush()
            approval = pool.submit(review, reviewer, finding)
            assert review_started.wait(timeout=3)
            with pytest.raises(TimeoutError):
                approval.result(timeout=0.15)
        result = approval.result(timeout=5)

    assert result.status_code == 422
    assert result.json()["detail"]["code"] == "FINDING_EVIDENCE_REQUIRED"
    assert_review_denied(client, finding, action, before)
