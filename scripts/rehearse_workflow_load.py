#!/usr/bin/env python3
"""Measure bounded synthetic DrillLoop API workflows on an isolated local database."""

from __future__ import annotations

import argparse
import http.cookiejar
import json
import math
import os
import socket
import statistics
import subprocess
import sys
import threading
import time
import urllib.error
import urllib.request
import uuid
from collections import Counter
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import UTC, datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from scripts.isolated_runtime import configure  # noqa: E402

OPS = (
    "login",
    "exercise_create",
    "evidence_upload_and_extraction",
    "analysis_execution",
    "finding_retrieval",
    "finding_review",
    "action_update",
    "action_review",
    "action_close",
    "report_generation",
)
PASSWORD = "synthetic-evaluation-only-password"


class StepFailure(RuntimeError):
    pass


class LocalClient:
    def __init__(self, base_url: str):
        self.base_url = base_url
        self.cookies = http.cookiejar.CookieJar()
        self.opener = urllib.request.build_opener(urllib.request.HTTPCookieProcessor(self.cookies))
        self.csrf: str | None = None
        self.latencies: dict[str, list[float]] = {name: [] for name in OPS}
        self.statuses: Counter[str] = Counter()
        self.errors: list[dict] = []
        self.request_count = 0

    def request(
        self,
        operation: str,
        path: str,
        *,
        method: str = "GET",
        payload: dict | None = None,
        raw_body: bytes | None = None,
        content_type: str | None = None,
        expected_status: int = 200,
    ) -> tuple[dict, bytes]:
        headers = {"Host": "127.0.0.1"}
        body = raw_body
        if payload is not None:
            body = json.dumps(payload).encode("utf-8")
            content_type = "application/json"
        if content_type:
            headers["Content-Type"] = content_type
        if method not in {"GET", "HEAD", "OPTIONS", "POST_LOGIN"} and self.csrf:
            headers["X-CSRF-Token"] = self.csrf
        actual_method = "POST" if method == "POST_LOGIN" else method
        request = urllib.request.Request(
            self.base_url + path, data=body, headers=headers, method=actual_method
        )
        started = time.perf_counter()
        try:
            response = self.opener.open(request, timeout=15)
        except urllib.error.HTTPError as error:
            response = error
        except (urllib.error.URLError, TimeoutError, OSError) as error:
            elapsed = (time.perf_counter() - started) * 1000
            self.latencies[operation].append(elapsed)
            self.request_count += 1
            self.statuses["connection_error"] += 1
            self.errors.append({"operation": operation, "error": type(error).__name__})
            raise StepFailure(f"{operation}: {type(error).__name__}") from error
        elapsed = (time.perf_counter() - started) * 1000
        self.latencies[operation].append(elapsed)
        self.request_count += 1
        self.statuses[str(response.status)] += 1
        response_body = response.read()
        try:
            data = (
                json.loads(response_body)
                if response_body and "json" in response.headers.get("Content-Type", "")
                else {}
            )
        except json.JSONDecodeError:
            data = {}
        if response.status != expected_status:
            self.errors.append(
                {"operation": operation, "status": response.status, "expected": expected_status}
            )
            raise StepFailure(
                f"{operation}: expected HTTP {expected_status}, got {response.status}"
            )
        return data, response_body

    def workflow(self, ordinal: int) -> dict:
        exercise_id = f"LOAD-{uuid.uuid4().hex[:16]}-{ordinal}"
        self.request(
            "login",
            "/api/auth/login",
            method="POST_LOGIN",
            payload={"username": "evaluation-admin", "password": PASSWORD},
            expected_status=200,
        )
        session_data, _ = self.request("login", "/api/auth/session", expected_status=200)
        self.csrf = session_data["csrf_token"]
        self.request(
            "exercise_create",
            "/api/exercises",
            method="POST",
            payload={
                "id": exercise_id,
                "title": f"Synthetic bounded-load workflow {ordinal}",
                "scenario": "A wholly fictional response exercise for local application workflow measurement.",
                "exercise_date": "2026-11-04",
                "duration_minutes": 45,
                "objectives": [
                    {
                        "id": "LOAD-OBJ-01",
                        "text": "Restore the fictional service within one minute.",
                        "evaluation_rule": {
                            "type": "elapsed_time",
                            "threshold_seconds": 60,
                            "start_terms": ["synthetic pump failed"],
                            "completion_terms": ["synthetic pump restored"],
                            "finding_code": "SYNTHETIC_PUMP_DELAY",
                        },
                    }
                ],
            },
            expected_status=201,
        )
        boundary = f"drillloop-{uuid.uuid4().hex}"
        csv = (
            b"event_id,timestamp,event\n"
            b"SYN-01,14:00,Synthetic pump failed at the control point.\n"
            b"SYN-02,14:02,Synthetic pump restored and checked.\n"
        )
        multipart = (
            (
                f'--{boundary}\r\nContent-Disposition: form-data; name="files"; filename="{exercise_id}.csv"\r\n'
                "Content-Type: text/csv\r\n\r\n"
            ).encode()
            + csv
            + f"\r\n--{boundary}--\r\n".encode()
        )
        self.request(
            "evidence_upload_and_extraction",
            f"/api/exercises/{exercise_id}/evidence",
            method="POST",
            raw_body=multipart,
            content_type=f"multipart/form-data; boundary={boundary}",
            expected_status=201,
        )
        self.request(
            "analysis_execution",
            f"/api/exercises/{exercise_id}/analyze",
            method="POST",
            expected_status=200,
        )
        detail, _ = self.request(
            "finding_retrieval", f"/api/exercises/{exercise_id}", expected_status=200
        )
        if not detail.get("findings") or not detail.get("actions"):
            raise StepFailure("Analysis did not produce the expected synthetic finding and action.")
        finding = detail["findings"][0]
        action = detail["actions"][0]
        self.request(
            "finding_review",
            f"/api/findings/{finding['id']}/review",
            method="POST",
            payload={"decision": "approved", "note": "Synthetic bounded-load reviewer decision."},
            expected_status=200,
        )
        self.request(
            "action_update",
            f"/api/actions/{action['id']}",
            method="PUT",
            payload={
                "title": "Run the synthetic timed recovery exercise.",
                "owner": "Synthetic Response Team",
                "priority": "medium",
                "due_date": "2026-12-01",
                "acceptance_criteria": "A synthetic timed retest documents restoration within the objective.",
            },
            expected_status=200,
        )
        self.request(
            "action_review",
            f"/api/actions/{action['id']}/review",
            method="POST",
            payload={"decision": "approved"},
            expected_status=200,
        )
        self.request(
            "action_close",
            f"/api/actions/{action['id']}/close",
            method="POST",
            payload={"closure_evidence": "Synthetic local load-test closure evidence."},
            expected_status=200,
        )
        report_request = urllib.request.Request(
            self.base_url + f"/api/exercises/{exercise_id}/report.pdf",
            headers={"Host": "127.0.0.1"},
        )
        started = time.perf_counter()
        try:
            report_response = self.opener.open(report_request, timeout=15)
        except urllib.error.HTTPError as error:
            report_response = error
        report_body = report_response.read()
        elapsed = (time.perf_counter() - started) * 1000
        self.latencies["report_generation"].append(elapsed)
        self.request_count += 1
        self.statuses[str(report_response.status)] += 1
        if report_response.status != 200 or not report_body.startswith(b"%PDF"):
            self.errors.append({"operation": "report_generation", "status": report_response.status})
            raise StepFailure("PDF report generation failed.")
        return {"exercise_id": exercise_id}


def percentile(values: list[float], probability: float) -> float:
    ordered = sorted(values)
    index = max(0, math.ceil(probability * len(ordered)) - 1)
    return ordered[index]


def summarize(values: list[float]) -> dict:
    return {
        "samples": len(values),
        "p50_ms": round(statistics.median(values), 2) if values else None,
        "p95_ms": round(percentile(values, 0.95), 2) if len(values) >= 20 else None,
        "p99_ms": round(percentile(values, 0.99), 2) if len(values) >= 100 else None,
        "max_ms": round(max(values), 2) if values else None,
    }


def process_snapshot(root_pid: int) -> tuple[float, float]:
    result = subprocess.run(
        ["ps", "-axo", "pid=,ppid=,rss=,%cpu="], capture_output=True, text=True, check=False
    )
    rows = []
    for line in result.stdout.splitlines():
        fields = line.split()
        if len(fields) != 4:
            continue
        try:
            rows.append((int(fields[0]), int(fields[1]), int(fields[2]), float(fields[3])))
        except ValueError:
            continue
    selected = {root_pid}
    changed = True
    while changed:
        changed = False
        for pid, parent, _rss, _cpu in rows:
            if parent in selected and pid not in selected:
                selected.add(pid)
                changed = True
    processes = [row for row in rows if row[0] in selected]
    return (
        sum(row[2] for row in processes) / 1024,
        sum(row[3] for row in processes),
    )


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--workflows-per-level", type=int, default=20)
    parser.add_argument("--max-concurrency", type=int, choices=(1, 2, 4), default=4)
    args = parser.parse_args()
    if not 5 <= args.workflows_per_level <= 25:
        raise SystemExit("Bounded limits are 5–25 workflows per concurrency level.")

    owned_root = configure()
    import os as runtime_os

    from app import db as database

    runtime_os.environ["DRILLLOOP_BUILD_VERSION"] = "phase4-workflow-load"
    runtime_os.environ["DRILLLOOP_BUILD_REVISION"] = "synthetic-disposable"
    database.migrate_database()
    with socket.socket() as probe:
        probe.bind(("127.0.0.1", 0))
        port = probe.getsockname()[1]
    log_path = owned_root / "api.log"
    log_stream = log_path.open("w", encoding="utf-8")
    api_environment = os.environ.copy()
    api_environment.pop("DRILLLOOP_TEST_MODE", None)
    api = subprocess.Popen(
        [
            sys.executable,
            "-m",
            "uvicorn",
            "app.main:app",
            "--app-dir",
            "backend",
            "--host",
            "127.0.0.1",
            "--port",
            str(port),
            "--no-access-log",
        ],
        cwd=ROOT,
        env=api_environment,
        stdout=log_stream,
        stderr=subprocess.STDOUT,
    )
    origin = f"http://127.0.0.1:{port}"
    deadline = time.monotonic() + 45
    while time.monotonic() < deadline:
        if api.poll() is not None:
            raise RuntimeError(
                "Disposable API exited before load test: " + log_path.read_text()[-2000:]
            )
        try:
            with urllib.request.urlopen(origin + "/api/ready", timeout=2) as response:
                if response.status == 200:
                    break
        except (urllib.error.URLError, TimeoutError):
            time.sleep(0.25)
    else:
        api.terminate()
        raise RuntimeError("Disposable API did not become ready within 45 seconds.")

    samples: dict[str, list[float]] = {name: [] for name in OPS}
    level_results = []
    workflow_total = 0
    request_total = 0
    error_records = []
    status_counts: Counter[str] = Counter()
    memory_samples: list[float] = []
    cpu_samples: list[float] = []
    stop_sampling = threading.Event()

    def sample_resources() -> None:
        while not stop_sampling.wait(0.1):
            memory, cpu = process_snapshot(api.pid)
            memory_samples.append(memory)
            cpu_samples.append(cpu)

    resource_thread = threading.Thread(target=sample_resources, daemon=True)
    resource_thread.start()
    levels = [1, 2, 4]
    if args.max_concurrency < 4:
        levels = [level for level in levels if level <= args.max_concurrency]
    try:
        for concurrency in levels:
            clients: list[LocalClient] = []
            completed = 0
            level_start = time.perf_counter()
            with ThreadPoolExecutor(max_workers=concurrency) as pool:
                futures = {}
                for index in range(args.workflows_per_level):
                    client = LocalClient(origin)
                    clients.append(client)
                    futures[pool.submit(client.workflow, workflow_total + index + 1)] = client
                for future in as_completed(futures):
                    try:
                        future.result()
                        completed += 1
                    except Exception as error:
                        # HTTP failures are already recorded by LocalClient. Keep a
                        # workflow-level diagnostic only for failures that did not
                        # originate in a request, so one failed upload is counted once.
                        client = futures[future]
                        if not client.errors:
                            error_records.append({"concurrency": concurrency, "error": str(error)})
            elapsed = time.perf_counter() - level_start
            for client in clients:
                for name in OPS:
                    samples[name].extend(client.latencies[name])
                request_total += client.request_count
                status_counts.update(client.statuses)
                error_records.extend({"concurrency": concurrency, **item} for item in client.errors)
            workflow_total += args.workflows_per_level
            level_results.append(
                {
                    "concurrency": concurrency,
                    "workflows_attempted": args.workflows_per_level,
                    "workflows_completed": completed,
                    "elapsed_seconds": round(elapsed, 3),
                    "workflows_per_second": round(completed / elapsed, 3) if elapsed else None,
                    "requests_per_second": round(
                        sum(client.request_count for client in clients) / elapsed, 3
                    )
                    if elapsed
                    else None,
                }
            )
        metrics_client = LocalClient(origin)
        metrics_client.request(
            "login",
            "/api/auth/login",
            method="POST_LOGIN",
            payload={"username": "evaluation-admin", "password": PASSWORD},
        )
        session, _ = metrics_client.request("login", "/api/auth/session")
        metrics_client.csrf = session["csrf_token"]
        _data, metrics_body = metrics_client.request("login", "/api/metrics")
        metrics_text = metrics_body.decode("utf-8", errors="replace")
    finally:
        stop_sampling.set()
        resource_thread.join(timeout=2)
        api.terminate()
        try:
            api.wait(timeout=15)
        except subprocess.TimeoutExpired:
            api.kill()
            api.wait(timeout=5)
        log_stream.close()

    def gauge(name: str) -> float | None:
        for line in metrics_text.splitlines():
            if line.startswith(name + " "):
                try:
                    return float(line.split()[-1])
                except ValueError:
                    return None
        return None

    report = {
        "schema_version": "drillloop-workflow-load-result/v1",
        "created_at_utc": datetime.now(UTC).isoformat(),
        "fictional_only": True,
        "target": "disposable local FastAPI process and isolated SQLite file",
        "database_file_bytes": (
            owned_root / Path(os.environ["DATABASE_URL"].replace("sqlite:///", "")).name
        )
        .stat()
        .st_size
        if (owned_root / Path(os.environ["DATABASE_URL"].replace("sqlite:///", "")).name).exists()
        else None,
        "concurrency_matrix": level_results,
        "operation_latency": {name: summarize(values) for name, values in samples.items()},
        "total_workflow_attempts": workflow_total,
        "total_api_requests": request_total,
        "http_status_counts": dict(status_counts),
        "error_count": len(error_records),
        "errors": error_records[:30],
        "workflow_throughput_bottleneck_note": "Upload includes scanner adapter and isolated parse worker; this local rehearsal uses scan mode disabled in test configuration and does not measure an approved scanner service.",
        "resources": {
            "api_process_tree_sampled_peak_rss_mib": round(max(memory_samples), 2)
            if memory_samples
            else None,
            "api_process_tree_sampled_peak_cpu_percent": round(max(cpu_samples), 2)
            if cpu_samples
            else None,
            "samples": len(memory_samples),
            "sample_interval_ms": 100,
            "cpu_count": os.cpu_count(),
        },
        "database_pool": {
            "configured_base_size": gauge("drillloop_db_pool_size"),
            "checked_out_at_final_sample": gauge("drillloop_db_pool_checked_out"),
            "current_overflow_at_final_sample": gauge("drillloop_db_pool_overflow"),
            "peak_checked_out_observed_by_middleware": gauge("drillloop_db_pool_peak_checked_out"),
            "engine": "SQLite file-backed test database; PostgreSQL connection capacity is not inferred.",
        },
        "latency_percentiles": "p95 shown with at least 20 samples per operation; p99 shown only with at least 100 samples. No production service-level targets were supplied.",
        "limitations": [
            "All data is synthetic and the database is a disposable local SQLite file.",
            "This result is a bounded workflow measurement on one developer machine, not production capacity or service-level acceptance.",
            "The test does not include Nginx/TLS, a production scanner, PostgreSQL, external identity, or external integrations.",
        ],
    }
    print(json.dumps(report, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
