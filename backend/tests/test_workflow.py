from __future__ import annotations

import sys

from app.main import app
from fastapi.testclient import TestClient


def test_demo_pipeline_is_evidence_linked_and_marks_unresolved_time(client):
    seeded = client.post("/api/demo/seed")
    assert seeded.status_code == 200, seeded.text
    assert seeded.json()["analysis"]["candidate_count"] == 5
    detail = client.get("/api/exercises/HOSP-PO-2026-01").json()
    assert {f["code"] for f in detail["findings"]} == {
        "POWER_RESTORATION_DELAY",
        "COMMUNICATION_ACK_DELAY",
        "RESPONSE_TIME_DISCREPANCY",
        "COLD_CHAIN_PROCEDURE_COMPLETED",
        "ACTION_OWNER_MISSING",
    }
    for finding in detail["findings"]:
        assert finding["status"] == "proposed"
        assert finding["supporting_evidence"]
        assert all(
            item["observation_id"] in finding["evidence_ids"]
            for item in finding["supporting_evidence"]
        )
    assert detail["timeline_conflicts"]
    assert any(row["time_confidence"] == "unknown" for row in detail["timeline"])
    assert any(
        row["recognition_confidence"] == 0.58 and row["time_confidence"] == "uncertain"
        for row in detail["timeline"]
    )
    missing_owner = next(action for action in detail["actions"] if action["owner"] is None)
    assert missing_owner["reviewer_decision"] == "pending"


def test_communication_finding_cites_csv_request_and_conflicting_watch_note(client):
    seeded = client.post("/api/demo/seed")
    assert seeded.status_code == 200, seeded.text
    finding = next(
        row
        for row in client.get("/api/exercises/HOSP-PO-2026-01").json()["findings"]
        if row["code"] == "COMMUNICATION_ACK_DELAY"
    )

    references = {
        (item["source_filename"], item["source_locator"]) for item in finding["supporting_evidence"]
    }
    assert ("control_room_log.csv", "row 4 · EL-03") in references
    assert ("control_room_log.csv", "row 5 · EL-04") in references
    assert ("evaluator_notes.txt", "line 9") in references


def test_named_reviewer_controls_finding_and_action_closure(client):
    client.post("/api/demo/seed")
    detail = client.get("/api/exercises/HOSP-PO-2026-01").json()
    finding = next(item for item in detail["findings"] if item["code"] == "POWER_RESTORATION_DELAY")
    action = next(item for item in detail["actions"] if item["finding_id"] == finding["id"])

    with TestClient(app) as anonymous:
        unauthorized = anonymous.post(
            f"/api/findings/{finding['id']}/review", json={"decision": "approved", "note": ""}
        )
        assert unauthorized.status_code == 401
    approved_finding = client.post(
        f"/api/findings/{finding['id']}/review",
        json={
            "decision": "approved",
            "reviewer": "Caller supplied name",
            "note": "Evidence checked",
        },
    )
    assert approved_finding.status_code == 200
    assert approved_finding.json()["reviewer"] == "Fixture Administrator"

    updated = client.put(
        f"/api/actions/{action['id']}",
        json={
            "title": "Conduct a timed restoration retest and record the result.",
            "owner": "Facilities Operations",
            "priority": "high",
            "due_date": "2026-11-15",
            "acceptance_criteria": "A timed retest records essential circuits restored within 60 seconds.",
        },
    )
    assert updated.status_code == 200
    assert updated.json()["title"] == "Conduct a timed restoration retest and record the result."
    action_approval = client.post(
        f"/api/actions/{action['id']}/review",
        json={"decision": "approved"},
    )
    assert action_approval.status_code == 200
    closure = client.post(
        f"/api/actions/{action['id']}/close",
        json={
            "closure_evidence": "Exercise EX-77 timed retest record accepted by reviewer.",
        },
    )
    assert closure.status_code == 200
    assert closure.json()["status"] == "closed"


def test_action_cannot_be_approved_without_owner_or_approved_finding(client):
    client.post("/api/demo/seed")
    detail = client.get("/api/exercises/HOSP-PO-2026-01").json()
    action = next(item for item in detail["actions"] if item["owner"] is None)
    finding = next(item for item in detail["findings"] if item["id"] == action["finding_id"])
    missing_owner = client.post(
        f"/api/actions/{action['id']}/review",
        json={"decision": "approved"},
    )
    assert missing_owner.status_code == 422
    client.post(
        f"/api/findings/{finding['id']}/review",
        json={"decision": "approved"},
    )
    still_missing = client.post(
        f"/api/actions/{action['id']}/review",
        json={"decision": "approved"},
    )
    assert still_missing.status_code == 422


def test_upload_rejects_unsupported_and_accepts_transcript(client):
    client.post("/api/demo/seed")
    unsupported = client.post(
        "/api/exercises/HOSP-PO-2026-01/evidence", files={"files": ("bad.png", b"x", "image/png")}
    )
    assert unsupported.status_code == 400
    assert unsupported.json()["detail"]["code"] == "UNSUPPORTED_EVIDENCE"
    transcript = client.post(
        "/api/exercises/HOSP-PO-2026-01/transcripts",
        json={
            "transcript": "Unit acknowledged the simulated outage.",
            "source_name": "reviewed-transcript.txt",
            "language": "en",
            "model_version": "manual-review",
            "segments": [],
        },
    )
    assert transcript.status_code == 201
    assert transcript.json()["observations"] == 1
    original = client.get(f"/api/sources/{transcript.json()['source_id']}/download")
    assert original.status_code == 200
    assert b"Unit acknowledged" in original.content


def test_optional_asr_unavailable_returns_controlled_error(client, monkeypatch):
    client.post("/api/demo/seed")
    monkeypatch.delenv("WHISPER_MODEL_PATH", raising=False)
    monkeypatch.setitem(sys.modules, "faster_whisper", None)

    response = client.post(
        "/api/exercises/HOSP-PO-2026-01/audio",
        files={"file": ("unavailable.wav", b"not-real-audio", "audio/wav")},
    )

    assert response.status_code == 503
    assert response.json()["detail"]["code"] == "ASR_UNAVAILABLE"


def test_malformed_csv_timestamp_returns_validation_response(client):
    client.post("/api/demo/seed")
    response = client.post(
        "/api/exercises/HOSP-PO-2026-01/evidence",
        files={"files": ("events.csv", b"timestamp,event\n99:99,Power failed\n", "text/csv")},
    )

    assert response.status_code == 400
    assert response.json()["detail"]["code"] == "INVALID_TIMESTAMP"


def test_upload_rejects_content_type_mismatch_without_persisting_source(client):
    client.post("/api/demo/seed")
    before = client.get("/api/exercises/HOSP-PO-2026-01").json()["sources"]
    response = client.post(
        "/api/exercises/HOSP-PO-2026-01/evidence",
        files={"files": ("events.csv", b"timestamp,event\n09:02,Power failed\n", "image/png")},
    )
    after = client.get("/api/exercises/HOSP-PO-2026-01").json()["sources"]

    assert response.status_code == 415
    assert response.json()["detail"]["code"] == "CONTENT_TYPE_MISMATCH"
    assert len(after) == len(before)


def test_report_export_is_a_pdf(client):
    client.post("/api/demo/seed")
    result = client.get("/api/exercises/HOSP-PO-2026-01/report.pdf")
    assert result.status_code == 200
    assert result.headers["content-type"] == "application/pdf"
    assert result.content.startswith(b"%PDF")


def test_analysis_stops_when_exercise_has_no_objectives(client):
    created = client.post(
        "/api/exercises",
        json={
            "id": "HOSP-EMPTY-01",
            "title": "Incomplete plan",
            "scenario": "A fictional scenario missing objective data.",
            "exercise_date": "2026-10-26",
            "duration_minutes": 60,
            "objectives": [],
        },
    )
    assert created.status_code == 201
    response = client.post("/api/exercises/HOSP-EMPTY-01/analyze")
    assert response.status_code == 422
    assert response.json()["detail"]["code"] == "OBJECTIVES_REQUIRED"
