from __future__ import annotations

import json
import os
import uuid

from app.db import SessionLocal
from app.main import app
from app.models import ExerciseGrant
from fastapi.testclient import TestClient

PASSWORD = "test-only-password-for-suite"


def _login(client: TestClient, username: str, *, add_csrf: bool = True) -> dict:
    response = client.post("/api/auth/login", json={"username": username, "password": PASSWORD})
    assert response.status_code == 200, response.text
    if add_csrf:
        client.headers.update({"X-CSRF-Token": response.json()["csrf_token"]})
    return response.json()


def test_anonymous_requests_cannot_access_exercise_data_or_mutations(client):
    with TestClient(app) as anonymous:
        assert anonymous.get("/api/health").status_code == 200
        assert anonymous.get("/api/capabilities").status_code == 200
        assert anonymous.get("/api/exercises").status_code == 401
        assert anonymous.post("/api/exercises", json={}).status_code == 401


def test_missing_source_download_returns_not_found(client):
    missing = client.get("/api/sources/source-that-does-not-exist/download")

    assert missing.status_code == 404


def test_login_sets_http_only_named_user_session_and_requires_csrf(client):
    with TestClient(app) as user:
        login = _login(user, "test-viewer", add_csrf=False)
        set_cookie = user.cookies.get("drillloop_session")

        assert login["identity"] == {
            "id": "test-viewer",
            "username": "test-viewer",
            "name": "Fixture Viewer",
            "role": "viewer",
            "organization_id": "test-organization",
        }
        assert set_cookie
        session_response = user.get("/api/auth/session")
        assert session_response.status_code == 200
        assert session_response.json()["csrf_token"] == login["csrf_token"]
        blocked = user.post(
            "/api/exercises",
            json={
                "id": "CSRF-BLOCK-01",
                "title": "CSRF blocked write",
                "scenario": "A request without a session CSRF token.",
                "exercise_date": "2026-11-03",
                "duration_minutes": 30,
            },
        )
        assert blocked.status_code == 403
        assert blocked.json()["detail"]["code"] == "CSRF_TOKEN_REQUIRED"


def test_role_and_organization_grants_limit_read_write_and_review(client):
    exercise_id = "AUTH-SCOPE-01"
    created = client.post(
        "/api/exercises",
        json={
            "id": exercise_id,
            "title": "Authorization boundary exercise",
            "scenario": "A fictional exercise for access boundary checks.",
            "exercise_date": "2026-11-03",
            "duration_minutes": 30,
            "objectives": [{"id": "OBJ-01", "text": "Test protected access."}],
        },
    )
    assert created.status_code == 201, created.text
    upload = client.post(
        f"/api/exercises/{exercise_id}/evidence",
        files={
            "files": ("source.txt", b"[14:00] A source record for the access test.", "text/plain")
        },
    )
    assert upload.status_code == 201, upload.text
    detail = client.get(f"/api/exercises/{exercise_id}").json()
    source_id = detail["sources"][0]["id"]

    with SessionLocal() as db:
        db.add(
            ExerciseGrant(
                id=str(uuid.uuid4()),
                exercise_id=exercise_id,
                user_id="test-viewer",
                organization_id="test-organization",
                access_role="viewer",
            )
        )
        db.add(
            ExerciseGrant(
                id=str(uuid.uuid4()),
                exercise_id=exercise_id,
                user_id="test-reviewer",
                organization_id="test-organization",
                access_role="reviewer",
            )
        )
        db.commit()

    with TestClient(app) as viewer:
        _login(viewer, "test-viewer")
        assert viewer.get(f"/api/exercises/{exercise_id}").status_code == 200
        assert viewer.get(f"/api/sources/{source_id}/download").status_code == 200
        assert viewer.get(f"/api/exercises/{exercise_id}/report.pdf").status_code == 200
        assert viewer.post(f"/api/exercises/{exercise_id}/analyze").status_code == 403
        assert (
            viewer.post(
                f"/api/exercises/{exercise_id}/evidence",
                files={"files": ("new.txt", b"New source.", "text/plain")},
            ).status_code
            == 403
        )

    with TestClient(app) as outsider:
        _login(outsider, "other-admin")
        assert outsider.get(f"/api/exercises/{exercise_id}").status_code == 404
        assert outsider.post(f"/api/exercises/{exercise_id}/analyze").status_code == 404
        assert outsider.get(f"/api/exercises/{exercise_id}/report.pdf").status_code == 404
        assert outsider.get(f"/api/sources/{source_id}/download").status_code == 404


def test_reviewer_role_can_review_but_cannot_create(client):
    with TestClient(app) as reviewer:
        _login(reviewer, "test-reviewer")
        created = reviewer.post(
            "/api/exercises",
            json={
                "id": "ROLE-DENY-01",
                "title": "Reviewer cannot create",
                "scenario": "This create request should be denied by role policy.",
                "exercise_date": "2026-11-03",
                "duration_minutes": 30,
            },
        )
        assert created.status_code == 403


def test_review_attribution_comes_from_named_identity_and_reviewer_is_read_only(client):
    seeded = client.post("/api/demo/seed")
    assert seeded.status_code == 200, seeded.text
    detail = client.get("/api/exercises/HOSP-PO-2026-01").json()
    finding = next(item for item in detail["findings"] if item["status"] == "proposed")
    action = next(item for item in detail["actions"])
    granted = client.post(
        "/api/exercises/HOSP-PO-2026-01/access",
        json={"user_id": "test-reviewer"},
    )
    assert granted.status_code == 201, granted.text
    assert granted.json()["role"] == "reviewer"
    assert any(
        person["user_id"] == "test-reviewer"
        for person in client.get("/api/exercises/HOSP-PO-2026-01/access").json()
    )

    with TestClient(app) as reviewer:
        _login(reviewer, "test-reviewer")
        decision = reviewer.post(
            f"/api/findings/{finding['id']}/review",
            json={"decision": "approved", "reviewer": "Forged Caller", "note": "Checked"},
        )
        assert decision.status_code == 200, decision.text
        assert decision.json()["reviewer"] == "Fixture Reviewer"
        assert (
            reviewer.put(
                f"/api/actions/{action['id']}",
                json={
                    "owner": "Caller supplied",
                    "priority": "high",
                    "due_date": "2026-11-15",
                    "acceptance_criteria": "The action is verified by a documented test record.",
                },
            ).status_code
            == 403
        )
        assert reviewer.post("/api/exercises/HOSP-PO-2026-01/analyze").status_code == 403


def test_exercise_access_grants_are_scoped_and_revocable(client):
    created = client.post(
        "/api/exercises",
        json={
            "id": "GRANT-LIFECYCLE-01",
            "title": "Exercise grant lifecycle",
            "scenario": "Verify adding and revoking a configured reviewer safely.",
            "exercise_date": "2026-11-03",
            "duration_minutes": 30,
        },
    )
    assert created.status_code == 201, created.text
    wrong_org = client.post(
        "/api/exercises/GRANT-LIFECYCLE-01/access",
        json={"user_id": "other-organization-admin"},
    )
    assert wrong_org.status_code == 404

    grant = client.post(
        "/api/exercises/GRANT-LIFECYCLE-01/access",
        json={"user_id": "test-viewer"},
    )
    assert grant.status_code == 201
    with TestClient(app) as viewer:
        _login(viewer, "test-viewer")
        assert viewer.get("/api/exercises/GRANT-LIFECYCLE-01").status_code == 200

    self_revoke = client.delete("/api/exercises/GRANT-LIFECYCLE-01/access/test-admin")
    assert self_revoke.status_code == 409
    revoked = client.delete("/api/exercises/GRANT-LIFECYCLE-01/access/test-viewer")
    assert revoked.status_code == 200
    with TestClient(app) as viewer:
        _login(viewer, "test-viewer")
        assert viewer.get("/api/exercises/GRANT-LIFECYCLE-01").status_code == 404


def test_auth_configuration_missing_fails_closed(client, monkeypatch):
    monkeypatch.setenv("DRILLLOOP_USERS_JSON", "[]")
    monkeypatch.setenv("DRILLLOOP_SESSION_SECRET", "")
    response = client.get("/api/exercises")
    assert response.status_code == 503
    assert response.json()["detail"]["code"] == "AUTH_NOT_CONFIGURED"


def test_configured_user_directory_is_same_organization_and_omits_credentials(client):
    response = client.get("/api/configured-users")

    assert response.status_code == 200
    assert {user["user_id"] for user in response.json()} == {
        "test-admin",
        "test-reviewer",
        "test-evaluator",
        "test-viewer",
    }
    assert all("password_hash" not in user for user in response.json())


def test_removing_configured_user_deactivates_existing_session(client, monkeypatch):
    with TestClient(app) as viewer:
        _login(viewer, "test-viewer")
        assert viewer.get("/api/auth/session").status_code == 200
        users = json.loads(os.environ["DRILLLOOP_USERS_JSON"])
        monkeypatch.setenv(
            "DRILLLOOP_USERS_JSON",
            json.dumps([user for user in users if user["id"] != "test-viewer"]),
        )
        response = viewer.get("/api/auth/session")

    assert response.status_code == 401
    assert response.json()["detail"]["code"] == "AUTHENTICATION_REQUIRED"
