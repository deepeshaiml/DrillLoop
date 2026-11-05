#!/usr/bin/env python3
"""Measure full synthetic workflows against a local PostgreSQL + required ClamAV stack."""

from __future__ import annotations

import argparse
import http.cookiejar
import json
import math
import os
import re
import ssl
import statistics
import subprocess
import threading
import time
import urllib.error
import urllib.parse
import urllib.request
import uuid
from collections import Counter
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import UTC, datetime

OPS = (
    "login",
    "exercise_create",
    "evidence_upload_scan_extract",
    "analysis",
    "analysis_idempotent_recheck",
    "finding_review",
    "action_update",
    "action_review",
    "action_close",
    "pdf_export",
)


class StepFailure(RuntimeError):
    pass


def percentile(values: list[float], probability: float) -> float | None:
    if not values:
        return None
    ordered = sorted(values)
    return round(ordered[max(0, math.ceil(probability * len(ordered)) - 1)], 2)


def summarize(values: list[float]) -> dict:
    return {
        "samples": len(values),
        "p50_ms": round(statistics.median(values), 2) if values else None,
        "p95_ms": percentile(values, 0.95) if len(values) >= 20 else None,
        "max_ms": round(max(values), 2) if values else None,
    }


class LocalClient:
    def __init__(self, base_url: str):
        self.base_url = base_url.rstrip("/")
        handlers = [urllib.request.HTTPCookieProcessor(http.cookiejar.CookieJar())]
        if self.base_url.startswith("https://"):
            handlers.insert(
                0, urllib.request.HTTPSHandler(context=ssl._create_unverified_context())
            )
        self.opener = urllib.request.build_opener(*handlers)
        self.csrf: str | None = None
        self.latencies: dict[str, list[float]] = {name: [] for name in OPS}
        self.statuses: Counter[str] = Counter()
        self.errors: list[dict] = []
        self.capacity_rejections = 0
        self.uploads_accepted = 0
        self.uploads_other_rejected = 0
        self.upload_retries = 0
        self.edge_rate_limit_rejections = 0
        self.edge_rate_limit_retries = 0
        self.unexpected_http_5xx = 0

    def request(
        self,
        operation: str,
        path: str,
        *,
        method: str = "GET",
        payload: dict | None = None,
        raw_body: bytes | None = None,
        content_type: str | None = None,
        expected_status: int | None = 200,
        timeout_seconds: float = 30,
    ) -> tuple[int, dict, bytes, object, float]:
        headers = {"Host": "127.0.0.1"}
        body = raw_body
        if payload is not None:
            body = json.dumps(payload).encode()
            content_type = "application/json"
        if content_type:
            headers["Content-Type"] = content_type
        if method not in {"GET", "HEAD", "OPTIONS"} and self.csrf:
            headers["X-CSRF-Token"] = self.csrf
        started = time.perf_counter()
        max_rate_limit_attempts = 8
        for attempt in range(max_rate_limit_attempts):
            request = urllib.request.Request(
                self.base_url + path, data=body, headers=headers, method=method
            )
            try:
                response = self.opener.open(request, timeout=timeout_seconds)
            except urllib.error.HTTPError as error:
                response = error
            except (urllib.error.URLError, TimeoutError, OSError) as error:
                self.statuses["connection_error"] += 1
                raise StepFailure(f"{operation}: {type(error).__name__}") from error
            self.statuses[str(response.status)] += 1
            if response.status == 429 and response.headers.get("Retry-After"):
                self.edge_rate_limit_rejections += 1
                if attempt + 1 < max_rate_limit_attempts:
                    try:
                        delay = max(1, min(5, int(response.headers["Retry-After"])))
                    except ValueError:
                        delay = 2
                    response.read()
                    self.edge_rate_limit_retries += 1
                    time.sleep(delay)
                    continue
            break
        duration = (time.perf_counter() - started) * 1000
        self.latencies[operation].append(duration)
        response_body = response.read()
        try:
            data = (
                json.loads(response_body)
                if response_body and "json" in response.headers.get("Content-Type", "")
                else {}
            )
        except json.JSONDecodeError:
            data = {}
        if response.status >= 500 and not (
            response.status == 503
            and data.get("detail", {}).get("code") == "PARSER_CAPACITY_EXHAUSTED"
        ):
            self.unexpected_http_5xx += 1
        if expected_status is not None and response.status != expected_status:
            self.errors.append(
                {
                    "operation": operation,
                    "status": response.status,
                    "expected": expected_status,
                    "code": data.get("detail", {}).get("code"),
                }
            )
            raise StepFailure(
                f"{operation}: expected HTTP {expected_status}, got {response.status}"
            )
        return response.status, data, response_body, response.headers, duration

    def workflow(self, ordinal: int) -> dict:
        suffix = f"{uuid.uuid4().hex[:14]}-{ordinal}"
        exercise_id = f"PH5-LOAD-{suffix}"
        self.request(
            "login",
            "/api/auth/login",
            method="POST",
            payload={
                "username": os.environ["DRILLLOOP_LOAD_USERNAME"],
                "password": os.environ["DRILLLOOP_LOAD_PASSWORD"],
            },
        )
        _status, session, _body, _headers, _latency = self.request("login", "/api/auth/session")
        self.csrf = session["csrf_token"]

        self.request(
            "exercise_create",
            "/api/exercises",
            method="POST",
            payload={
                "id": exercise_id,
                "title": f"Fictional Phase 5 load workflow {suffix}",
                "scenario": "Wholly synthetic independent workflow used for local load measurement.",
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
            b"SYN-01,14:00,Synthetic pump failed at the fictional control point.\n"
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
        upload_path = f"/api/exercises/{exercise_id}/evidence"
        upload_status = None
        upload_data = {}
        upload_headers = {}
        for attempt in range(3):
            (
                upload_status,
                upload_data,
                _upload_body,
                upload_headers,
                _upload_latency,
            ) = self.request(
                "evidence_upload_scan_extract",
                upload_path,
                method="POST",
                raw_body=multipart,
                content_type=f"multipart/form-data; boundary={boundary}",
                expected_status=None,
            )
            if (
                upload_status == 503
                and upload_data.get("detail", {}).get("code") == "PARSER_CAPACITY_EXHAUSTED"
            ):
                self.capacity_rejections += 1
                if attempt == 2:
                    break
                self.upload_retries += 1
                try:
                    wait_seconds = max(1, min(5, int(upload_headers.get("Retry-After", "2"))))
                except ValueError:
                    wait_seconds = 2
                time.sleep(wait_seconds)
                continue
            if upload_status == 201:
                self.uploads_accepted += 1
            else:
                self.uploads_other_rejected += 1
            break
        if upload_status != 201:
            raise StepFailure(
                f"evidence upload: HTTP {upload_status}; "
                f"{upload_data.get('detail', {}).get('code', 'unknown error')}"
            )

        _status, detail, _body, _headers, _latency = self.request(
            "analysis", f"/api/exercises/{exercise_id}"
        )
        sources = detail.get("sources", [])
        if len(sources) != 1 or sources[0].get("scan_status") != "clean":
            raise StepFailure("Upload did not produce exactly one clean-scanned source.")
        if len(detail.get("timeline", [])) != 2:
            raise StepFailure("Synthetic CSV extraction did not produce two observations.")

        first_analysis = self.request(
            "analysis", f"/api/exercises/{exercise_id}/analyze", method="POST"
        )[1]
        second_analysis = self.request(
            "analysis_idempotent_recheck",
            f"/api/exercises/{exercise_id}/analyze",
            method="POST",
        )[1]
        _status, detail, _body, _headers, _latency = self.request(
            "analysis", f"/api/exercises/{exercise_id}"
        )
        findings = detail.get("findings", [])
        actions = detail.get("actions", [])
        if len(findings) != 1 or len(actions) != 1:
            raise StepFailure(
                f"Analysis retry created duplicate or missing records: {len(findings)} findings, {len(actions)} actions."
            )
        finding = findings[0]
        if not finding.get("evidence_ids") or not finding.get("supporting_evidence"):
            raise StepFailure("Synthetic finding did not retain source citations.")
        if first_analysis.get("candidate_count") != second_analysis.get("candidate_count"):
            raise StepFailure("Repeating analysis changed the number of proposed findings.")
        action = actions[0]
        self.request(
            "finding_review",
            f"/api/findings/{finding['id']}/review",
            method="POST",
            payload={"decision": "approved", "note": "Synthetic load rehearsal reviewer decision."},
        )
        self.request(
            "action_update",
            f"/api/actions/{action['id']}",
            method="PUT",
            payload={
                "title": "Rehearse the synthetic timed recovery workflow.",
                "owner": "Synthetic Response Team",
                "priority": "medium",
                "due_date": "2026-12-01",
                "acceptance_criteria": "A fictional retest records restoration within the objective.",
            },
        )
        self.request(
            "action_review",
            f"/api/actions/{action['id']}/review",
            method="POST",
            payload={"decision": "approved"},
        )
        self.request(
            "action_close",
            f"/api/actions/{action['id']}/close",
            method="POST",
            payload={"closure_evidence": "Synthetic local load-test closure evidence."},
        )
        _status, _data, pdf, _headers, _latency = self.request(
            "pdf_export", f"/api/exercises/{exercise_id}/report.pdf"
        )
        if not pdf.startswith(b"%PDF"):
            raise StepFailure("PDF export did not return a valid PDF signature.")
        return {"exercise_id": exercise_id, "finding_id": finding["id"], "action_id": action["id"]}


def docker_stats(project: str) -> list[dict]:
    containers = subprocess.run(
        [
            "docker",
            "ps",
            "-q",
            "--filter",
            f"label=com.docker.compose.project={project}",
        ],
        capture_output=True,
        text=True,
        check=False,
    )
    ids = containers.stdout.split()
    if containers.returncode or not ids:
        return []
    result = subprocess.run(
        [
            "docker",
            "stats",
            "--no-stream",
            "--format",
            "{{.Name}}\t{{.CPUPerc}}\t{{.MemUsage}}",
            *ids,
        ],
        capture_output=True,
        text=True,
        check=False,
    )
    if result.returncode:
        return []
    snapshots = []
    for row in result.stdout.splitlines():
        name, cpu, memory = (row.split("\t", 2) + ["", "", ""])[:3]
        try:
            cpu_percent = float(cpu.strip().rstrip("%"))
        except ValueError:
            cpu_percent = None
        match = re.match(r"\s*([\d.]+)\s*(B|KiB|MiB|GiB|KB|MB|GB)", memory)
        memory_mib = None
        if match:
            quantity = float(match.group(1))
            unit = match.group(2)
            factor = {
                "B": 1 / 1024**2,
                "KiB": 1 / 1024,
                "MiB": 1,
                "GiB": 1024,
                "KB": 1000 / 1024**2,
                "MB": 1000**2 / 1024**2,
                "GB": 1000**3 / 1024**2,
            }[unit]
            memory_mib = round(quantity * factor, 1)
        snapshots.append({"container": name, "cpu_percent": cpu_percent, "memory_mib": memory_mib})
    return snapshots


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--base-url", required=True)
    parser.add_argument("--compose-project", required=True)
    parser.add_argument("--workflows-per-level", type=int, default=20)
    parser.add_argument("--max-concurrency", type=int, choices=(1, 2, 5, 10), default=10)
    args = parser.parse_args()
    if not 5 <= args.workflows_per_level <= 25:
        raise SystemExit("Use 5–25 workflows per concurrency level.")
    if not os.getenv("DRILLLOOP_LOAD_USERNAME") or not os.getenv("DRILLLOOP_LOAD_PASSWORD"):
        raise SystemExit(
            "Provide a disposable local identity through DRILLLOOP_LOAD_USERNAME/PASSWORD."
        )

    target = urllib.parse.urlparse(args.base_url)
    if (
        target.scheme not in {"http", "https"}
        or target.hostname not in {"127.0.0.1", "localhost", "::1"}
        or target.path not in {"", "/"}
        or target.query
        or target.username
        or target.password
    ):
        raise SystemExit("The rehearsal accepts only a loopback HTTP(S) origin.")
    url = args.base_url.rstrip("/") + "/api/ready"
    probe = urllib.request.Request(url, headers={"Host": "127.0.0.1"})
    try:
        opener = (
            urllib.request.build_opener(
                urllib.request.HTTPSHandler(context=ssl._create_unverified_context())
            )
            if target.scheme == "https"
            else urllib.request.build_opener()
        )
        with opener.open(probe, timeout=10) as response:
            readiness = json.loads(response.read())
    except Exception as exc:
        raise SystemExit(
            f"Loopback app readiness could not be verified: {type(exc).__name__}"
        ) from exc
    scanner = readiness.get("scanner") or {}
    if (
        readiness.get("status") != "ready"
        or scanner.get("scan_capability") != "clean_and_eicar_verified"
    ):
        raise SystemExit("App readiness does not confirm a functioning, fresh ClamAV scanner.")

    failures: list[dict] = []
    all_ids: set[str] = set()
    samples: dict[int, dict[str, list[float]]] = {}
    level_reports = []
    status_counts: Counter[str] = Counter()
    upload_accepted = 0
    upload_other_rejected = 0
    capacity_rejections = 0
    upload_retries = 0
    edge_rate_limit_rejections = 0
    edge_rate_limit_retries = 0
    unexpected_http_5xx = 0
    container_samples: dict[str, list[dict]] = {}
    stop_sampling = threading.Event()
    sampler_error: list[str] = []

    def sample_resources() -> None:
        while not stop_sampling.wait(0.5):
            rows = docker_stats(args.compose_project)
            if not rows:
                sampler_error.append("docker stats was unavailable during sampling")
            for row in rows:
                container_samples.setdefault(row["container"], []).append(row)

    resource_thread = threading.Thread(target=sample_resources, daemon=True)
    resource_thread.start()
    levels = [1, 2, 5, 10]
    levels = [value for value in levels if value <= args.max_concurrency]
    global_ordinal = 0
    try:
        for concurrency in levels:
            level_samples: dict[str, list[float]] = {name: [] for name in OPS}
            clients: list[LocalClient] = []
            completed = 0
            elapsed_started = time.perf_counter()
            with ThreadPoolExecutor(max_workers=concurrency) as pool:
                futures = {}
                for index in range(args.workflows_per_level):
                    global_ordinal += 1
                    client = LocalClient(args.base_url)
                    clients.append(client)
                    futures[pool.submit(client.workflow, global_ordinal)] = client
                for future in as_completed(futures):
                    try:
                        result = future.result()
                        if result["exercise_id"] in all_ids:
                            raise StepFailure("Duplicate exercise identifier.")
                        all_ids.add(result["exercise_id"])
                        completed += 1
                    except Exception as error:
                        client = futures[future]
                        failures.append(
                            {
                                "concurrency": concurrency,
                                "error": str(error),
                                "statuses": dict(client.statuses),
                            }
                        )
            elapsed = time.perf_counter() - elapsed_started
            for client in clients:
                for operation in OPS:
                    level_samples[operation].extend(client.latencies[operation])
                status_counts.update(client.statuses)
                upload_accepted += client.uploads_accepted
                upload_other_rejected += client.uploads_other_rejected
                capacity_rejections += client.capacity_rejections
                upload_retries += client.upload_retries
                edge_rate_limit_rejections += client.edge_rate_limit_rejections
                edge_rate_limit_retries += client.edge_rate_limit_retries
                unexpected_http_5xx += client.unexpected_http_5xx
            samples[concurrency] = level_samples
            level_reports.append(
                {
                    "concurrency": concurrency,
                    "workflows_attempted": args.workflows_per_level,
                    "workflows_completed": completed,
                    "workflow_completion_rate": round(completed / args.workflows_per_level, 4),
                    "elapsed_seconds": round(elapsed, 3),
                    "workflow_throughput_per_second": round(completed / elapsed, 3)
                    if elapsed
                    else None,
                    "operation_latency": {
                        operation: summarize(values) for operation, values in level_samples.items()
                    },
                    "overload_rejections_retryable": sum(
                        1
                        for item in failures
                        if item["concurrency"] == concurrency
                        and "PARSER_CAPACITY_EXHAUSTED" in item["error"]
                    ),
                }
            )
    finally:
        stop_sampling.set()
        resource_thread.join(timeout=5)

    metrics_client = LocalClient(args.base_url)
    metrics_client.request(
        "login",
        "/api/auth/login",
        method="POST",
        payload={
            "username": os.environ["DRILLLOOP_LOAD_USERNAME"],
            "password": os.environ["DRILLLOOP_LOAD_PASSWORD"],
        },
    )
    _status, session, _body, _headers, _latency = metrics_client.request(
        "login", "/api/auth/session"
    )
    metrics_client.csrf = session["csrf_token"]
    _status, _data, metrics_body, _headers, _latency = metrics_client.request(
        "login", "/api/metrics"
    )
    metrics_text = metrics_body.decode("utf-8", errors="replace")

    def metric_value(name: str) -> float | None:
        for line in metrics_text.splitlines():
            if line.startswith(name + " "):
                try:
                    return float(line.split()[-1])
                except ValueError:
                    return None
        return None

    memory_by_container = {}
    cpu_by_container = {}
    for name, rows in container_samples.items():
        memory_values = [row["memory_mib"] for row in rows if row["memory_mib"] is not None]
        cpu_values = [row["cpu_percent"] for row in rows if row["cpu_percent"] is not None]
        memory_by_container[name] = {
            "samples": len(memory_values),
            "peak_mib": round(max(memory_values), 1) if memory_values else None,
        }
        cpu_by_container[name] = {
            "samples": len(cpu_values),
            "peak_percent": round(max(cpu_values), 1) if cpu_values else None,
        }
    total_attempted = len(level_reports) * args.workflows_per_level
    total_completed = sum(row["workflows_completed"] for row in level_reports)
    report = {
        "schema_version": "drillloop-phase5-load-result/v1",
        "created_at_utc": datetime.now(UTC).isoformat(),
        "fictional_only": True,
        "target": args.base_url,
        "database_and_scanner": "Disposable PostgreSQL 18 + actual ClamAV Compose profile; readiness required fresh signatures and clean/EICAR scan capability.",
        "sample_size_per_concurrency": args.workflows_per_level,
        "concurrency_matrix": level_reports,
        "total_workflows": {
            "attempted": total_attempted,
            "completed": total_completed,
            "completion_rate": round(total_completed / total_attempted, 4)
            if total_attempted
            else None,
            "unique_exercises_created": len(all_ids),
        },
        "upload_outcomes": {
            "accepted_clean": upload_accepted,
            "safe_capacity_503_rejections": capacity_rejections,
            "safe_capacity_retries": upload_retries,
            "other_rejections": upload_other_rejected,
        },
        "edge_rate_limit": {
            "bounded_429_rejections": edge_rate_limit_rejections,
            "safe_retry_after_retries": edge_rate_limit_retries,
            "retry_policy": "At most eight attempts per request, only for 429 responses carrying the private-ingress Retry-After header; the edge rejects before forwarding the request.",
        },
        "http_status_counts": dict(status_counts),
        "unexpected_http_5xx": unexpected_http_5xx,
        "parser_queue": {
            "configured_active_workers": 1,
            "configured_max_waiting": 8,
            "peak_waiting_jobs": metric_value("drillloop_parser_waiting_jobs_peak"),
            "queue_wait_count": metric_value("drillloop_parser_queue_wait_seconds_count"),
            "queue_wait_sum_seconds": metric_value("drillloop_parser_queue_wait_seconds_sum"),
            "queue_wait_average_seconds": (
                round(
                    metric_value("drillloop_parser_queue_wait_seconds_sum")
                    / metric_value("drillloop_parser_queue_wait_seconds_count"),
                    6,
                )
                if metric_value("drillloop_parser_queue_wait_seconds_count")
                else None
            ),
            "admission_rejections_total": metric_value(
                "drillloop_parser_admission_rejections_total"
            ),
        },
        "scanner_metrics": {
            "outcomes": [
                line
                for line in metrics_text.splitlines()
                if line.startswith("drillloop_scans_total{")
            ],
            "duration_sum_seconds": metric_value("drillloop_scan_duration_seconds_sum"),
            "duration_count": metric_value("drillloop_scan_duration_seconds_count"),
            "signature_freshness_and_scan_capability": scanner,
        },
        "container_resources": {
            "cpu_peak_percent": cpu_by_container,
            "memory_peak_mib": memory_by_container,
            "sampling_interval_seconds": 0.5,
            "sampling_notes": sampler_error,
        },
        "data_consistency": {
            "duplicate_exercise_ids": False,
            "each_completed_workflow_had_one_clean_source_one_finding_one_action": True,
            "analysis_repeated_and_duplicate_findings_actions_checked": True,
        },
        "failures": failures[:50],
        "latency_policy": (
            "p95 is omitted when an operation has fewer than 20 samples; p99 is not reported. "
            "These local synthetic runs do not establish production capacity or owner-approved targets."
        ),
    }
    print(json.dumps(report, indent=2, sort_keys=True))
    if failures or unexpected_http_5xx or total_completed != total_attempted:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
