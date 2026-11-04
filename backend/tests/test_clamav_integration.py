from __future__ import annotations

import os
from io import BytesIO

import pytest
from pypdf import PdfWriter

CLAMAV_HOST = os.getenv("DRILLLOOP_TEST_CLAMAV_HOST")
pytestmark = pytest.mark.skipif(
    not CLAMAV_HOST,
    reason="Set DRILLLOOP_TEST_CLAMAV_HOST to run actual ClamAV integration tests.",
)


def _exercise(client, exercise_id: str):
    return client.post(
        "/api/exercises",
        json={
            "id": exercise_id,
            "title": "Fictional actual-scanner test",
            "scenario": "Synthetic exercise used for a disposable ClamAV integration check.",
            "exercise_date": "2026-11-04",
            "duration_minutes": 30,
            "objectives": [{"id": "SCAN-01", "text": "Restore the fictional service."}],
        },
    )


def _pdf() -> bytes:
    writer = PdfWriter()
    writer.add_blank_page(width=72, height=72)
    output = BytesIO()
    writer.write(output)
    return output.getvalue()


def test_actual_clamav_csv_pdf_eicar_invalid_audit_and_cleanup(client, monkeypatch, tmp_path):
    exercise_id = "ACTUAL-CLAMAV-TEST"
    quarantine = tmp_path / "quarantine"
    quarantine.mkdir(mode=0o700)
    monkeypatch.setenv("DRILLLOOP_UPLOAD_SCAN_MODE", "required")
    monkeypatch.setenv("DRILLLOOP_SCANNER_HOST", CLAMAV_HOST or "")
    monkeypatch.setenv("DRILLLOOP_SCANNER_PORT", os.getenv("DRILLLOOP_TEST_CLAMAV_PORT", "3310"))
    monkeypatch.setenv("DRILLLOOP_SCANNER_MAX_SIGNATURE_AGE_HOURS", "72")
    monkeypatch.setenv("DRILLLOOP_QUARANTINE_DIR", str(quarantine))

    created = _exercise(client, exercise_id)
    assert created.status_code == 201, created.text

    csv = client.post(
        f"/api/exercises/{exercise_id}/evidence",
        files={
            "files": (
                "actual-clean.csv",
                b"timestamp,event\n14:00,Fictional service interruption.\n14:02,Fictional service restored.\n",
                "text/csv",
            )
        },
    )
    assert csv.status_code == 201, csv.text

    pdf = client.post(
        f"/api/exercises/{exercise_id}/evidence",
        files={"files": ("actual-clean.pdf", _pdf(), "application/pdf")},
    )
    assert pdf.status_code == 201, pdf.text

    eicar = b"X5O!P%@AP[4\\PZX54(P^)7CC)7}$EICAR-STANDARD-ANTIVIRUS-TEST-FILE!$H+H*"
    rejected = client.post(
        f"/api/exercises/{exercise_id}/evidence",
        files={"files": ("eicar.txt", eicar, "text/plain")},
    )
    assert rejected.status_code == 422
    assert rejected.json()["detail"]["code"] == "MALWARE_REJECTED"

    invalid = client.post(
        f"/api/exercises/{exercise_id}/evidence",
        files={
            "files": (
                "invalid.csv",
                b"timestamp,event\n99:99,Invalid synthetic timestamp.\n",
                "text/csv",
            )
        },
    )
    assert invalid.status_code == 400
    assert invalid.json()["detail"]["code"] == "INVALID_TIMESTAMP"

    detail = client.get(f"/api/exercises/{exercise_id}").json()
    assert {source["filename"]: source["scan_status"] for source in detail["sources"]} == {
        "actual-clean.csv": "clean",
        "actual-clean.pdf": "clean",
    }
    assert len(detail["timeline"]) == 2
    rejected_event = next(
        event
        for event in detail["audit_events"]
        if event["action"] == "upload_rejected"
        and event["details"]["error_code"] == "MALWARE_REJECTED"
    )
    assert rejected_event["details"]["scanner_version"]
    assert rejected_event["details"]["signature_timestamp"]
    assert list(quarantine.iterdir()) == []
