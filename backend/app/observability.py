from __future__ import annotations

import json
import logging
import re
import threading
import time
import uuid
from collections import Counter
from contextvars import ContextVar

request_id_context: ContextVar[str] = ContextVar("drillloop_request_id", default="-")
_SAFE_ID = re.compile(r"^[A-Za-z0-9._-]{1,64}$")


def request_id(value: str | None) -> str:
    if value and _SAFE_ID.fullmatch(value):
        return value
    return uuid.uuid4().hex


class JsonLogFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        entry = {
            "timestamp": self.formatTime(record, "%Y-%m-%dT%H:%M:%S%z"),
            "level": record.levelname.lower(),
            "logger": record.name,
            "message": record.getMessage(),
            "request_id": request_id_context.get(),
        }
        fields = getattr(record, "fields", None)
        if isinstance(fields, dict):
            entry.update(fields)
        return json.dumps(entry, separators=(",", ":"), ensure_ascii=True)


def configure_logging() -> None:
    root = logging.getLogger()
    if any(getattr(handler, "_drillloop_json", False) for handler in root.handlers):
        return
    handler = logging.StreamHandler()
    handler._drillloop_json = True  # type: ignore[attr-defined]
    handler.setFormatter(JsonLogFormatter())
    root.handlers[:] = [handler]
    root.setLevel(logging.INFO)


class RuntimeMetrics:
    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._http_requests: Counter[tuple[str, int]] = Counter()
        self._http_duration = 0.0
        self._http_count = 0
        self._upload_count: Counter[tuple[str, str]] = Counter()
        self._upload_duration = 0.0
        self._upload_processing_count = 0
        self._analysis_count = 0
        self._analysis_duration = 0.0
        self._parser_active = 0
        self._parser_waiting = 0
        self._parser_waiting_peak = 0
        self._parser_rejections = 0
        self._parser_queue_wait_sum = 0.0
        self._parser_queue_wait_count = 0
        self._parser_work_sum = 0.0
        self._parser_work_count = 0
        self._scan_outcomes: Counter[str] = Counter()
        self._scan_duration_sum = 0.0
        self._scan_duration_count = 0
        self._db_pool_checked_out = 0
        self._db_pool_size = 0
        self._db_pool_overflow = 0
        self._db_pool_peak_checked_out = 0

    def observe_request(self, method: str, status: int, duration: float) -> None:
        with self._lock:
            self._http_requests[(method, status)] += 1
            self._http_duration += duration
            self._http_count += 1

    def observe_upload(self, status: str, scan_status: str, duration: float) -> None:
        with self._lock:
            self._upload_count[(status, scan_status)] += 1
            self._upload_duration += duration
            self._upload_processing_count += 1

    def observe_analysis(self, duration: float) -> None:
        with self._lock:
            self._analysis_count += 1
            self._analysis_duration += duration

    def observe_parser_state(self, active: int, waiting: int) -> None:
        with self._lock:
            self._parser_active = active
            self._parser_waiting = waiting
            self._parser_waiting_peak = max(self._parser_waiting_peak, waiting)

    def observe_parser_rejection(self) -> None:
        with self._lock:
            self._parser_rejections += 1

    def observe_parser_queue_wait(self, duration: float) -> None:
        with self._lock:
            self._parser_queue_wait_sum += duration
            self._parser_queue_wait_count += 1

    def observe_parser_work(self, duration: float) -> None:
        with self._lock:
            self._parser_work_sum += duration
            self._parser_work_count += 1

    def observe_scan(self, outcome: str, duration: float) -> None:
        with self._lock:
            self._scan_outcomes[outcome] += 1
            self._scan_duration_sum += duration
            self._scan_duration_count += 1

    def observe_database_pool(self, checked_out: int, size: int, overflow: int) -> None:
        with self._lock:
            self._db_pool_checked_out = checked_out
            self._db_pool_size = size
            self._db_pool_overflow = overflow
            self._db_pool_peak_checked_out = max(self._db_pool_peak_checked_out, checked_out)

    def prometheus(self) -> str:
        with self._lock:
            lines = [
                "# HELP drillloop_http_requests_total HTTP requests by method and status.",
                "# TYPE drillloop_http_requests_total counter",
            ]
            for (method, status), count in sorted(self._http_requests.items()):
                lines.append(
                    f'drillloop_http_requests_total{{method="{method}",status="{status}"}} {count}'
                )
            lines.extend(
                [
                    "# HELP drillloop_http_request_duration_seconds_sum Total request duration.",
                    "# TYPE drillloop_http_request_duration_seconds_sum counter",
                    f"drillloop_http_request_duration_seconds_sum {self._http_duration:.6f}",
                    "# HELP drillloop_http_request_duration_seconds_count Total completed requests.",
                    "# TYPE drillloop_http_request_duration_seconds_count counter",
                    f"drillloop_http_request_duration_seconds_count {self._http_count}",
                    "# HELP drillloop_uploads_total Upload attempts by status and scan state.",
                    "# TYPE drillloop_uploads_total counter",
                ]
            )
            for (status, scan_status), count in sorted(self._upload_count.items()):
                lines.append(
                    f'drillloop_uploads_total{{status="{status}",scan_status="{scan_status}"}} {count}'
                )
            lines.extend(
                [
                    "# HELP drillloop_upload_processing_duration_seconds_sum Total parser duration.",
                    "# TYPE drillloop_upload_processing_duration_seconds_sum counter",
                    f"drillloop_upload_processing_duration_seconds_sum {self._upload_duration:.6f}",
                    "# HELP drillloop_upload_processing_duration_seconds_count Total upload processing outcomes.",
                    "# TYPE drillloop_upload_processing_duration_seconds_count counter",
                    f"drillloop_upload_processing_duration_seconds_count {self._upload_processing_count}",
                    "# HELP drillloop_analysis_runs_total Analysis runs.",
                    "# TYPE drillloop_analysis_runs_total counter",
                    f"drillloop_analysis_runs_total {self._analysis_count}",
                    "# HELP drillloop_analysis_duration_seconds_sum Total analysis duration.",
                    "# TYPE drillloop_analysis_duration_seconds_sum counter",
                    f"drillloop_analysis_duration_seconds_sum {self._analysis_duration:.6f}",
                    "# HELP drillloop_parser_active_workers Current active parser/scanner workers.",
                    "# TYPE drillloop_parser_active_workers gauge",
                    f"drillloop_parser_active_workers {self._parser_active}",
                    "# HELP drillloop_parser_waiting_jobs Current bounded admission queue depth.",
                    "# TYPE drillloop_parser_waiting_jobs gauge",
                    f"drillloop_parser_waiting_jobs {self._parser_waiting}",
                    "# HELP drillloop_parser_waiting_jobs_peak Peak bounded admission queue depth.",
                    "# TYPE drillloop_parser_waiting_jobs_peak gauge",
                    f"drillloop_parser_waiting_jobs_peak {self._parser_waiting_peak}",
                    "# HELP drillloop_parser_admission_rejections_total Capacity rejections and queue timeouts.",
                    "# TYPE drillloop_parser_admission_rejections_total counter",
                    f"drillloop_parser_admission_rejections_total {self._parser_rejections}",
                    "# HELP drillloop_parser_queue_wait_seconds_sum Total parser admission wait duration.",
                    "# TYPE drillloop_parser_queue_wait_seconds_sum counter",
                    f"drillloop_parser_queue_wait_seconds_sum {self._parser_queue_wait_sum:.6f}",
                    "# HELP drillloop_parser_queue_wait_seconds_count Parser admission waits observed.",
                    "# TYPE drillloop_parser_queue_wait_seconds_count counter",
                    f"drillloop_parser_queue_wait_seconds_count {self._parser_queue_wait_count}",
                    "# HELP drillloop_parser_processing_seconds_sum Total isolated processing duration.",
                    "# TYPE drillloop_parser_processing_seconds_sum counter",
                    f"drillloop_parser_processing_seconds_sum {self._parser_work_sum:.6f}",
                    "# HELP drillloop_parser_processing_seconds_count Isolated processing outcomes.",
                    "# TYPE drillloop_parser_processing_seconds_count counter",
                    f"drillloop_parser_processing_seconds_count {self._parser_work_count}",
                    "# HELP drillloop_scans_total Scanner outcomes.",
                    "# TYPE drillloop_scans_total counter",
                ]
            )
            for outcome, count in sorted(self._scan_outcomes.items()):
                lines.append(f'drillloop_scans_total{{outcome="{outcome}"}} {count}')
            lines.extend(
                [
                    "# HELP drillloop_scan_duration_seconds_sum Total scanner operation duration.",
                    "# TYPE drillloop_scan_duration_seconds_sum counter",
                    f"drillloop_scan_duration_seconds_sum {self._scan_duration_sum:.6f}",
                    "# HELP drillloop_scan_duration_seconds_count Scanner operations observed.",
                    "# TYPE drillloop_scan_duration_seconds_count counter",
                    f"drillloop_scan_duration_seconds_count {self._scan_duration_count}",
                    "# HELP drillloop_db_pool_checked_out Current checked-out database connections.",
                    "# TYPE drillloop_db_pool_checked_out gauge",
                    f"drillloop_db_pool_checked_out {self._db_pool_checked_out}",
                    "# HELP drillloop_db_pool_size Configured base database connection pool size.",
                    "# TYPE drillloop_db_pool_size gauge",
                    f"drillloop_db_pool_size {self._db_pool_size}",
                    "# HELP drillloop_db_pool_overflow Current database pool overflow connections.",
                    "# TYPE drillloop_db_pool_overflow gauge",
                    f"drillloop_db_pool_overflow {self._db_pool_overflow}",
                    "# HELP drillloop_db_pool_peak_checked_out Peak checked-out connections since process start.",
                    "# TYPE drillloop_db_pool_peak_checked_out gauge",
                    f"drillloop_db_pool_peak_checked_out {self._db_pool_peak_checked_out}",
                ]
            )
            return "\n".join(lines) + "\n"


METRICS = RuntimeMetrics()


class CorrelationMiddleware:
    def __init__(self, app):
        self.app = app

    async def __call__(self, scope, receive, send):
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return
        headers = {key.lower(): value.decode("latin-1") for key, value in scope.get("headers", [])}
        identifier = request_id(headers.get(b"x-request-id"))
        token = request_id_context.set(identifier)
        started = time.perf_counter()
        status = 500

        async def add_request_id(message):
            nonlocal status
            if message["type"] == "http.response.start":
                status = message["status"]
                response_headers = list(message.get("headers", []))
                response_headers.append((b"x-request-id", identifier.encode("ascii")))
                message["headers"] = response_headers
            await send(message)

        try:
            await self.app(scope, receive, add_request_id)
        finally:
            duration = time.perf_counter() - started
            method = scope.get("method", "UNKNOWN")[:16]
            METRICS.observe_request(method, status, duration)
            route = scope.get("route")
            route_path = getattr(route, "path", "unmatched")
            logging.getLogger("drillloop.http").info(
                "request_complete",
                extra={
                    "fields": {
                        "method": method,
                        "route": route_path,
                        "status": status,
                        "duration_ms": round(duration * 1000, 2),
                    }
                },
            )
            request_id_context.reset(token)
