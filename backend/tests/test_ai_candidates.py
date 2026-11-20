"""Backend candidate contract checks with fictional evidence and a fake provider."""

from __future__ import annotations

import json
import os
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from unittest.mock import patch

import pytest
from app import ai_candidates, candidate_evidence
from app.ai_evaluation import AiService, AiSettings, ProviderReply
from app.db import SessionLocal
from app.main import app
from app.models import AiCandidate, AuditEvent, ExerciseGrant, Observation, Source
from fastapi.testclient import TestClient
from sqlalchemy import delete, func, select, text, update
from sqlalchemy.exc import IntegrityError, OperationalError

ID = "FICTIONAL-CANDIDATE"
EXERCISE = f"/api/exercises/{ID}"
CANDIDATES = f"{EXERCISE}/ai-candidates"
WORDING = "The fictional dispatcher logged the backup panel handoff."
OBJECTIVES = [{"id": "OBJ", "text": "Document the fictional panel handoff."}]


class FakeProvider:
    def __init__(self, suggestions):
        self.suggestions = suggestions
        self.calls = 0

    async def generate(self, _system, _evidence, _schema):
        self.calls += 1
        return ProviderReply(json.dumps({"suggestions": self.suggestions}))


def configure_provider(*entries):
    provider = FakeProvider(entries)
    app.state.ai_evaluation = AiService(
        AiSettings("http://127.0.0.1:11434", "fictional-model:test", 5, 12_000, 1024, 1), provider
    )
    return provider


def create_exercise(client, exercise_id=ID, objectives=OBJECTIVES):
    response = client.post(
        "/api/exercises",
        json={
            "id": exercise_id,
            "title": "Fictional panel handoff",
            "scenario": "A fictional panel exercise for advisory candidate validation.",
            "exercise_date": "2026-11-20",
            "duration_minutes": 20,
            "objectives": objectives,
            "organization_id": "untrusted-payload",
        },
    )
    assert response.status_code == 201, response.text


def add_transcript(client, *observations, exercise=EXERCISE):
    response = client.post(
        f"{exercise}/transcripts",
        json={
            "transcript": "Fictional transcript fixture",
            "source_name": "fictional-transcript.json",
            "segments": [
                {"text": wording, "start": index * 4, "end": index * 4 + 3, "confidence": 0.7}
                for index, wording in enumerate(observations, 1)
            ],
        },
    )
    assert response.status_code == 201, response.text
    return response.json()["source_id"]


def upload_text(client, filename, *lines):
    response = client.post(
        f"{EXERCISE}/evidence",
        files={
            "files": (filename, "\n".join(lines).encode(), "text/plain"),
        },
    )
    assert response.status_code == 201, response.text


def entry(*citations, kind="relevant_observation", objective="OBJ", unknowns=()):
    return {
        "objective_id": objective,
        "kind": kind,
        "citations": [{"record": record, "excerpt": excerpt} for record, excerpt in citations],
        "missing_information": list(unknowns),
    }


def generate(client):
    response = client.post(f"{EXERCISE}/ai-suggestions")
    assert response.status_code == 200, response.text
    assert response.headers["Cache-Control"] == "no-store"
    return response.json()["suggestions"]


def prepare(client):
    create_exercise(client)
    add_transcript(client, WORDING)
    return configure_provider(entry((1, WORDING)))


def save(client, token, key="save-1"):
    return client.post(CANDIDATES, json={"save_token": token}, headers={"Idempotency-Key": key})


def persisted(client, key="save-1"):
    token = generate(client)[0]["save_token"]
    response = save(client, token, key)
    assert response.status_code == 201, response.text
    return token, response.json()["id"]


def review(client, url, decision, key="review-1", version=1, note=None):
    return client.post(
        f"{url}/review",
        json={"decision": decision, "note": note},
        headers={"Idempotency-Key": key, "If-Match": f'"{version}"'},
    )


def login(client, username, *, csrf=True):
    result = client.post(
        "/api/auth/login",
        json={
            "username": username,
            "password": "test-only-password-for-suite",
        },
    )
    assert result.status_code == 200, result.text
    if csrf:
        client.headers["X-CSRF-Token"] = result.json()["csrf_token"]


def grant(client, user):
    response = client.post(f"{EXERCISE}/access", json={"user_id": user})
    assert response.status_code == 201, response.text


def test_save_provenance_restart_and_deterministic_state(client):
    objectives = [
        {
            **OBJECTIVES[0],
            "evaluation_rule": {
                "type": "event_presence",
                "terms": ["backup panel handoff"],
                "finding_code": "HANDOFF",
            },
        }
    ]
    create_exercise(client, objectives=objectives)
    source_id = add_transcript(client, WORDING)
    assert client.post(f"{EXERCISE}/analyze").status_code == 200
    before = client.get(EXERCISE).json()
    assert len(before["findings"]) == 1
    provider = configure_provider(entry((1, "dispatcher logged the backup panel handoff")))
    issued = generate(client)[0]
    assert issued["evidence"][0]["text"] == WORDING
    assert issued["status"] == "proposed"
    assert client.get(CANDIDATES).json() == {"candidates": [], "next_after": None}
    response = client.post(
        CANDIDATES,
        json={"save_token": issued["save_token"]},
        headers={"Idempotency-Key": "save-1"},
    )
    assert response.status_code == 201, response.text
    saved = response.json()
    url = f"{CANDIDATES}/{saved['id']}"
    detail = client.get(url)
    assert detail.headers["ETag"] == '"1"'
    candidate = detail.json()
    assert candidate["version"] == 1
    assert candidate["review_state"] == "pending_review"
    assert candidate["reviewer_decision"] is None
    assert candidate["freshness"] == "current"
    assert candidate["organization_id"] == "test-organization"
    assert candidate["evidence"][0]["source_id"] == source_id
    assert candidate["evidence"][0]["source_locator"] == "segment 1 · 4.00–7.00s"
    assert candidate["evidence"][0]["recognition_confidence"] == 0.7
    assert candidate["evidence"][0]["event_time_raw"] is None
    assert candidate["provenance"]["provider"] == "ollama"
    assert candidate["provenance"]["model"] == "fictional-model:test"
    assert candidate["provenance"]["model_digest"] is None
    assert candidate["provenance"]["requested_by_user_id"] == "test-admin"
    assert len(candidate["evidence"][0]["source_sha256"]) == 64
    assert len(candidate["evidence"][0]["observation_fingerprint"]) == 64
    assert len(candidate["objective_fingerprint"]) == 64
    (event,) = candidate["history"]
    assert event["operation"] == "ai_candidate_saved"
    assert event["actor_user_id"] == "test-admin"
    assert event["organization_id"] == "test-organization"
    assert event["request_id"] == response.headers["x-request-id"]
    assert event["prior_state"] is None and event["new_state"] == "pending_review"
    assert provider.calls == 1
    assert client.get(EXERCISE).json() == before
    with TestClient(app) as restarted:
        login(restarted, "test-admin")
        assert restarted.get(url).json() == candidate
        assert save(restarted, issued["save_token"]).json() == saved
        assert restarted.get(EXERCISE).json() == before
        assert restarted.post(f"{url}/promote").status_code == 404

    create_exercise(client, "OTHER-FICTIONAL")
    assert (
        client.get(f"/api/exercises/OTHER-FICTIONAL/ai-candidates/{saved['id']}").status_code == 404
    )
    assert (
        client.post(
            "/api/exercises/OTHER-FICTIONAL/ai-candidates",
            json={"save_token": issued["save_token"]},
            headers={"Idempotency-Key": "valid"},
        ).status_code
        == 404
    )


@pytest.mark.parametrize(
    "entries,advisory_count",
    [
        ([entry()], 0),
        ([entry(kind="insufficient_evidence", unknowns=["completion_record"])], 1),
        ([entry((1, "Fictional timestamp made up by the test."))], 0),
        ([entry((2, WORDING))], 0),
        ([entry((1, "dispatcher"))], 0),
        ([entry((1, WORDING), (1, WORDING))], 0),
        ([entry((1, WORDING), objective="FOREIGN")], 0),
        ([entry((1, WORDING)), entry((1, "A fabricated competing citation."))], 1),
    ],
)
def test_unsaveable_model_entries(client, entries, advisory_count):
    create_exercise(client)
    add_transcript(client, WORDING)
    create_exercise(
        client, "OTHER-EVIDENCE", [{"id": "FOREIGN", "text": "Another exercise objective."}]
    )
    add_transcript(client, WORDING, exercise="/api/exercises/OTHER-EVIDENCE")
    configure_provider(*entries)
    suggestions = generate(client)
    assert len(suggestions) == advisory_count
    assert all(suggestion["save_token"] is None for suggestion in suggestions)
    invalid = save(client, "manufactured.reference")
    assert invalid.status_code == 422
    assert invalid.json()["detail"]["code"] == "AI_SAVE_TOKEN_INVALID"
    assert client.get(CANDIDATES).json()["candidates"] == []


def test_competing_suggestions_cannot_omit_any_cited_records(client):
    create_exercise(client)
    observations = [
        f"Fictional observer reported separate panel observation number {i}." for i in range(5)
    ]
    add_transcript(client, *observations)
    configure_provider(
        entry(*enumerate(observations[:4], 1)),
        entry((5, observations[4]), kind="unknown", unknowns=["event_identity"]),
    )
    (suggestion,) = generate(client)
    assert suggestion["kind"] == "unknown"
    assert len(suggestion["evidence"]) == 4
    assert suggestion["save_token"] is None


@pytest.mark.parametrize("suffix,saveable", [(0, True), (1, False)])
def test_quotes_preserve_next_sentence_and_360_boundary(client, suffix, saveable):
    create_exercise(client)
    start = "The fictional observer saw a panel release. A later note says this was a drill prop."
    wording = start.ljust(359 + suffix, ".") + "!"
    add_transcript(client, wording)
    configure_provider(entry((1, "fictional observer saw a panel release")))
    suggestions = generate(client)
    if saveable:
        (candidate,) = suggestions
        response = save(client, candidate["save_token"])
        assert response.status_code == 201, response.text
        assert (
            client.get(f"{CANDIDATES}/{response.json()['id']}").json()["evidence"][0]["text"]
            == wording
        )
    else:
        assert not suggestions


def test_panel_stages_identity_and_missing_documentation_survive_save_and_review(client):
    create_exercise(
        client,
        objectives=[
            {"id": "PANEL-STAGES", "text": "Relate the fictional QC-7 panel response stages."},
            {"id": "PANEL-ID", "text": "Identify which fictional handoff the observer meant."},
            {"id": "PANEL-DOC", "text": "Check the fictional notebook for evidence of handoff."},
        ],
    )
    control = [
        "At QC-7 the operator isolated Panel D for testing.",
        "Panel D was released in exercise run A to the maintenance team.",
        "Panel D was released in exercise run B to the evaluation team.",
    ]
    observer = [
        "I saw Panel D returned to service after testing during QC-7.",
        "I saw Panel D released but did not write down the exercise run or receiving team.",
        "No matching handoff entry was found in the notebook.",
    ]
    upload_text(client, "fictional-control.txt", *control)
    upload_text(client, "fictional-observer.txt", *observer)
    stage = entry(
        (1, control[0]),
        (4, observer[0]),
        kind="different_response_phases",
        objective="PANEL-STAGES",
    )
    configure_provider(
        stage,
        entry(
            (2, control[1]),
            (3, control[2]),
            (5, observer[1]),
            kind="unknown",
            objective="PANEL-ID",
            unknowns=["event_identity"],
        ),
        entry(
            (6, "handoff entry was found in the notebook"),
            kind="insufficient_evidence",
            objective="PANEL-DOC",
            unknowns=["completion_record"],
        ),
    )
    ids = {}
    for suggestion in generate(client):
        code = suggestion["objective_id"]
        result = save(client, suggestion["save_token"], code)
        assert result.status_code == 201, result.text
        ids[code] = f"{CANDIDATES}/{result.json()['id']}"
    stages = client.get(ids["PANEL-STAGES"]).json()
    assert stages["kind"] == "different_response_phases"
    assert [
        (row["source_filename"], row["source_locator"], row["text"]) for row in stages["evidence"]
    ] == [
        ("fictional-control.txt", "line 1", control[0]),
        ("fictional-observer.txt", "line 1", observer[0]),
    ]
    identity = client.get(ids["PANEL-ID"]).json()
    assert identity["kind"] == "unknown"
    assert len(identity["evidence"]) == 3
    assert "Confirmation of which event the wording refers to." in identity["unknowns"]
    documentation = client.get(ids["PANEL-DOC"]).json()
    assert documentation["kind"] == "insufficient_evidence"
    assert documentation["evidence"][0]["text"] == observer[2]
    assert "A record that confirms the expected outcome occurred." in documentation["unknowns"]
    for key, url in ids.items():
        assert review(client, url, "accepted_for_consideration", key=key).status_code == 200

    stage["kind"] = "contradiction"
    configure_provider(stage)
    _, incorrect = persisted(client, "incorrect-relationship")
    wrong = f"{CANDIDATES}/{incorrect}"
    candidate = client.get(wrong).json()
    assert candidate["kind"] == "contradiction"
    assert candidate["assessment"] == "advisory"
    assert candidate["counterevidence"][0]["text"] == observer[0]
    assert review(client, wrong, "rejected", key="reject-relationship").status_code == 200
    assert client.get(EXERCISE).json()["findings"] == []


def test_ocr_snapshot_preserves_page_reported_time_and_uncertainty(client):
    create_exercise(client)
    source_id = add_transcript(client, WORDING)
    with SessionLocal.begin() as db:
        db.execute(
            update(Observation)
            .where(Observation.source_id == source_id)
            .values(
                extraction_method="ocr",
                source_locator="page 3",
                time_confidence="uncertain",
                event_time_raw="14:11",
                event_time_normalized=None,
                recognition_confidence=None,
            )
        )
        db.execute(
            update(Source)
            .where(Source.id == source_id)
            .values(
                provenance_json='{"ocr_engine":"Tesseract","ocr_engine_version":"fixture","ocr_language":"eng"}',
            )
        )
    configure_provider(entry((1, WORDING)))
    _, candidate_id = persisted(client)
    detail = client.get(f"{CANDIDATES}/{candidate_id}").json()
    (citation,) = detail["evidence"]
    assert (citation["ocr_page"], citation["ocr_engine"], citation["source_locator"]) == (
        3,
        "Tesseract",
        "page 3",
    )
    assert citation["event_time_raw"] == "14:11" and citation["time_confidence"] == "uncertain"
    assert citation["recognition_confidence"] is None
    assert (
        "Verify OCR wording and any source times against the original page."
        in detail["uncertainty"]
    )


def test_token_tampering_redaction_disabled_and_key_retries(client, monkeypatch):
    provider = prepare(client)
    token = generate(client)[0]["save_token"]
    tampered = ("A" if token[0] != "A" else "B") + token[1:]
    assert save(client, tampered).status_code == 422
    extra = client.post(CANDIDATES, json={"save_token": token, token: "client payload"})
    assert extra.status_code == 422 and token not in extra.text
    assert save(client, token).status_code == 201
    first = save(client, token).json()
    assert save(client, tampered).status_code == 409

    another = generate(client)[0]["save_token"]
    configure_provider()
    app.state.ai_evaluation = AiService(None)
    assert client.post(f"{EXERCISE}/ai-suggestions").json()["detail"]["code"] == "AI_DISABLED"
    assert save(client, another, "disabled").json()["detail"]["code"] == "AI_DISABLED"
    assert client.get(f"{CANDIDATES}/{first['id']}").json()["freshness"] == "current"
    assert save(client, token).json() == first
    assert save(client, token, "another-key").json() == first
    app.state.ai_evaluation = AiService(
        provider=provider,
        settings=AiSettings(
            "http://127.0.0.1:11434",
            "fictional-model:upgrade",
            5,
            12_000,
            1024,
            1,
        ),
    )
    assert client.get(f"{CANDIDATES}/{first['id']}").json()["freshness"] == "current"
    with monkeypatch.context() as clock:
        clock.setattr(
            candidate_evidence,
            "time",
            type(
                "Clock",
                (),
                {
                    "time": staticmethod(
                        lambda: time.time() + candidate_evidence.TOKEN_TTL_SECONDS + 100
                    ),
                },
            ),
        )
        assert save(client, another, "expired").json()["detail"]["code"] == "AI_SAVE_TOKEN_EXPIRED"
        assert save(client, token).json() == first
    assert provider.calls == 2
    assert save(client, another, "second-run").status_code == 201
    assert len(client.get(CANDIDATES).json()["candidates"]) == 2


def test_scope_grants_roles_csrf_deactivation_and_disabled_review(client, monkeypatch):
    prepare(client)
    token, candidate_id = persisted(client)
    url = f"{CANDIDATES}/{candidate_id}"
    for user in ("test-viewer", "test-reviewer", "test-evaluator"):
        grant(client, user)
    # Simulate a retained contradictory grant. The durable owner still denies it.
    with SessionLocal.begin() as db:
        db.add(
            ExerciseGrant(
                id="foreign-retained-grant",
                exercise_id=ID,
                user_id="other-organization-admin",
                organization_id="other-organization",
                access_role="admin",
            )
        )
    outsider = TestClient(app)
    login(outsider, "other-admin")
    assert outsider.get("/api/exercises").json() == []
    assert outsider.get(CANDIDATES).status_code == 404
    assert outsider.get(url).status_code == 404
    assert save(outsider, token).status_code == 404
    assert review(outsider, url, "rejected").status_code == 404
    assert outsider.post("/api/demo/seed").status_code == 200
    assert client.post("/api/demo/seed").status_code == 404
    anonymous = TestClient(app)
    assert anonymous.get(url).status_code == 401
    assert save(anonymous, token).status_code == 401
    viewer = TestClient(app)
    login(viewer, "test-viewer")
    assert viewer.get(url).status_code == 200
    assert save(viewer, token).status_code == 403
    assert viewer.post(f"{EXERCISE}/ai-suggestions").status_code == 403
    assert review(viewer, url, "rejected").status_code == 403
    evaluator = TestClient(app)
    login(evaluator, "test-evaluator")
    assert save(evaluator, token).status_code == 404  # Same exercise, different issuer.
    assert review(evaluator, url, "rejected").status_code == 403
    reviewer = TestClient(app)
    login(reviewer, "test-reviewer", csrf=False)
    assert review(reviewer, url, "rejected").headers["Cache-Control"] == "no-store"
    assert review(reviewer, url, "rejected").json()["detail"]["code"] == "CSRF_TOKEN_REQUIRED"
    login(reviewer, "test-reviewer")
    assert save(reviewer, token).status_code == 403
    app.state.ai_evaluation = AiService(None)
    decided = review(reviewer, url, "accepted_for_consideration")
    assert decided.status_code == 200, decided.text
    assert reviewer.get(url).json()["latest_decision"]["actor_user_id"] == "test-reviewer"
    assert client.delete(f"{EXERCISE}/access/test-reviewer").status_code == 200
    assert reviewer.get(url).status_code == 404
    assert review(reviewer, url, "accepted_for_consideration").status_code == 404
    users = json.loads(os.environ["DRILLLOOP_USERS_JSON"])
    monkeypatch.setenv(
        "DRILLLOOP_USERS_JSON", json.dumps([u for u in users if u["id"] != "test-viewer"])
    )
    assert viewer.get(url).status_code == 401


def test_concurrent_saves_and_reviews_are_idempotent(client):
    prepare(client)
    token = generate(client)[0]["save_token"]
    with ThreadPoolExecutor(max_workers=4) as executor:
        responses = list(
            executor.map(lambda key: save(client, token, key), ["one", "one", "two", "three"])
        )
    assert [r.status_code for r in responses] == [201] * 4
    assert len({r.json()["id"] for r in responses}) == 1
    url = f"{CANDIDATES}/{responses[0].json()['id']}"
    assert len(client.get(url).json()["history"]) == 1
    decisions = ["accepted_for_consideration", "rejected"]
    with ThreadPoolExecutor(max_workers=2) as executor:
        responses = list(
            executor.map(lambda decision: review(client, url, decision, decision), decisions)
        )
    assert sorted(r.status_code for r in responses) == [200, 412]
    (winner,) = [r.json() for r in responses if r.status_code == 200]
    assert review(client, url, winner["decision"], winner["decision"]).json() == winner
    assert len(client.get(url).json()["history"]) == 2


def test_transition_guards_versions_pagination_and_audit_rollback(client, monkeypatch):
    prepare(client)
    _, first = persisted(client)
    persisted(client, "another-run")
    page = client.get(CANDIDATES, params={"limit": 1}).json()
    second = client.get(CANDIDATES, params={"limit": 1, "after": page["next_after"]}).json()
    assert page["candidates"][0]["id"] != second["candidates"][0]["id"]
    assert second["next_after"] is None
    url = f"{CANDIDATES}/{first}"
    assert (
        client.post(
            f"{url}/review",
            json={"decision": "rejected"},
            headers={
                "Idempotency-Key": "missing-version",
            },
        ).status_code
        == 428
    )
    assert review(client, url, "more_evidence_required", note=" ").status_code == 422
    with monkeypatch.context() as injection:
        audit = ai_candidates._audit

        def broken_audit(db, *args, **kwargs):
            audit(db, *args, **kwargs)
            db.add(
                AuditEvent(
                    id="invalid",
                    exercise_id="missing-exercise",
                    actor="fixture",
                    object_id="fixture",
                    action="fixture",
                    details_json="{}",
                )
            )

        injection.setattr(ai_candidates, "_audit", broken_audit)
        assert review(client, url, "rejected").status_code == 503
        assert save(client, generate(client)[0]["save_token"], "rollback-save").status_code == 503
    assert client.get(url).headers["ETag"] == '"1"'
    assert len(client.get(CANDIDATES).json()["candidates"]) == 2
    assert (
        review(
            client, url, "more_evidence_required", note="Find the original handoff register."
        ).status_code
        == 200
    )
    assert (
        review(
            client, url, "more_evidence_required", key="same-decision", version=2, note="Same"
        ).status_code
        == 409
    )
    assert (
        review(client, url, "accepted_for_consideration", key="accept", version=2).status_code
        == 200
    )
    assert (
        review(
            client,
            url,
            "more_evidence_required",
            key="reopen",
            version=3,
            note="Find the next page.",
        ).status_code
        == 200
    )
    assert review(client, url, "rejected", key="reject", version=4).status_code == 200
    assert (
        review(client, url, "accepted_for_consideration", key="terminal", version=5).status_code
        == 409
    )
    history_page = client.get(url, params={"history_limit": 2}).json()
    assert history_page["reviewer_decision"] == "rejected"
    assert history_page["next_history_after_version"] == 2
    assert [
        event["version"]
        for event in client.get(url, params={"history_after_version": 2}).json()["history"]
    ] == [3, 4, 5]
    assert client.get(EXERCISE).json()["actions"] == []


@pytest.mark.parametrize(
    "change,reason",
    [
        ("bytes_missing", "source_unavailable"),
        ("bytes_modified", "source_unavailable"),
        ("source_deleted", "source_unavailable"),
        ("observation_removed", "citation_invalid"),
        ("ocr_provenance", "citation_invalid"),
        ("different_wording", "citation_invalid"),
        ("other_evidence", "context_changed"),
        ("objectives", "objective_changed"),
        ("validator", "validator_changed"),
    ],
)
def test_staleness_preserves_history_and_commits_before_denial(client, monkeypatch, change, reason):
    prepare(client)
    unused_token = generate(client)[0]["save_token"]
    _, candidate_id = persisted(client)
    url = f"{CANDIDATES}/{candidate_id}"
    assert review(client, url, "accepted_for_consideration").status_code == 200
    prior = client.get(url).json()
    source_id = prior["evidence"][0]["source_id"]
    if change == "other_evidence":
        add_transcript(client, "Fictional new evidence changed the validation context.")
    elif change == "objectives":
        response = client.put(
            f"{EXERCISE}/objectives",
            json={
                "objectives": [
                    {
                        **OBJECTIVES[0],
                        "text": "Confirm which fictional team signed the handoff record.",
                    },
                ]
            },
        )
        assert response.status_code == 200
    elif change == "validator":
        monkeypatch.setattr(candidate_evidence, "VALIDATOR_VERSION", "test-upgrade")
    else:
        with SessionLocal.begin() as db:
            source = db.get(Source, source_id)
            if change == "bytes_missing":
                source.source_bytes = None
            elif change == "bytes_modified":
                source.source_bytes = b"fictional replaced bytes"
            elif change == "ocr_provenance":
                source.provenance_json = '{"ocr_engine_version":"different"}'
            elif change == "different_wording":
                db.execute(
                    update(Observation)
                    .where(Observation.source_id == source.id)
                    .values(text="Changed fictional wording.")
                )
            else:
                db.execute(delete(Observation).where(Observation.source_id == source.id))
                if change == "source_deleted":
                    db.delete(source)

    transition = review(client, url, "rejected", key="changed", version=2)
    assert transition.status_code in (
        {412} if change in {"objectives", "other_evidence"} else {409}
    )
    assert save(client, unused_token, "old-token").status_code == 409
    stale = client.get(url).json()
    assert stale["version"] == 3 and stale["freshness"] == "stale"
    assert reason in stale["stale_reasons"]
    assert stale["reviewer_decision"] == "accepted_for_consideration"
    assert stale["interpretation"] == prior["interpretation"]
    assert stale["evidence"] == prior["evidence"]
    assert stale["history"][-1]["operation"] == "ai_candidate_invalidated"
    assert stale["history"][-1]["actor"] == "system"
    assert review(client, url, "rejected", key="present-version", version=3).status_code == 409
    assert client.get(url).json() == stale


def test_review_and_evidence_mutation_use_same_transaction_lock(client):
    prepare(client)
    _, candidate_id = persisted(client)
    url = f"{CANDIDATES}/{candidate_id}"
    entered = threading.Event()
    finished = threading.Event()
    reviewer_started = threading.Event()
    authorize = ai_candidates._exercise_for_user
    invalidate = ai_candidates.invalidate_changed_candidates

    def hold_evidence_lock(db, exercise):
        entered.set()
        assert finished.wait(timeout=3)
        invalidate(db, exercise)

    def signal_review_lock(*args, **kwargs):
        reviewer_started.set()
        return authorize(*args, **kwargs)

    with (
        patch("app.main.invalidate_changed_candidates", hold_evidence_lock),
        patch("app.ai_candidates._exercise_for_user", signal_review_lock),
        ThreadPoolExecutor(max_workers=2) as pool,
    ):
        writer = pool.submit(add_transcript, client, "Fictional newly recorded opposing evidence.")
        try:
            assert entered.wait(timeout=3)
            reviewer = pool.submit(review, client, url, "accepted_for_consideration")
            assert reviewer_started.wait(timeout=3)
            with pytest.raises(TimeoutError):
                reviewer.result(timeout=0.15)
        finally:
            finished.set()
        writer.result(timeout=5)
        assert reviewer.result(timeout=5).status_code == 412
    assert client.get(url).json()["reviewer_decision"] is None


def test_verification_outage_returns_503_and_history_retries(client, monkeypatch):
    prepare(client)
    _, candidate_id = persisted(client)
    url = f"{CANDIDATES}/{candidate_id}"
    with monkeypatch.context() as injection:

        def outage(*_args, **_kwargs):
            raise OperationalError("fixture unavailable", None, None)

        injection.setattr(ai_candidates, "load_evidence", outage)
        assert client.get(url).status_code == 503
        assert client.get(CANDIDATES).status_code == 503
        assert review(client, url, "rejected").status_code == 503
        with SessionLocal() as db:
            assert db.get(AiCandidate, candidate_id).version == 1
            assert (
                db.scalar(
                    select(func.count())
                    .select_from(AuditEvent)
                    .where(
                        AuditEvent.object_id == candidate_id,
                    )
                )
                == 1
            )
    assert client.get(url).json()["freshness"] == "current"
    with pytest.raises(IntegrityError), SessionLocal.begin() as db:
        db.execute(text("DELETE FROM exercises WHERE id = :id"), {"id": ID})


def test_cors_and_server_owned_audit_correlation(client):
    prepare(client)
    token = generate(client)[0]["save_token"]
    origin = "http://localhost:5173"
    preflight = client.options(
        CANDIDATES,
        headers={
            "Origin": origin,
            "Access-Control-Request-Method": "POST",
            "Access-Control-Request-Headers": "Idempotency-Key, If-Match, X-CSRF-Token",
        },
    )
    assert preflight.status_code == 200
    assert preflight.headers["Access-Control-Allow-Origin"] == origin
    response = client.post(
        CANDIDATES,
        json={"save_token": token},
        headers={
            "Idempotency-Key": "cors-test",
            "X-Request-ID": "client-chosen-id",
        },
    )
    assert response.status_code == 201, response.text
    detail = client.get(f"{CANDIDATES}/{response.json()['id']}", headers={"Origin": origin})
    assert detail.headers["Access-Control-Expose-Headers"] == "ETag"
    assert detail.headers["Cache-Control"] == "no-store"
    assert response.headers["X-Request-ID"] == "client-chosen-id"
    (event,) = detail.json()["history"]
    assert len(event["request_id"]) == 32
    assert event["request_id"] != "client-chosen-id"


def test_candidate_snapshot_and_request_scope_have_database_guards(client):
    prepare(client)
    _, candidate_id = persisted(client)
    create_exercise(client, "OTHER-DB-SCOPE")
    statements = (
        "UPDATE ai_candidates SET snapshot_json='{}' WHERE id=:id",
        "UPDATE ai_candidate_requests SET exercise_id='OTHER-DB-SCOPE' WHERE candidate_id=:id",
    )
    for statement in statements:
        with pytest.raises(IntegrityError), SessionLocal.begin() as db:
            db.execute(text(statement), {"id": candidate_id})
    detail = client.get(f"{CANDIDATES}/{candidate_id}").json()
    assert detail["evidence"][0]["text"] == WORDING
    assert detail["history"][0]["version"] == 1


def test_competing_relationships_preserve_counterevidence(client):
    create_exercise(client)
    account = "The fictional operator reported Panel D released before testing."
    opposing = "The fictional verifier reported Panel D remained isolated through testing."
    background = "The fictional observer lacked the receiving team's name."
    add_transcript(client, account, opposing, background)
    configure_provider(
        entry((1, account), (2, opposing), kind="contradiction"),
        entry((3, background), kind="unknown", unknowns=["event_identity"]),
    )
    _, candidate_id = persisted(client)
    candidate = client.get(f"{CANDIDATES}/{candidate_id}").json()
    assert candidate["kind"] == "unknown"
    assert {cite["text"] for cite in candidate["evidence"]} == {account, background}
    assert [cite["text"] for cite in candidate["counterevidence"]] == [opposing]
