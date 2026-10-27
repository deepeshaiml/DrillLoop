from __future__ import annotations

REVIEW = {"X-Reviewer-Key": "test-reviewer", "Content-Type": "application/json"}


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


def test_authorized_reviewer_controls_finding_and_action_closure(client):
    client.post("/api/demo/seed")
    detail = client.get("/api/exercises/HOSP-PO-2026-01").json()
    finding = next(item for item in detail["findings"] if item["code"] == "POWER_RESTORATION_DELAY")
    action = next(item for item in detail["actions"] if item["finding_id"] == finding["id"])

    unauthorized = client.post(
        f"/api/findings/{finding['id']}/review", json={"decision": "approved", "reviewer": "Alex"}
    )
    assert unauthorized.status_code == 401
    approved_finding = client.post(
        f"/api/findings/{finding['id']}/review",
        headers=REVIEW,
        json={"decision": "approved", "reviewer": "Alex", "note": "Evidence checked"},
    )
    assert approved_finding.status_code == 200

    updated = client.put(
        f"/api/actions/{action['id']}",
        headers=REVIEW,
        json={
            "owner": "Facilities Operations",
            "priority": "high",
            "due_date": "2026-11-15",
            "acceptance_criteria": "A timed retest records essential circuits restored within 60 seconds.",
            "reviewer": "Alex",
        },
    )
    assert updated.status_code == 200
    action_approval = client.post(
        f"/api/actions/{action['id']}/review",
        headers=REVIEW,
        json={"decision": "approved", "reviewer": "Alex"},
    )
    assert action_approval.status_code == 200
    closure = client.post(
        f"/api/actions/{action['id']}/close",
        headers=REVIEW,
        json={
            "closure_evidence": "Exercise EX-77 timed retest record accepted by reviewer.",
            "reviewer": "Alex",
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
        headers=REVIEW,
        json={"decision": "approved", "reviewer": "Alex"},
    )
    assert missing_owner.status_code == 422
    client.post(
        f"/api/findings/{finding['id']}/review",
        headers=REVIEW,
        json={"decision": "approved", "reviewer": "Alex"},
    )
    still_missing = client.post(
        f"/api/actions/{action['id']}/review",
        headers=REVIEW,
        json={"decision": "approved", "reviewer": "Alex"},
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
