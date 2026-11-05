#!/usr/bin/env python3
"""Run a bounded synthetic GET load against a loopback-only DrillLoop readiness URL."""

from __future__ import annotations

import argparse
import json
import statistics
import subprocess
import threading
import time
import urllib.error
import urllib.parse
import urllib.request
from collections import Counter
from datetime import UTC, datetime


def resident_mb(pid: int | None) -> float | None:
    if pid is None:
        return None
    result = subprocess.run(
        ["ps", "-o", "rss=", "-p", str(pid)], capture_output=True, text=True, check=False
    )
    try:
        return int(result.stdout.strip()) / 1024
    except (ValueError, TypeError):
        return None


def request(url: str, timeout: float) -> tuple[float, int | None]:
    started = time.perf_counter()
    status = None
    try:
        with urllib.request.urlopen(url, timeout=timeout) as response:
            status = response.status
            response.read(4096)
    except urllib.error.HTTPError as exc:
        status = exc.code
        exc.read(4096)
    except (urllib.error.URLError, TimeoutError, OSError):
        pass
    return (time.perf_counter() - started) * 1000, status


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--base-url", default="http://127.0.0.1:8000")
    parser.add_argument("--requests", type=int, default=100)
    parser.add_argument("--concurrency", type=int, default=10)
    parser.add_argument("--pid", type=int, help="Optional PID of the local DrillLoop API process.")
    args = parser.parse_args()
    parsed = urllib.parse.urlparse(args.base_url)
    if parsed.scheme != "http" or parsed.hostname not in {"127.0.0.1", "localhost", "::1"}:
        raise SystemExit("Load testing is restricted to an HTTP loopback target.")
    if parsed.path not in {"", "/"} or parsed.query or parsed.username or parsed.password:
        raise SystemExit("Specify a loopback origin only; the script requests /api/ready.")
    if not 1 <= args.requests <= 1000 or not 1 <= args.concurrency <= 20:
        raise SystemExit("Limits are 1–1000 requests and 1–20 concurrent workers.")
    if args.pid is not None and args.pid <= 1:
        raise SystemExit("PID must identify a non-system process.")

    url = f"{args.base_url.rstrip('/')}/api/ready"
    samples: list[tuple[float, int | None]] = []
    samples_lock = threading.Lock()
    finished = threading.Event()
    memory_samples = [resident_mb(args.pid)]

    def sample_memory() -> None:
        while not finished.wait(0.2):
            value = resident_mb(args.pid)
            if value is not None:
                memory_samples.append(value)

    sampler = threading.Thread(target=sample_memory, daemon=True)
    sampler.start()
    started = time.perf_counter()
    from concurrent.futures import ThreadPoolExecutor, as_completed

    with ThreadPoolExecutor(max_workers=args.concurrency) as pool:
        futures = [pool.submit(request, url, 5.0) for _ in range(args.requests)]
        for future in as_completed(futures):
            with samples_lock:
                samples.append(future.result())
    elapsed = time.perf_counter() - started
    finished.set()
    sampler.join(timeout=1)

    latencies = sorted(sample[0] for sample in samples)
    statuses = Counter(
        str(sample[1]) if sample[1] is not None else "connection_error" for sample in samples
    )
    failures = sum(count for status, count in statuses.items() if status != "200")
    p95_index = min(len(latencies) - 1, max(0, int(0.95 * len(latencies)) - 1))
    report = {
        "schema_version": "drillloop-load-result/v1",
        "created_at_utc": datetime.now(UTC).isoformat(),
        "target": "http://loopback/api/ready",
        "requests": args.requests,
        "concurrency": args.concurrency,
        "elapsed_seconds": round(elapsed, 4),
        "throughput_requests_per_second": round(args.requests / elapsed, 2) if elapsed else None,
        "latency_ms": {
            "p50": round(statistics.median(latencies), 2) if latencies else None,
            "p95": round(latencies[p95_index], 2) if latencies else None,
            "max": round(max(latencies), 2) if latencies else None,
        },
        "failures": failures,
        "status_counts": dict(statuses),
        "process_memory_mb": {
            "pid": args.pid,
            "initial": round(memory_samples[0], 1) if memory_samples[0] is not None else None,
            "sampled_peak": round(max(memory_samples), 1)
            if any(value is not None for value in memory_samples)
            else None,
            "sample_interval_ms": 200,
        },
        "limits": "Synthetic GET readiness probe only; max 1000 requests, concurrency 20, 5 second request timeout.",
    }
    print(json.dumps(report, indent=2, sort_keys=True))
    if failures:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
