from __future__ import annotations

from io import BytesIO

from app.reporting import make_report_pdf
from pypdf import PdfReader


def _pdf_text(content: bytes) -> tuple[str, int]:
    reader = PdfReader(BytesIO(content))
    text = " ".join(" ".join((page.extract_text() or "").split()) for page in reader.pages)
    return text, len(reader.pages)


def _report_detail() -> dict:
    return {
        "exercise": {
            "id": "CUSTOM-REPORT-01",
            "title": "Custom exercise for report accuracy",
            "scenario": "A custom exercise with no synthetic classification metadata.",
            "exercise_date": "2026-11-06",
            "duration_minutes": 90,
            "objectives": [{"id": "OBJ-1", "text": "Restore service and report the result."}],
            "expected_milestones": [
                {"id": "M-1", "expected": "Service restored", "objective_id": "OBJ-1"}
            ],
        },
        "timeline": [
            {
                "event_time_normalized": None,
                "text": "Source record reports an unresolved acknowledgement time.",
                "source_filename": "incident_" + "source_" * 15 + "record.csv",
                "source_locator": "row 29 · EL-29",
                "time_confidence": "uncertain",
            }
        ],
        "timeline_conflicts": [
            {
                "description": "Two source times remain unresolved.",
                "source_locator": "row 29 · EL-29",
            }
        ],
        "findings": [
            {
                "id": "finding-proposed",
                "title": "Proposed finding",
                "category": "improvement",
                "objective_id": "OBJ-1",
                "observation": "Source wording from the exercise record.",
                "interpretation": "Analysis-time assessment. Reviewer decision: pending.",
                "evidence_labels": ["very_long_filename_" + "x" * 100 + ".csv · row 4 · EL-04"],
                "status": "proposed",
                "review_note": "",
                "reviewer": None,
            },
            {
                "id": "finding-approved",
                "title": "Approved finding with historical pending text",
                "category": "improvement",
                "objective_id": "OBJ-1",
                "observation": "A source-backed finding.",
                "interpretation": "Original analysis text. Reviewer decision: pending.",
                "evidence_labels": ["events.csv · row 6 · EL-06"],
                "status": "approved",
                "review_note": "Evaluator accepted the cited evidence.",
                "reviewer": "Fixture Reviewer",
            },
            {
                "id": "finding-rejected",
                "title": "Rejected finding",
                "category": "strength",
                "objective_id": None,
                "observation": "A record reviewed and rejected.",
                "interpretation": "Original interpretation text.",
                "evidence_labels": [],
                "status": "rejected",
                "review_note": "The source does not support this conclusion.",
                "reviewer": None,
            },
        ],
        "actions": [
            {
                "id": "action-closed",
                "finding_id": "finding-approved",
                "finding_title": "Approved finding with historical pending text",
                "title": "Conduct a retest with a deliberately long action description " * 3,
                "owner": "Facilities Operations",
                "due_date": "2026-12-12",
                "priority": "high",
                "acceptance_criteria": "A long acceptance criterion that must wrap across the report without clipping. "
                * 10,
                "status": "closed",
                "reviewer_decision": "approved",
                "reviewer": "Fixture Reviewer",
                "closure_evidence": "Synthetic test record: retest completed and evidence stored.",
            },
            {
                "id": "action-pending",
                "finding_id": "finding-proposed",
                "finding_title": "Proposed finding",
                "title": "Action awaiting approval",
                "owner": None,
                "due_date": None,
                "priority": "medium",
                "acceptance_criteria": "Not provided in this test record.",
                "status": "proposed",
                "reviewer_decision": "pending",
                "reviewer": None,
                "closure_evidence": "",
            },
        ],
        "sources": [
            {
                "filename": "very_long_source_filename_" + "report_" * 20 + ".csv",
                "kind": "csv",
                "sha256": "abcdef0123456789" * 4,
            }
        ],
        "audit_events": [
            {
                "actor": "Fixture Reviewer",
                "action": "finding_approved",
                "object_id": "finding-approved",
                "details": {"note": "Evaluator accepted the cited evidence."},
                "created_at": "2026-11-06T10:30:00+00:00",
            },
            {
                "actor": "Fixture Reviewer",
                "action": "finding_rejected",
                "object_id": "finding-rejected",
                "details": {"note": "The source does not support this conclusion."},
                "created_at": "2026-11-06T10:35:00+00:00",
            },
            {
                "actor": "Fixture Reviewer",
                "action": "action_approved",
                "object_id": "action-closed",
                "details": {"note": "Owner and due date reviewed."},
                "created_at": "2026-11-06T10:40:00+00:00",
            },
            {
                "actor": "Fixture Reviewer",
                "action": "action_closed",
                "object_id": "action-closed",
                "details": {
                    "closure_evidence": "Synthetic test record: retest completed and evidence stored."
                },
                "created_at": "2026-11-06T11:00:00+00:00",
            },
        ],
    }


def test_custom_report_uses_neutral_identity_and_current_decisions():
    detail = _report_detail()
    text, page_count = _pdf_text(make_report_pdf(detail))

    assert "Custom exercise for report accuracy" in text
    assert "Exercise report" in text
    assert "Fictional synthetic hospital" not in text
    assert "Synthetic exercise" not in text
    assert "CURRENT REVIEW STATE" in text
    assert "PROPOSED" in text and "APPROVED" in text and "REJECTED" in text
    assert "Analysis-time interpretation" in text
    assert "Original analysis text. Reviewer decision: pending." in text
    assert "Current reviewer status: Approved by Fixture Reviewer" in text
    assert "2026-11-06 10:30:00 +00:00" in text
    assert "Evaluator accepted the cited evidence." in text
    assert "Current reviewer status: Proposed" in text
    assert "Finding Rejected" in text
    assert "Action Closed" in text
    assert "Linked finding: Approved finding with historical pending text" in text
    assert "Closed with recorded evidence" in text
    assert "not independent verification" in text
    assert "Synthetic test record: retest completed and evidence stored." in text
    assert "Owner: Not recorded" in text
    assert "Due date: Not recorded" in text
    assert "Two source times remain unresolved." in text
    assert "very_long_source_filename_" in text
    assert "Acceptance criteria" in text
    assert page_count >= 2
    assert f"Page {page_count}" in text


def test_packaged_hospital_report_is_labeled_fictional():
    detail = _report_detail()
    detail["exercise"] = {
        **detail["exercise"],
        "id": "HOSP-PO-2026-01",
        "title": "Night Shift: Extended Power Loss",
        "scenario": "Fictional regional hospital exercise: prolonged utility outage.",
    }
    text, _ = _pdf_text(make_report_pdf(detail))

    assert "Fictional synthetic exercise" in text
    assert "Fictional regional hospital exercise" in text
    assert "DRILLLOOP · Fictional synthetic exercise" in text


def test_reviewed_finding_without_reviewer_metadata_shows_unknowns():
    detail = _report_detail()
    approved = detail["findings"][1]
    approved["reviewer"] = None
    approved["review_note"] = ""
    detail["audit_events"] = []
    text, _ = _pdf_text(make_report_pdf(detail))

    assert "Current reviewer status: Approved by Not recorded" in text
    assert "Not recorded in audit history" in text
    assert "No reviewer note recorded." in text


def test_report_api_uses_current_workflow_state_and_audit_history(client):
    seeded = client.post("/api/demo/seed")
    assert seeded.status_code == 200
    detail = client.get("/api/exercises/HOSP-PO-2026-01").json()
    finding = next(row for row in detail["findings"] if row["code"] == "POWER_RESTORATION_DELAY")
    action = next(row for row in detail["actions"] if row["finding_id"] == finding["id"])

    approved = client.post(
        f"/api/findings/{finding['id']}/review",
        json={"decision": "approved", "note": "Reviewed source citations."},
    )
    assert approved.status_code == 200
    updated = client.put(
        f"/api/actions/{action['id']}",
        json={
            "title": "Conduct a timed power restoration retest.",
            "owner": "Facilities Operations",
            "priority": "high",
            "due_date": "2026-12-12",
            "acceptance_criteria": "Retest records restoration within the stated objective.",
        },
    )
    assert updated.status_code == 200
    action_approved = client.post(
        f"/api/actions/{action['id']}/review",
        json={"decision": "approved", "note": "Plan accepted."},
    )
    assert action_approved.status_code == 200
    closed = client.post(
        f"/api/actions/{action['id']}/close",
        json={"closure_evidence": "Synthetic retest record accepted for this test exercise."},
    )
    assert closed.status_code == 200

    response = client.get("/api/exercises/HOSP-PO-2026-01/report.pdf")
    assert response.status_code == 200
    assert response.headers["content-type"] == "application/pdf"
    text, _ = _pdf_text(response.content)
    assert "Current reviewer status: Approved by Fixture Administrator" in text
    assert "Reviewer note: Reviewed source citations." in text
    assert "Reviewer decision: pending." in text
    assert "Analysis-time interpretation" in text
    assert "Closed with recorded evidence" in text
    assert "Synthetic retest record accepted for this test exercise." in text
    assert "Fixture Administrator" in text
    assert "finding_approved" not in text
    assert "Finding Approved" in text
