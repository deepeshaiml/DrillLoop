from __future__ import annotations

from datetime import date

import pytest


def _create_exercise(client, exercise_id: str, objective: dict):
    response = client.post(
        "/api/exercises",
        json={
            "id": exercise_id,
            "title": "Unfamiliar evidence evaluation",
            "scenario": "A separate fictional exercise for objective-rule verification.",
            "exercise_date": date(2026, 11, 3).isoformat(),
            "duration_minutes": 90,
            "objectives": [objective],
        },
    )
    assert response.status_code == 201, response.text


def _upload_events(client, exercise_id: str, records: list[tuple[str, str, str]]):
    csv_bytes = "event_id,timestamp,event\n" + "".join(
        f"{event_id},{timestamp},{event}\n" for event_id, timestamp, event in records
    )
    response = client.post(
        f"/api/exercises/{exercise_id}/evidence",
        files={"files": ("unfamiliar-events.csv", csv_bytes.encode(), "text/csv")},
    )
    assert response.status_code == 201, response.text


def _elapsed_objective(threshold_seconds: int) -> dict:
    threshold_minutes = threshold_seconds // 60
    return {
        "id": "OBJ-LOCAL-01",
        "text": f"Restore the essential system within {threshold_minutes} minutes of power loss.",
        "evaluation_rule": {
            "type": "elapsed_time",
            "threshold_seconds": threshold_seconds,
            "start_terms": ["external power supply failed"],
            "completion_terms": ["essential system restored to normal"],
        },
    }


@pytest.mark.parametrize(
    ("threshold_seconds", "expected_state", "expected_elapsed"),
    [
        (300, "confirmed_success", [240]),
        (240, "confirmed_success", [240]),
        (120, "confirmed_failure", [240]),
    ],
)
def test_elapsed_assessment_uses_selected_objective_and_evidence_times(
    client, threshold_seconds, expected_state, expected_elapsed
):
    exercise_id = f"UNFAMILIAR-{threshold_seconds}"
    _create_exercise(client, exercise_id, _elapsed_objective(threshold_seconds))
    # Completion appears first in source order; arithmetic follows timestamps, not CSV order.
    _upload_events(
        client,
        exercise_id,
        [
            ("NEW-02", "14:04", "Essential system restored to normal."),
            ("NEW-01", "14:00", "External power supply failed."),
        ],
    )

    result = client.post(f"/api/exercises/{exercise_id}/analyze")
    assert result.status_code == 200, result.text
    assessment = result.json()["objective_assessments"][0]
    detail = client.get(f"/api/exercises/{exercise_id}").json()

    assert assessment["state"] == expected_state
    assert assessment["threshold_seconds"] == threshold_seconds
    assert assessment["elapsed_seconds"] == expected_elapsed
    assert len(detail["findings"]) == 1
    finding = detail["findings"][0]
    assert finding["objective_id"] == "OBJ-LOCAL-01"
    assert finding["status"] == "proposed"
    assert {item["source_locator"] for item in finding["supporting_evidence"]} == {
        "row 2 · NEW-02",
        "row 3 · NEW-01",
    }
    assert "14:00" not in finding["observation"]
    assert "09:02" not in finding["observation"]
    assert "240 seconds" in finding["observation"]
    if expected_state == "confirmed_failure":
        action = detail["actions"][0]
        assert action["owner"] is None
        assert action["due_date"] is None


def test_missing_or_ambiguous_objective_evidence_remains_unknown(client):
    objective = _elapsed_objective(300)
    exercise_id = "UNFAMILIAR-MISSING"
    _create_exercise(client, exercise_id, objective)
    _upload_events(client, exercise_id, [("ONLY-START", "14:00", "External power supply failed.")])

    response = client.post(f"/api/exercises/{exercise_id}/analyze")
    assessment = response.json()["objective_assessments"][0]
    detail = client.get(f"/api/exercises/{exercise_id}").json()

    assert response.status_code == 200
    assert assessment["state"] == "insufficient_information"
    assert "completion event" in assessment["unknowns"][0]
    assert detail["findings"] == []
    assert detail["actions"] == []


def test_conflicting_timestamps_are_flagged_without_forcing_a_result(client):
    exercise_id = "UNFAMILIAR-CONFLICT"
    _create_exercise(client, exercise_id, _elapsed_objective(300))
    _upload_events(
        client,
        exercise_id,
        [
            ("START", "14:00", "External power supply failed."),
            ("END-A", "14:04", "Essential system restored to normal."),
            ("END-B", "14:08", "Essential system restored to normal."),
        ],
    )

    response = client.post(f"/api/exercises/{exercise_id}/analyze")
    assessment = response.json()["objective_assessments"][0]
    detail = client.get(f"/api/exercises/{exercise_id}").json()

    assert response.status_code == 200
    assert assessment["state"] == "conflicting_evidence"
    assert assessment["elapsed_seconds"] == [240, 480]
    assert assessment["conflicts"]
    assert detail["findings"] == []
    assert detail["actions"] == []


def test_objective_without_rule_returns_needs_review_not_a_finding(client):
    exercise_id = "UNFAMILIAR-NO-RULE"
    _create_exercise(
        client,
        exercise_id,
        {"id": "OBJ-UNKNOWN", "text": "Coordinate the response effectively."},
    )
    _upload_events(
        client, exercise_id, [("ROW-1", "14:00", "Several teams coordinated the response.")]
    )

    response = client.post(f"/api/exercises/{exercise_id}/analyze")
    assessment = response.json()["objective_assessments"][0]

    assert response.status_code == 200
    assert assessment["state"] == "needs_review"
    assert "No explicit deterministic evaluation rule" in assessment["unknowns"][0]
    assert response.json()["candidate_count"] == 0


def test_conflicting_required_field_evidence_remains_unresolved(client):
    exercise_id = "UNFAMILIAR-FIELD-CONFLICT"
    _create_exercise(
        client,
        exercise_id,
        {
            "id": "OBJ-FIELD",
            "text": "Record the corrective-action owner.",
            "evaluation_rule": {
                "type": "required_field",
                "missing_terms": ["owner missing"],
                "present_terms": ["owner assigned"],
            },
        },
    )
    _upload_events(
        client,
        exercise_id,
        [
            ("FIELD-1", "14:00", "Owner missing in the signed action register."),
            ("FIELD-2", "14:01", "Owner assigned in the signed action register."),
        ],
    )

    result = client.post(f"/api/exercises/{exercise_id}/analyze")
    detail = client.get(f"/api/exercises/{exercise_id}").json()
    assessment = result.json()["objective_assessments"][0]

    assert result.status_code == 200
    assert assessment["state"] == "conflicting_evidence"
    assert len(assessment["evidence"]) == 2
    assert assessment["conflicts"]
    assert detail["findings"] == []
    assert detail["actions"] == []


def test_objectives_can_be_edited_before_analysis_and_lock_afterward(client):
    exercise_id = "OBJECTIVE-EDIT-01"
    _create_exercise(
        client,
        exercise_id,
        {"id": "OBJ-EDIT", "text": "Complete the new objective."},
    )
    updated_objective = _elapsed_objective(300)
    update = client.put(
        f"/api/exercises/{exercise_id}/objectives",
        json={"objectives": [updated_objective], "criteria": ["Use source timestamps"]},
    )
    assert update.status_code == 200, update.text
    assert update.json()["objectives"] == [updated_objective]

    analyzed = client.post(f"/api/exercises/{exercise_id}/analyze")
    assert analyzed.status_code == 200
    assert client.get(f"/api/exercises/{exercise_id}").json()["analysis_locked"] is True

    refused = client.put(
        f"/api/exercises/{exercise_id}/objectives",
        json={"objectives": [{"id": "OBJ-EDIT", "text": "A revised objective."}], "criteria": []},
    )
    assert refused.status_code == 409
    assert refused.json()["detail"]["code"] == "OBJECTIVES_LOCKED_AFTER_ANALYSIS"


def test_exercise_evidence_and_findings_remain_isolated(client):
    first_id = "INDEPENDENT-5M"
    second_id = "INDEPENDENT-2M"
    _create_exercise(client, first_id, _elapsed_objective(300))
    _create_exercise(client, second_id, _elapsed_objective(120))
    records = [
        ("COMPLETE", "14:04", "Essential system restored to normal."),
        ("START", "14:00", "External power supply failed."),
    ]
    _upload_events(client, first_id, records)
    _upload_events(client, second_id, records)

    first_result = client.post(f"/api/exercises/{first_id}/analyze").json()
    second_result = client.post(f"/api/exercises/{second_id}/analyze").json()
    first_detail = client.get(f"/api/exercises/{first_id}").json()
    second_detail = client.get(f"/api/exercises/{second_id}").json()
    listed = {item["id"] for item in client.get("/api/exercises").json()}

    assert first_result["objective_assessments"][0]["state"] == "confirmed_success"
    assert second_result["objective_assessments"][0]["state"] == "confirmed_failure"
    assert first_detail["exercise"]["id"] == first_id
    assert second_detail["exercise"]["id"] == second_id
    assert len(first_detail["sources"]) == len(second_detail["sources"]) == 1
    assert first_detail["sources"][0]["id"] != second_detail["sources"][0]["id"]
    assert first_id in listed and second_id in listed
