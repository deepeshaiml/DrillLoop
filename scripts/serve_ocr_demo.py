#!/usr/bin/env python3
"""Serve a fictional OCR demo on an owner-marked disposable SQLite database."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from scripts.isolated_runtime import configure  # noqa: E402

TEMP_ROOT = configure()
sys.path.insert(0, str(ROOT / "backend"))

from app import db as database  # noqa: E402
from app.main import app  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402

DEMO_USERNAME = "evaluation-admin"
DEMO_PASSWORD = "synthetic-evaluation-only-password"
EXERCISE_ID = "OCR-PHASE2-DEMO"


def _prepare_exercise() -> None:
    database.migrate_database()
    with TestClient(app) as client:
        login = client.post(
            "/api/auth/login",
            json={"username": DEMO_USERNAME, "password": DEMO_PASSWORD},
        )
        if login.status_code != 200:
            raise RuntimeError("Could not initialize the fictional OCR demo account.")
        client.headers.update({"X-CSRF-Token": login.json()["csrf_token"]})
        created = client.post(
            "/api/exercises",
            json={
                "id": EXERCISE_ID,
                "title": "Fictional water utility scanned-PDF exercise",
                "scenario": "A wholly fictional exercise for scanned PDF OCR and evidence traceability.",
                "exercise_date": "2026-11-13",
                "duration_minutes": 30,
                "objectives": [
                    {
                        "id": "OBJ-PRESSURE-15",
                        "text": "Restore stable pressure within 15 minutes after the alarm.",
                        "evaluation_rule": {
                            "type": "elapsed_time",
                            "threshold_seconds": 900,
                            "start_terms": ["low-pressure alarm activated"],
                            "completion_terms": ["stable pressure"],
                        },
                    },
                    {
                        "id": "OBJ-STATION-B",
                        "text": "Confirm Station B service restored.",
                        "evaluation_rule": {
                            "type": "event_presence",
                            "terms": ["station b confirmed service restored"],
                            "finding_code": "STATION_B_RESTORED",
                        },
                    },
                ],
            },
        )
        if created.status_code != 201:
            raise RuntimeError(f"Could not prepare the fictional OCR exercise: {created.text}")


def main() -> None:
    import uvicorn

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--port", type=int, default=8123)
    args = parser.parse_args()
    if not 1 <= args.port <= 65535:
        raise SystemExit("Port must be between 1 and 65535.")
    _prepare_exercise()
    print(f"Fictional OCR exercise ready: {EXERCISE_ID}", flush=True)
    print(f"Open http://127.0.0.1:{args.port} and sign in with:", flush=True)
    print(f"  username: {DEMO_USERNAME}", flush=True)
    print(f"  password: {DEMO_PASSWORD}", flush=True)
    print(
        "Upload only evals/phase2/sources/utility_emergency_log_scanned.pdf; this local synthetic demo has scanning disabled.",
        flush=True,
    )
    uvicorn.run(app, host="127.0.0.1", port=args.port, log_level="warning")


if __name__ == "__main__":
    main()
