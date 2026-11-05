from __future__ import annotations

import asyncio
import threading
import time
from datetime import date
from unittest.mock import Mock

import pytest
from app import upload_processing
from app.db import SessionLocal
from app.evidence import safe_filename
from app.limits import RequestBodyLimitMiddleware
from app.main import MAX_FILE_SIZE
from app.models import AuditEvent
from app.upload_processing import (
    ParserAdmissionController,
    UploadCancelled,
    UploadProcessingFailure,
    process_upload_isolated,
)


def test_upload_parser_runs_in_disposable_worker_and_marks_unscanned(monkeypatch):
    monkeypatch.setenv("DRILLLOOP_UPLOAD_SCAN_MODE", "disabled")
    parsed, scan_status = process_upload_isolated(
        "../synthetic.csv",
        "text/csv",
        b"timestamp,event\n09:00,fictional event\n",
        date(2026, 11, 3),
    )

    assert parsed.observations[0].source_locator == "row 2"
    assert parsed.observations[0].text == "fictional event"
    assert scan_status.status == "not_scanned"


def test_required_scanner_fails_closed_when_adapter_is_missing(monkeypatch):
    monkeypatch.setenv("DRILLLOOP_UPLOAD_SCAN_MODE", "required")
    monkeypatch.delenv("DRILLLOOP_SCANNER_HOST", raising=False)
    monkeypatch.setattr(upload_processing.shutil, "which", lambda _name: None)

    with pytest.raises(UploadProcessingFailure, match="unavailable") as error:
        upload_processing._clamav_scan(b"synthetic", "required")

    assert error.value.code == "SCANNER_UNAVAILABLE"
    assert upload_processing._clamav_scan(b"synthetic", "optional").status == "not_scanned"


def test_stale_clamav_signatures_remain_rejected(monkeypatch):
    monkeypatch.setenv("DRILLLOOP_SCANNER_MAX_SIGNATURE_AGE_HOURS", "72")
    monkeypatch.setattr(
        upload_processing,
        "_clamd_command",
        lambda *_args: "ClamAV 1.5.4/1/Mon Jan  1 00:00:00 2024",
    )

    with pytest.raises(UploadProcessingFailure) as error:
        upload_processing._checked_signature_version("clamav", 3310, 1)

    assert error.value.code == "SCANNER_SIGNATURES_STALE"
    assert error.value.details["signature_max_age_hours"] == 72


def test_parser_backpressure_and_portable_filename_sanitization(monkeypatch):
    controller = ParserAdmissionController(active_limit=1, waiting_limit=0)
    monkeypatch.setattr(upload_processing, "_PARSER_ADMISSION", controller)
    controller.acquire(1)
    with pytest.raises(UploadProcessingFailure) as error:
        process_upload_isolated(
            "events.csv", "text/csv", b"timestamp,event\n09:00,synthetic\n", date(2026, 11, 3)
        )
    assert error.value.code == "PARSER_CAPACITY_EXHAUSTED"
    controller.release()
    assert safe_filename(r"..\\..\\evidence\\events.csv") == "events.csv"
    assert safe_filename("../../") == "evidence"


def test_scanner_rejection_prevents_import(monkeypatch):
    monkeypatch.setenv("DRILLLOOP_UPLOAD_SCAN_MODE", "optional")
    monkeypatch.setattr(upload_processing.shutil, "which", lambda _name: "/usr/bin/clamdscan")
    monkeypatch.setattr(
        upload_processing.subprocess,
        "run",
        lambda *_args, **_kwargs: Mock(returncode=1, stdout="", stderr=""),
    )

    with pytest.raises(UploadProcessingFailure) as error:
        upload_processing._clamav_scan(b"synthetic", "optional")

    assert error.value.code == "MALWARE_REJECTED"


def _fake_scanner(tmp_path, body: str) -> tuple[str, str]:
    scanner_dir = tmp_path / "scanner-bin"
    scanner_dir.mkdir(mode=0o700)
    scanner = scanner_dir / "clamdscan"
    scanner.write_text(f"#!/bin/sh\n{body}\n", encoding="utf-8")
    scanner.chmod(0o700)
    quarantine = tmp_path / "quarantine"
    quarantine.mkdir(mode=0o700)
    return str(scanner_dir), str(quarantine)


def test_scanner_clean_verdict_uses_private_quarantine_and_cleans_file(monkeypatch, tmp_path):
    scanner_path, quarantine = _fake_scanner(tmp_path, "exit 0")
    monkeypatch.setenv("PATH", scanner_path)
    monkeypatch.setenv("DRILLLOOP_QUARANTINE_DIR", quarantine)
    monkeypatch.setenv("DRILLLOOP_UPLOAD_SCAN_MODE", "required")
    monkeypatch.delenv("DRILLLOOP_SCANNER_HOST", raising=False)

    assert upload_processing._clamav_scan(b"fictional clean fixture", "required").status == "clean"
    assert list((tmp_path / "quarantine").iterdir()) == []


@pytest.mark.parametrize(
    ("script", "timeout", "expected_code"),
    [
        ("exit 1", "5", "MALWARE_REJECTED"),
        ("exit 2", "5", "SCANNER_FAILED"),
        ("/bin/sleep 2; exit 0", "1", "SCANNER_TIMEOUT"),
    ],
)
def test_scanner_rejects_malicious_error_and_timeout_verdicts(
    monkeypatch, tmp_path, script, timeout, expected_code
):
    scanner_path, quarantine = _fake_scanner(tmp_path, script)
    monkeypatch.setenv("PATH", scanner_path)
    monkeypatch.setenv("DRILLLOOP_QUARANTINE_DIR", quarantine)
    monkeypatch.setenv("DRILLLOOP_SCANNER_TIMEOUT_SECONDS", timeout)
    monkeypatch.delenv("DRILLLOOP_SCANNER_HOST", raising=False)

    with pytest.raises(UploadProcessingFailure) as error:
        upload_processing._clamav_scan(b"fictional scanner fixture", "required")

    assert error.value.code == expected_code
    assert list((tmp_path / "quarantine").iterdir()) == []


def test_required_scanner_unavailable_rejects_api_upload_and_records_audit(
    client, monkeypatch, tmp_path
):
    empty_path = tmp_path / "empty-path"
    empty_path.mkdir(mode=0o700)
    monkeypatch.setenv("PATH", str(empty_path))
    monkeypatch.setenv("DRILLLOOP_UPLOAD_SCAN_MODE", "required")
    monkeypatch.delenv("DRILLLOOP_SCANNER_HOST", raising=False)
    exercise = client.post(
        "/api/exercises",
        json={
            "id": "SCAN-UNAVAILABLE-01",
            "title": "Fictional scanner outage",
            "scenario": "Synthetic test of required scanner fail-closed behavior.",
            "exercise_date": "2026-11-03",
            "duration_minutes": 30,
            "objectives": [{"id": "O1", "text": "Restore essential service."}],
        },
    )
    assert exercise.status_code == 201

    response = client.post(
        "/api/exercises/SCAN-UNAVAILABLE-01/evidence",
        files={"files": ("synthetic.txt", b"fictional evidence", "text/plain")},
    )

    assert response.status_code == 503
    assert response.json()["detail"]["code"] == "SCANNER_UNAVAILABLE"
    detail = client.get("/api/exercises/SCAN-UNAVAILABLE-01").json()
    assert detail["sources"] == []
    analysis = client.post("/api/exercises/SCAN-UNAVAILABLE-01/analyze")
    assert analysis.status_code == 200
    assert analysis.json()["objective_assessments"][0]["state"] == "needs_review"
    with SessionLocal() as session:
        rejected = session.query(AuditEvent).filter_by(action="upload_rejected").one()
        assert '"scan_status": "unavailable"' in rejected.details_json


def test_required_clean_scanner_verdict_allows_upload_for_analysis(monkeypatch, tmp_path, client):
    scanner_path, quarantine = _fake_scanner(tmp_path, "exit 0")
    monkeypatch.setenv("PATH", scanner_path)
    monkeypatch.setenv("DRILLLOOP_QUARANTINE_DIR", quarantine)
    monkeypatch.setenv("DRILLLOOP_UPLOAD_SCAN_MODE", "required")
    monkeypatch.delenv("DRILLLOOP_SCANNER_HOST", raising=False)
    exercise = client.post(
        "/api/exercises",
        json={
            "id": "SCAN-CLEAN-01",
            "title": "Fictional clean scan",
            "scenario": "Synthetic test of a clean scanner verdict and upload import.",
            "exercise_date": "2026-11-03",
            "duration_minutes": 30,
            "objectives": [{"id": "O1", "text": "Restore the essential service."}],
        },
    )
    assert exercise.status_code == 201
    response = client.post(
        "/api/exercises/SCAN-CLEAN-01/evidence",
        files={"files": ("synthetic.txt", b"fictional evidence", "text/plain")},
    )

    assert response.status_code == 201, response.text
    detail = client.get("/api/exercises/SCAN-CLEAN-01").json()
    assert len(detail["sources"]) == 1
    assert detail["sources"][0]["scan_status"] == "clean"
    assert len(detail["timeline"]) == 1


def test_required_malware_verdict_never_persists_or_exposes_upload(monkeypatch, tmp_path, client):
    scanner_path, quarantine = _fake_scanner(tmp_path, "exit 1")
    monkeypatch.setenv("PATH", scanner_path)
    monkeypatch.setenv("DRILLLOOP_QUARANTINE_DIR", quarantine)
    monkeypatch.setenv("DRILLLOOP_UPLOAD_SCAN_MODE", "required")
    monkeypatch.delenv("DRILLLOOP_SCANNER_HOST", raising=False)
    exercise = client.post(
        "/api/exercises",
        json={
            "id": "SCAN-REJECTED-01",
            "title": "Fictional rejected scan",
            "scenario": "Synthetic test of malware verdict quarantine and rejection.",
            "exercise_date": "2026-11-03",
            "duration_minutes": 30,
            "objectives": [{"id": "O1", "text": "Restore the essential service."}],
        },
    )
    assert exercise.status_code == 201
    response = client.post(
        "/api/exercises/SCAN-REJECTED-01/evidence",
        files={"files": ("synthetic.txt", b"fictional rejected fixture", "text/plain")},
    )

    assert response.status_code == 422
    assert response.json()["detail"]["code"] == "MALWARE_REJECTED"
    detail = client.get("/api/exercises/SCAN-REJECTED-01").json()
    assert detail["sources"] == []
    assert detail["timeline"] == []
    analysis = client.post("/api/exercises/SCAN-REJECTED-01/analyze")
    assert analysis.status_code == 200
    assert analysis.json()["objective_assessments"][0]["state"] == "needs_review"


def test_parser_timeout_terminates_child_and_removes_quarantine(monkeypatch, tmp_path):
    quarantine = tmp_path / "quarantine"
    quarantine.mkdir(mode=0o700)
    job_directory = []

    def make_job_directory():
        path = quarantine / "job"
        path.mkdir(mode=0o700)
        job_directory.append(path)
        return str(path)

    monkeypatch.setenv("DRILLLOOP_UPLOAD_SCAN_MODE", "required")
    monkeypatch.setattr(upload_processing, "_make_job_quarantine", make_job_directory)

    class Connection:
        def poll(self, _timeout):
            return False

        def close(self):
            return None

    class Process:
        def __init__(self, **_kwargs):
            self.alive = True
            self.terminated = False
            self.killed = False

        def start(self):
            (job_directory[0] / "orphaned-scan").mkdir()
            return None

        def join(self, **_kwargs):
            return None

        def is_alive(self):
            return self.alive

        def terminate(self):
            self.terminated = True

        def kill(self):
            self.killed = True
            self.alive = False

    parent = Connection()
    child = Connection()
    fake_process = Process()
    fake_context = Mock()
    fake_context.Pipe.return_value = (parent, child)
    fake_context.Process.return_value = fake_process
    monkeypatch.setattr(
        upload_processing.multiprocessing, "get_context", lambda _name: fake_context
    )

    with pytest.raises(UploadProcessingFailure) as error:
        process_upload_isolated(
            "synthetic.csv",
            "text/csv",
            b"timestamp,event\n09:00,synthetic\n",
            date(2026, 11, 3),
            timeout_seconds=1,
        )

    assert error.value.code == "PARSER_TIMEOUT"
    assert fake_process.terminated is True
    assert fake_process.killed is True
    assert list(quarantine.iterdir()) == []


def test_parser_admission_waits_fairly_and_releases_every_slot():
    controller = ParserAdmissionController(active_limit=1, waiting_limit=2)
    controller.acquire(1)
    outcomes = []

    def wait_for_slot():
        controller.acquire(2)
        outcomes.append("admitted")
        controller.release()

    first = threading.Thread(target=wait_for_slot)
    second = threading.Thread(target=wait_for_slot)
    first.start()
    deadline = time.monotonic() + 2
    while controller.snapshot()[1] != 1 and time.monotonic() < deadline:
        time.sleep(0.01)
    second.start()
    deadline = time.monotonic() + 2
    while controller.snapshot()[1] != 2 and time.monotonic() < deadline:
        time.sleep(0.01)
    assert controller.snapshot()[:2] == (1, 2)

    controller.release()
    first.join(timeout=3)
    second.join(timeout=3)
    assert not first.is_alive()
    assert not second.is_alive()
    assert outcomes == ["admitted", "admitted"]
    assert controller.snapshot() == (0, 0, 0)


def test_full_admission_queue_rejects_safely_and_retry_succeeds():
    controller = ParserAdmissionController(active_limit=1, waiting_limit=1)
    controller.acquire(1)
    queued = threading.Event()
    finished = threading.Event()
    failures = []

    def wait_for_slot():
        try:
            controller.acquire(3)
            queued.set()
            controller.release()
        except Exception as error:  # surfaced to the main test thread
            failures.append(error)
        finally:
            finished.set()

    waiting_thread = threading.Thread(target=wait_for_slot)
    waiting_thread.start()
    deadline = time.monotonic() + 2
    while controller.snapshot()[1] != 1 and time.monotonic() < deadline:
        time.sleep(0.01)
    with pytest.raises(UploadProcessingFailure) as error:
        controller.acquire(1)
    assert error.value.code == "PARSER_CAPACITY_EXHAUSTED"
    assert error.value.retry_after_seconds == 2
    controller.release()
    assert finished.wait(3)
    waiting_thread.join(timeout=1)
    assert not failures
    assert queued.is_set()
    controller.acquire(1)
    controller.release()
    assert controller.snapshot() == (0, 0, 1)


def test_cancelled_waiter_is_removed_without_consuming_a_slot():
    controller = ParserAdmissionController(active_limit=1, waiting_limit=1)
    controller.acquire(1)
    cancelled = threading.Event()
    finished = threading.Event()
    errors = []

    def wait_for_slot():
        try:
            controller.acquire(5, cancelled)
        except Exception as error:
            errors.append(error)
        finally:
            finished.set()

    waiting_thread = threading.Thread(target=wait_for_slot)
    waiting_thread.start()
    deadline = time.monotonic() + 2
    while controller.snapshot()[1] != 1 and time.monotonic() < deadline:
        time.sleep(0.01)
    cancelled.set()
    assert finished.wait(2)
    waiting_thread.join(timeout=1)
    assert len(errors) == 1 and isinstance(errors[0], UploadCancelled)
    assert controller.snapshot() == (1, 0, 0)
    controller.release()
    assert controller.snapshot() == (0, 0, 0)


def test_cancelled_parser_terminates_child_and_removes_quarantine(monkeypatch, tmp_path):
    quarantine = tmp_path / "quarantine"
    quarantine.mkdir(mode=0o700)
    job_directory = []

    def make_job_directory():
        path = quarantine / "job"
        path.mkdir(mode=0o700)
        job_directory.append(path)
        return str(path)

    monkeypatch.setenv("DRILLLOOP_UPLOAD_SCAN_MODE", "required")
    monkeypatch.setattr(upload_processing, "_make_job_quarantine", make_job_directory)

    class Connection:
        def poll(self, _timeout):
            return False

        def close(self):
            return None

    class Process:
        def __init__(self, **_kwargs):
            self.alive = True
            self.terminated = False
            self.killed = False

        def start(self):
            (job_directory[0] / "orphaned-scan").mkdir()
            return None

        def join(self, **_kwargs):
            return None

        def is_alive(self):
            return self.alive

        def terminate(self):
            self.terminated = True

        def kill(self):
            self.killed = True
            self.alive = False

    fake_process = Process()
    fake_context = Mock()
    fake_context.Pipe.return_value = (Connection(), Connection())
    fake_context.Process.return_value = fake_process
    monkeypatch.setattr(
        upload_processing.multiprocessing, "get_context", lambda _name: fake_context
    )
    cancellation = threading.Event()
    errors = []

    def process():
        try:
            process_upload_isolated(
                "synthetic.csv",
                "text/csv",
                b"timestamp,event\n09:00,synthetic\n",
                date(2026, 11, 3),
                timeout_seconds=5,
                cancellation_event=cancellation,
            )
        except Exception as error:
            errors.append(error)

    worker_thread = threading.Thread(target=process)
    worker_thread.start()
    time.sleep(0.15)
    cancellation.set()
    worker_thread.join(timeout=3)

    assert not worker_thread.is_alive()
    assert len(errors) == 1 and isinstance(errors[0], UploadCancelled)
    assert fake_process.terminated is True
    assert fake_process.killed is True
    assert upload_processing._PARSER_ADMISSION.snapshot()[:2] == (0, 0)
    assert list(quarantine.iterdir()) == []


def test_upload_capacity_503_can_be_retried_without_duplicate_records(client, monkeypatch):
    monkeypatch.setenv("DRILLLOOP_UPLOAD_SCAN_MODE", "disabled")
    controller = ParserAdmissionController(active_limit=1, waiting_limit=0)
    monkeypatch.setattr(upload_processing, "_PARSER_ADMISSION", controller)
    controller.acquire(1)
    exercise = client.post(
        "/api/exercises",
        json={
            "id": "UPLOAD-RETRY-01",
            "title": "Fictional upload retry",
            "scenario": "Synthetic test of bounded upload admission recovery.",
            "exercise_date": "2026-11-03",
            "duration_minutes": 30,
            "objectives": [{"id": "O1", "text": "Restore essential service."}],
        },
    )
    assert exercise.status_code == 201
    files = {"files": ("synthetic.csv", b"timestamp,event\n09:00,synthetic event\n", "text/csv")}

    rejected = client.post("/api/exercises/UPLOAD-RETRY-01/evidence", files=files)
    assert rejected.status_code == 503
    assert rejected.headers["retry-after"] == "2"
    assert client.get("/api/exercises/UPLOAD-RETRY-01").json()["sources"] == []

    controller.release()
    accepted = client.post("/api/exercises/UPLOAD-RETRY-01/evidence", files=files)
    assert accepted.status_code == 201, accepted.text
    detail = client.get("/api/exercises/UPLOAD-RETRY-01").json()
    assert len(detail["sources"]) == 1
    assert len(detail["timeline"]) == 1


def test_multi_file_upload_is_atomic_when_later_file_is_invalid(client, monkeypatch):
    monkeypatch.setenv("DRILLLOOP_UPLOAD_SCAN_MODE", "disabled")
    exercise = client.post(
        "/api/exercises",
        json={
            "id": "UPLOAD-ATOMIC-01",
            "title": "Fictional atomic upload batch",
            "scenario": "Synthetic test of file-batch persistence boundaries.",
            "exercise_date": "2026-11-03",
            "duration_minutes": 30,
            "objectives": [{"id": "O1", "text": "Restore essential service."}],
        },
    )
    assert exercise.status_code == 201
    response = client.post(
        "/api/exercises/UPLOAD-ATOMIC-01/evidence",
        files=[
            ("files", ("first.csv", b"timestamp,event\n09:00,synthetic event\n", "text/csv")),
            ("files", ("second.csv", b"timestamp,event\n99:99,invalid timestamp\n", "text/csv")),
        ],
    )
    assert response.status_code == 400
    assert response.json()["detail"]["code"] == "INVALID_TIMESTAMP"
    assert client.get("/api/exercises/UPLOAD-ATOMIC-01").json()["sources"] == []


@pytest.mark.parametrize(
    "content",
    [b"%PDF-", b"%PDF-1.4\ntruncated synthetic content"],
)
def test_malformed_pdf_upload_returns_controlled_error(client, content):
    exercise = client.post(
        "/api/exercises",
        json={
            "id": f"PDF-{len(content)}",
            "title": "Fictional malformed PDF test",
            "scenario": "Synthetic test only",
            "exercise_date": "2026-11-03",
            "duration_minutes": 30,
            "objectives": [{"id": "O1", "text": "Synthetic objective"}],
        },
    ).json()
    response = client.post(
        f"/api/exercises/{exercise['id']}/evidence",
        files={"files": ("synthetic.pdf", content, "application/pdf")},
    )

    assert response.status_code == 400
    assert response.json()["detail"]["code"] == "MALFORMED_PDF"
    assert "Traceback" not in response.text


def test_file_size_limit_rejects_large_synthetic_upload(client):
    created = client.post(
        "/api/exercises",
        json={
            "id": "UPLOAD-LIMIT-01",
            "title": "Synthetic upload size limit",
            "scenario": "A local synthetic request-size regression test.",
            "exercise_date": "2026-11-03",
            "duration_minutes": 30,
            "objectives": [{"id": "O1", "text": "Synthetic test objective"}],
        },
    )
    assert created.status_code == 201
    response = client.post(
        "/api/exercises/UPLOAD-LIMIT-01/evidence",
        files={"files": ("synthetic.txt", b"x" * (MAX_FILE_SIZE + 1), "text/plain")},
    )

    assert response.status_code == 413
    assert response.json()["detail"]["code"] == "FILE_TOO_LARGE"
    assert "Traceback" not in response.text


def test_request_body_limit_rejects_chunked_body_without_content_length():
    response_messages = []
    body_parts = [
        {"type": "http.request", "body": b"12345678", "more_body": True},
        {"type": "http.request", "body": b"90abcdef", "more_body": False},
    ]

    async def receive():
        return body_parts.pop(0)

    async def send(message):
        response_messages.append(message)

    async def app(_scope, limited_receive, _send):
        while (await limited_receive())["more_body"]:
            pass

    middleware = RequestBodyLimitMiddleware(app, max_bytes=12)
    asyncio.run(
        middleware(
            {"type": "http", "path": "/api/test", "headers": []},
            receive,
            send,
        )
    )

    assert response_messages[0]["status"] == 413
    assert b"REQUEST_TOO_LARGE" in response_messages[1]["body"]


def test_request_body_limit_rejects_declared_oversize_before_reading():
    response_messages = []

    async def receive():
        raise AssertionError("Oversized declared request body must not be read")

    async def send(message):
        response_messages.append(message)

    async def app(_scope, _receive, _send):
        raise AssertionError("Oversized declared request must not reach the application")

    middleware = RequestBodyLimitMiddleware(app, max_bytes=12)
    asyncio.run(
        middleware(
            {"type": "http", "path": "/api/test", "headers": [(b"content-length", b"13")]},
            receive,
            send,
        )
    )

    assert response_messages[0]["status"] == 413
    assert b"REQUEST_TOO_LARGE" in response_messages[1]["body"]
