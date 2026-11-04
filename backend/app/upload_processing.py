from __future__ import annotations

import multiprocessing
import os
import re
import shutil
import socket
import stat
import struct
import subprocess
import tempfile
import threading
import time
from collections import deque
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path

from app.evidence import EvidenceError, ParsedEvidence, parse_evidence, safe_filename
from app.observability import METRICS

MAX_ACTIVE_PARSERS = 1
MAX_WAITING_PARSERS = 8
PARSER_QUEUE_TIMEOUT_SECONDS = 30.0
_CLAMAV_EICAR = b"X5O!P%@AP[4\\PZX54(P^)7CC)7}$EICAR-STANDARD-ANTIVIRUS-TEST-FILE!$H+H*"


class UploadProcessingFailure(Exception):
    def __init__(
        self,
        code: str,
        message: str,
        status_code: int,
        *,
        retry_after_seconds: int | None = None,
        details: dict | None = None,
    ):
        self.code = code
        self.message = message
        self.status_code = status_code
        self.retry_after_seconds = retry_after_seconds
        self.details = details or {}
        super().__init__(message)


class UploadCancelled(Exception):
    """Internal signal used to stop waiting and terminate an isolated child."""


@dataclass(frozen=True)
class ScanResult:
    status: str
    engine_version: str | None = None
    signature_timestamp: str | None = None
    duration_seconds: float = 0.0


class ParserAdmissionController:
    """Fair, process-local admission with a fixed worker and waiting-job bound."""

    def __init__(self, active_limit: int, waiting_limit: int):
        if active_limit < 1 or waiting_limit < 0:
            raise ValueError("Parser limits must be positive workers and a non-negative queue.")
        self.active_limit = active_limit
        self.waiting_limit = waiting_limit
        self._condition = threading.Condition()
        self._active = 0
        self._queue: deque[object] = deque()
        self._rejections = 0

    def snapshot(self) -> tuple[int, int, int]:
        with self._condition:
            return self._active, len(self._queue), self._rejections

    def acquire(
        self,
        timeout_seconds: float,
        cancellation_event: threading.Event | None = None,
    ) -> float:
        started = time.monotonic()
        deadline = started + timeout_seconds
        ticket = object()
        with self._condition:
            if self._active < self.active_limit and not self._queue:
                self._active += 1
                METRICS.observe_parser_state(self._active, len(self._queue))
                METRICS.observe_parser_queue_wait(time.monotonic() - started)
                return time.monotonic() - started
            if len(self._queue) >= self.waiting_limit:
                self._rejections += 1
                METRICS.observe_parser_rejection()
                raise self._capacity_failure()

            self._queue.append(ticket)
            METRICS.observe_parser_state(self._active, len(self._queue))
            try:
                while True:
                    if cancellation_event is not None and cancellation_event.is_set():
                        raise UploadCancelled
                    if self._queue[0] is ticket and self._active < self.active_limit:
                        self._queue.popleft()
                        self._active += 1
                        METRICS.observe_parser_state(self._active, len(self._queue))
                        self._condition.notify_all()
                        waited = time.monotonic() - started
                        METRICS.observe_parser_queue_wait(waited)
                        return waited
                    remaining = deadline - time.monotonic()
                    if remaining <= 0:
                        self._rejections += 1
                        METRICS.observe_parser_rejection()
                        raise self._capacity_failure()
                    self._condition.wait(min(remaining, 0.1))
            finally:
                if ticket in self._queue:
                    self._queue.remove(ticket)
                    METRICS.observe_parser_state(self._active, len(self._queue))
                    self._condition.notify_all()

    def release(self) -> None:
        with self._condition:
            if self._active < 1:
                raise RuntimeError("Parser admission released without an active permit.")
            self._active -= 1
            METRICS.observe_parser_state(self._active, len(self._queue))
            self._condition.notify_all()

    @staticmethod
    def _capacity_failure() -> UploadProcessingFailure:
        return UploadProcessingFailure(
            "PARSER_CAPACITY_EXHAUSTED",
            "Evidence processing is busy; no files were imported. Wait a few seconds and retry.",
            503,
            retry_after_seconds=2,
        )


_PARSER_ADMISSION = ParserAdmissionController(MAX_ACTIVE_PARSERS, MAX_WAITING_PARSERS)


def _read_clamd_reply(connection: socket.socket, *, limit: int = 8192) -> bytes:
    response = bytearray()
    while len(response) < limit:
        block = connection.recv(min(1024, limit - len(response)))
        if not block:
            break
        response.extend(block)
        if b"\0" in block or b"\n" in block:
            break
    if len(response) >= limit and b"\0" not in response and b"\n" not in response:
        raise OSError("ClamAV reply exceeded the protocol response limit.")
    return bytes(response).rstrip(b"\0\r\n")


def _clamd_command(host: str, port: int, command: str, timeout_seconds: float) -> str:
    with socket.create_connection((host, port), timeout=timeout_seconds) as connection:
        connection.settimeout(timeout_seconds)
        connection.sendall(b"z" + command.encode("ascii") + b"\0")
        return _read_clamd_reply(connection).decode("utf-8", errors="replace")


def _clamd_stream_file(host: str, port: int, path: Path, timeout_seconds: float) -> str:
    with socket.create_connection((host, port), timeout=timeout_seconds) as connection:
        connection.settimeout(timeout_seconds)
        connection.sendall(b"zINSTREAM\0")
        with path.open("rb") as source:
            while chunk := source.read(64 * 1024):
                connection.sendall(struct.pack("!I", len(chunk)))
                connection.sendall(chunk)
        connection.sendall(struct.pack("!I", 0))
        return _read_clamd_reply(connection).decode("utf-8", errors="replace")


def _signature_timestamp(version: str) -> datetime | None:
    match = re.search(r"/(\d+)/(\w{3} \w{3}\s+\d{1,2} \d{2}:\d{2}:\d{2} \d{4})$", version)
    if not match:
        return None
    try:
        return datetime.strptime(match.group(2), "%a %b %d %H:%M:%S %Y").replace(tzinfo=UTC)
    except ValueError:
        return None


def _checked_signature_version(
    host: str, port: int, timeout_seconds: float
) -> tuple[str, datetime]:
    try:
        version = _clamd_command(host, port, "VERSION", timeout_seconds)
    except TimeoutError as exc:
        raise UploadProcessingFailure(
            "SCANNER_TIMEOUT", "Scanner signature check exceeded its time limit.", 503
        ) from exc
    except OSError as exc:
        raise UploadProcessingFailure(
            "SCANNER_UNAVAILABLE", "Required upload scanning is unavailable.", 503
        ) from exc
    signature_at = _signature_timestamp(version)
    if signature_at is None:
        raise UploadProcessingFailure(
            "SCANNER_SIGNATURES_UNKNOWN",
            "Scanner signature freshness could not be verified; the file was not imported.",
            503,
            details={"scanner_version": version[:160]},
        )
    try:
        max_age_hours = float(os.getenv("DRILLLOOP_SCANNER_MAX_SIGNATURE_AGE_HOURS", "72"))
    except ValueError as exc:
        raise UploadProcessingFailure(
            "SCANNER_CONFIGURATION_INVALID", "Scanner signature age policy is invalid.", 503
        ) from exc
    age_seconds = (datetime.now(UTC) - signature_at).total_seconds()
    if (
        not 1 <= max_age_hours <= 24 * 14
        or age_seconds < -300
        or age_seconds > max_age_hours * 3600
    ):
        raise UploadProcessingFailure(
            "SCANNER_SIGNATURES_STALE",
            "Scanner signatures are outside the configured freshness policy; the file was not imported.",
            503,
            details={
                "scanner_version": version[:160],
                "signature_timestamp": signature_at.isoformat(),
                "signature_age_hours": round(max(0, age_seconds) / 3600, 2),
                "signature_max_age_hours": max_age_hours,
            },
        )
    return version, signature_at


def _clamav_scan(raw: bytes, mode: str) -> ScanResult:
    started = time.perf_counter()
    if mode not in {"disabled", "optional", "required"}:
        raise UploadProcessingFailure(
            "SCANNER_CONFIGURATION_INVALID", "Upload scanning mode is invalid.", 503
        )
    if mode == "disabled":
        return ScanResult("not_scanned", duration_seconds=time.perf_counter() - started)

    host = os.getenv("DRILLLOOP_SCANNER_HOST", "").strip()
    try:
        if host:
            port = int(os.getenv("DRILLLOOP_SCANNER_PORT", "3310"))
            timeout = float(os.getenv("DRILLLOOP_SCANNER_TIMEOUT_SECONDS", "5"))
            if not 1 <= timeout <= 30 or not 1 <= port <= 65535:
                raise UploadProcessingFailure(
                    "SCANNER_CONFIGURATION_INVALID", "Scanner connection settings are invalid.", 503
                )
            version, signature_at = _checked_signature_version(host, port, timeout)
        else:
            version = None
            signature_at = None

        scanner = shutil.which("clamdscan") if not host else None
        if not host and scanner is None:
            if mode == "optional":
                return ScanResult("not_scanned", duration_seconds=time.perf_counter() - started)
            raise UploadProcessingFailure(
                "SCANNER_UNAVAILABLE", "Required upload scanning is unavailable.", 503
            )

        quarantine_root = os.getenv("DRILLLOOP_JOB_QUARANTINE_DIR") or os.getenv(
            "DRILLLOOP_QUARANTINE_DIR"
        )
        if quarantine_root:
            quarantine = Path(quarantine_root)
            if quarantine.is_symlink() or not quarantine.is_dir():
                raise UploadProcessingFailure(
                    "QUARANTINE_UNAVAILABLE",
                    "The restricted upload quarantine is unavailable.",
                    503,
                )
            metadata = quarantine.stat()
            if metadata.st_uid != os.geteuid() or stat.S_IMODE(metadata.st_mode) & 0o077:
                raise UploadProcessingFailure(
                    "QUARANTINE_CONFIGURATION_INVALID",
                    "The restricted upload quarantine must be owned by the application user and mode 0700 or stricter.",
                    503,
                )
        else:
            quarantine_root = None

        timeout = float(os.getenv("DRILLLOOP_SCANNER_TIMEOUT_SECONDS", "5"))
        if not 1 <= timeout <= 30:
            raise UploadProcessingFailure(
                "SCANNER_CONFIGURATION_INVALID",
                "Scanner timeout must be between 1 and 30 seconds.",
                503,
            )
        with tempfile.TemporaryDirectory(
            prefix="drillloop-scan-", dir=quarantine_root
        ) as directory:
            path = Path(directory) / "upload.bin"
            path.write_bytes(raw)
            path.chmod(0o600)
            if host:
                reply = _clamd_stream_file(host, port, path, timeout)
                if reply.endswith(" OK"):
                    return ScanResult(
                        "clean",
                        engine_version=version,
                        signature_timestamp=signature_at.isoformat() if signature_at else None,
                        duration_seconds=time.perf_counter() - started,
                    )
                if " FOUND" in reply:
                    raise UploadProcessingFailure(
                        "MALWARE_REJECTED",
                        "The scanner rejected this file; it was not imported.",
                        422,
                        details={
                            "scanner_version": version,
                            "signature_timestamp": signature_at.isoformat()
                            if signature_at
                            else None,
                            "scanner_reply": reply[:240],
                        },
                    )
                raise UploadProcessingFailure(
                    "SCANNER_FAILED",
                    "Upload scanning failed; the file was not imported.",
                    503,
                    details={"scanner_version": version, "scanner_reply": reply[:240]},
                )

            try:
                result = subprocess.run(
                    [scanner, "--no-summary", str(path)],
                    capture_output=True,
                    text=True,
                    timeout=timeout,
                    check=False,
                )
            except subprocess.TimeoutExpired as exc:
                raise UploadProcessingFailure(
                    "SCANNER_TIMEOUT",
                    "Upload scanning did not finish within the allowed time.",
                    503,
                ) from exc
            except OSError as exc:
                raise UploadProcessingFailure(
                    "SCANNER_UNAVAILABLE", "Required upload scanning is unavailable.", 503
                ) from exc

            if result.returncode == 0:
                return ScanResult("clean", duration_seconds=time.perf_counter() - started)
            if result.returncode == 1:
                raise UploadProcessingFailure(
                    "MALWARE_REJECTED", "The scanner rejected this file; it was not imported.", 422
                )
            raise UploadProcessingFailure(
                "SCANNER_FAILED", "Upload scanning failed; the file was not imported.", 503
            )
    except UploadProcessingFailure as exc:
        if exc.code.startswith("SCANNER_") or exc.code == "MALWARE_REJECTED":
            exc.details.setdefault("scan_outcome", exc.code.casefold())
            exc.details.setdefault("scan_duration_seconds", time.perf_counter() - started)
        raise
    except TimeoutError as exc:
        raise UploadProcessingFailure(
            "SCANNER_TIMEOUT",
            "Upload scanning did not finish within the allowed time.",
            503,
            details={
                "scan_outcome": "timeout",
                "scan_duration_seconds": time.perf_counter() - started,
            },
        ) from exc
    except OSError as exc:
        raise UploadProcessingFailure(
            "SCANNER_UNAVAILABLE",
            "Required upload scanning is unavailable.",
            503,
            details={
                "scan_outcome": "error",
                "scan_duration_seconds": time.perf_counter() - started,
            },
        ) from exc


def scanner_readiness() -> dict:
    """Verify clamd responsiveness, current signatures, and clean/EICAR scan behavior."""
    host = os.getenv("DRILLLOOP_SCANNER_HOST", "").strip()
    if not host:
        raise UploadProcessingFailure(
            "SCANNER_UNAVAILABLE", "Required upload scanning is not configured.", 503
        )
    try:
        port = int(os.getenv("DRILLLOOP_SCANNER_PORT", "3310"))
        timeout = float(os.getenv("DRILLLOOP_SCANNER_TIMEOUT_SECONDS", "5"))
        if not 1 <= timeout <= 30 or not 1 <= port <= 65535:
            raise ValueError
        ping = _clamd_command(host, port, "PING", timeout)
        if ping != "PONG":
            raise OSError("ClamAV did not answer PING with PONG.")
        version, signature_at = _checked_signature_version(host, port, timeout)
        clean = _clamd_stream_bytes(
            host, port, b"DrillLoop scanner readiness synthetic clean check\n", timeout
        )
        if not clean.endswith(" OK"):
            raise OSError("ClamAV did not return a clean scan verdict.")
        eicar = _clamd_stream_bytes(host, port, _CLAMAV_EICAR, timeout)
        if " FOUND" not in eicar or "eicar" not in eicar.casefold():
            raise OSError("ClamAV did not detect the EICAR readiness fixture.")
        age = max(0.0, (datetime.now(UTC) - signature_at).total_seconds() / 3600)
        return {
            "status": "ready",
            "engine_version": version[:160],
            "signature_timestamp": signature_at.isoformat(),
            "signature_age_hours": round(age, 2),
            "max_signature_age_hours": float(
                os.getenv("DRILLLOOP_SCANNER_MAX_SIGNATURE_AGE_HOURS", "72")
            ),
            "scan_capability": "clean_and_eicar_verified",
        }
    except UploadProcessingFailure:
        raise
    except (OSError, TimeoutError, ValueError) as exc:
        raise UploadProcessingFailure(
            "SCANNER_NOT_READY",
            "Required scanner readiness checks failed; evidence uploads remain unavailable.",
            503,
        ) from exc


def _clamd_stream_bytes(host: str, port: int, raw: bytes, timeout_seconds: float) -> str:
    with socket.create_connection((host, port), timeout=timeout_seconds) as connection:
        connection.settimeout(timeout_seconds)
        connection.sendall(b"zINSTREAM\0")
        for start in range(0, len(raw), 64 * 1024):
            chunk = raw[start : start + 64 * 1024]
            connection.sendall(struct.pack("!I", len(chunk)))
            connection.sendall(chunk)
        connection.sendall(struct.pack("!I", 0))
        return _read_clamd_reply(connection).decode("utf-8", errors="replace")


def _parser_worker(
    connection,
    filename: str,
    mime_type: str,
    raw: bytes,
    exercise_date: str,
    scan_mode: str,
    job_quarantine_dir: str | None,
):
    scan_result: ScanResult | None = None

    def scan_details() -> dict:
        if scan_result is None:
            return {}
        return {
            "scan_status": scan_result.status,
            "scanner_version": scan_result.engine_version,
            "signature_timestamp": scan_result.signature_timestamp,
            "scan_duration_seconds": scan_result.duration_seconds,
        }

    try:
        try:
            import resource

            memory_limit = max(256, min(int(os.getenv("DRILLLOOP_PARSER_MEMORY_MB", "768")), 768))
            resource.setrlimit(resource.RLIMIT_CPU, (10, 10))
            resource.setrlimit(resource.RLIMIT_AS, (memory_limit * 1024 * 1024,) * 2)
        except (ImportError, AttributeError, OSError, ValueError):
            pass
        if job_quarantine_dir:
            os.environ["DRILLLOOP_JOB_QUARANTINE_DIR"] = job_quarantine_dir
        scan_result = _clamav_scan(raw, scan_mode)
        parsed = parse_evidence(
            filename, mime_type, raw, datetime.fromisoformat(exercise_date).date()
        )
        connection.send(("ok", parsed, scan_result))
    except EvidenceError as exc:
        connection.send(("error", exc.code, exc.message, exc.status_code, scan_details()))
    except UploadProcessingFailure as exc:
        connection.send(
            ("error", exc.code, exc.message, exc.status_code, {**scan_details(), **exc.details})
        )
    except BaseException:
        connection.send(
            (
                "error",
                "PARSER_FAILED",
                "The file could not be processed safely.",
                422,
                scan_details(),
            )
        )
    finally:
        connection.close()


def _scan_worker(connection, raw: bytes, scan_mode: str, job_quarantine_dir: str | None):
    try:
        if job_quarantine_dir:
            os.environ["DRILLLOOP_JOB_QUARANTINE_DIR"] = job_quarantine_dir
        connection.send(("ok", _clamav_scan(raw, scan_mode)))
    except UploadProcessingFailure as exc:
        connection.send(("error", exc.code, exc.message, exc.status_code, exc.details))
    except BaseException:
        connection.send(
            (
                "error",
                "SCANNER_FAILED",
                "Upload scanning failed; the file was not imported.",
                503,
                {},
            )
        )
    finally:
        connection.close()


def _run_isolated_worker(
    target,
    args: tuple,
    timeout_seconds: float,
    cancellation_event: threading.Event | None,
    *,
    timeout_code: str,
    timeout_message: str,
    timeout_status: int,
):
    context = multiprocessing.get_context("spawn")
    parent, child = context.Pipe(duplex=True)
    worker = context.Process(target=target, args=(child, *args), daemon=True)
    try:
        worker.start()
        child.close()
        deadline = time.monotonic() + timeout_seconds
        while True:
            if cancellation_event is not None and cancellation_event.is_set():
                raise UploadCancelled
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                raise UploadProcessingFailure(timeout_code, timeout_message, timeout_status)
            if parent.poll(min(remaining, 0.1)):
                try:
                    return parent.recv()
                except EOFError as exc:
                    raise UploadProcessingFailure(
                        "PARSER_FAILED", "The file could not be processed safely.", 422
                    ) from exc
    except (OSError, EOFError) as exc:
        raise UploadProcessingFailure(
            "PARSER_FAILED", "The file could not be processed safely.", 422
        ) from exc
    finally:
        parent.close()
        child.close()
        if worker.is_alive():
            worker.terminate()
            worker.join(timeout=2)
            if worker.is_alive() and hasattr(worker, "kill"):
                worker.kill()
                worker.join(timeout=1)
        elif worker.pid is not None:
            worker.join(timeout=1)


def _queue_timeout() -> float:
    try:
        timeout = float(
            os.getenv("DRILLLOOP_PARSER_QUEUE_TIMEOUT_SECONDS", str(PARSER_QUEUE_TIMEOUT_SECONDS))
        )
    except ValueError as exc:
        raise UploadProcessingFailure(
            "PARSER_CONFIGURATION_INVALID", "Parser queue timeout must be numeric.", 503
        ) from exc
    if not 1 <= timeout <= 120:
        raise UploadProcessingFailure(
            "PARSER_CONFIGURATION_INVALID",
            "Parser queue timeout must be between 1 and 120 seconds.",
            503,
        )
    return timeout


def _make_job_quarantine() -> str:
    quarantine_root = os.getenv("DRILLLOOP_QUARANTINE_DIR")
    if quarantine_root:
        root = Path(quarantine_root)
        if root.is_symlink() or not root.is_dir():
            raise UploadProcessingFailure(
                "QUARANTINE_UNAVAILABLE", "The restricted upload quarantine is unavailable.", 503
            )
        metadata = root.stat()
        if metadata.st_uid != os.geteuid() or stat.S_IMODE(metadata.st_mode) & 0o077:
            raise UploadProcessingFailure(
                "QUARANTINE_CONFIGURATION_INVALID",
                "The restricted upload quarantine must be owned by the application user and mode 0700 or stricter.",
                503,
            )
    else:
        quarantine_root = None
    return tempfile.mkdtemp(prefix="drillloop-job-", dir=quarantine_root)


def _remove_job_quarantine(job_quarantine_dir: str | None) -> None:
    if not job_quarantine_dir:
        return
    path = Path(job_quarantine_dir)
    try:
        metadata = path.lstat()
    except FileNotFoundError:
        return
    if (
        path.is_symlink()
        or not path.is_dir()
        or metadata.st_uid != os.geteuid()
        or stat.S_IMODE(metadata.st_mode) & 0o077
    ):
        raise UploadProcessingFailure(
            "QUARANTINE_CONFIGURATION_INVALID",
            "The private upload quarantine changed ownership or permissions during processing.",
            503,
        )
    shutil.rmtree(path)


def process_upload_isolated(
    filename: str,
    mime_type: str,
    raw: bytes,
    exercise_date,
    *,
    timeout_seconds: float | None = None,
    cancellation_event: threading.Event | None = None,
) -> tuple[ParsedEvidence, ScanResult]:
    """Queue fairly within a fixed bound and parse in a disposable child process."""
    timeout = timeout_seconds or float(os.getenv("DRILLLOOP_PARSER_TIMEOUT_SECONDS", "15"))
    if timeout < 1 or timeout > 60:
        raise UploadProcessingFailure(
            "PARSER_CONFIGURATION_INVALID", "Parser timeout must be between 1 and 60 seconds.", 503
        )
    _PARSER_ADMISSION.acquire(_queue_timeout(), cancellation_event)
    started = time.perf_counter()
    job_quarantine_dir = None
    try:
        if os.getenv("DRILLLOOP_UPLOAD_SCAN_MODE", "disabled").casefold() != "disabled":
            job_quarantine_dir = _make_job_quarantine()
        result = _run_isolated_worker(
            _parser_worker,
            (
                safe_filename(filename),
                mime_type,
                raw,
                exercise_date.isoformat(),
                os.getenv("DRILLLOOP_UPLOAD_SCAN_MODE", "disabled").casefold(),
                job_quarantine_dir,
            ),
            timeout,
            cancellation_event,
            timeout_code="PARSER_TIMEOUT",
            timeout_message="Evidence processing exceeded its time limit.",
            timeout_status=422,
        )
        if result[0] == "ok":
            parsed, scan_result = result[1], result[2]
            METRICS.observe_parser_work(time.perf_counter() - started)
            METRICS.observe_scan(scan_result.status, scan_result.duration_seconds)
            return parsed, scan_result
        details = result[4] if len(result) > 4 else {}
        if details.get("scan_outcome"):
            METRICS.observe_scan(
                details["scan_outcome"], float(details.get("scan_duration_seconds", 0))
            )
        elif details.get("scan_status"):
            METRICS.observe_scan(
                details["scan_status"], float(details.get("scan_duration_seconds", 0))
            )
        raise UploadProcessingFailure(result[1], result[2], result[3], details=details)
    finally:
        try:
            _remove_job_quarantine(job_quarantine_dir)
        finally:
            _PARSER_ADMISSION.release()


def scan_bytes_isolated(
    raw: bytes,
    *,
    timeout_seconds: float = 7,
    cancellation_event: threading.Event | None = None,
) -> str:
    """Scan a non-parser upload using the same bounded admission controller."""
    _PARSER_ADMISSION.acquire(_queue_timeout(), cancellation_event)
    job_quarantine_dir = None
    try:
        if os.getenv("DRILLLOOP_UPLOAD_SCAN_MODE", "disabled").casefold() != "disabled":
            job_quarantine_dir = _make_job_quarantine()
        result = _run_isolated_worker(
            _scan_worker,
            (
                raw,
                os.getenv("DRILLLOOP_UPLOAD_SCAN_MODE", "disabled").casefold(),
                job_quarantine_dir,
            ),
            timeout_seconds,
            cancellation_event,
            timeout_code="SCANNER_TIMEOUT",
            timeout_message="Upload scanning did not finish within the allowed time.",
            timeout_status=503,
        )
        if result[0] == "ok":
            METRICS.observe_scan(result[1].status, result[1].duration_seconds)
            return result[1].status
        details = result[4] if len(result) > 4 else {}
        if details.get("scan_outcome"):
            METRICS.observe_scan(
                details["scan_outcome"], float(details.get("scan_duration_seconds", 0))
            )
        raise UploadProcessingFailure(result[1], result[2], result[3], details=details)
    finally:
        try:
            _remove_job_quarantine(job_quarantine_dir)
        finally:
            _PARSER_ADMISSION.release()
