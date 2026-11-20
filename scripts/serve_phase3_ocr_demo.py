#!/usr/bin/env python3
"""Serve the fictional Phase 3 mixed-page OCR demo on a disposable database."""

from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from scripts.isolated_runtime import configure  # noqa: E402

TEMP_ROOT = configure()
sys.path.insert(0, str(ROOT / "backend"))

from app.auth import hash_password  # noqa: E402

_local_users = json.loads(os.environ["DRILLLOOP_USERS_JSON"])
_local_users.append(
    {
        "id": "phase3-review-viewer",
        "username": "phase3-review-viewer",
        "name": "Phase 3 Synthetic Viewer",
        "role": "viewer",
        "organization_id": "synthetic-evaluation",
        "password_hash": hash_password("phase3-viewer-only-password"),
    }
)
os.environ["DRILLLOOP_USERS_JSON"] = json.dumps(_local_users)

from app import db as database  # noqa: E402
from app.main import app  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402

DEMO_USERNAME = "evaluation-admin"
DEMO_PASSWORD = "synthetic-evaluation-only-password"
EXERCISE_ID = "OCR-PHASE3-DEMO"
EXERCISE_TITLE = "Fictional mixed-page water utility exercise"


def _prepare_exercise() -> None:
    database.migrate_database()
    with TestClient(app) as client:
        login = client.post(
            "/api/auth/login",
            json={"username": DEMO_USERNAME, "password": DEMO_PASSWORD},
        )
        if login.status_code != 200:
            raise RuntimeError("Could not initialize the fictional Phase 3 demo account.")
        client.headers.update({"X-CSRF-Token": login.json()["csrf_token"]})
        created = client.post(
            "/api/exercises",
            json={
                "id": EXERCISE_ID,
                "title": EXERCISE_TITLE,
                "scenario": "A wholly fictional water utility exercise with a mixed native-text and scanned-image PDF page.",
                "exercise_date": "2026-11-19",
                "duration_minutes": 30,
                "objectives": [
                    {
                        "id": "OBJ-PRESSURE-15",
                        "text": "Restore stable pressure within 15 minutes after the alarm.",
                        "evaluation_rule": {
                            "type": "elapsed_time",
                            "threshold_seconds": 900,
                            "start_terms": ["low-pressure alarm activated"],
                            "completion_terms": ["station b pump restored"],
                        },
                    },
                    {
                        "id": "OBJ-STATION-B-RESTORED",
                        "text": "Confirm Station B pump restoration.",
                        "evaluation_rule": {
                            "type": "event_presence",
                            "terms": ["station b pump restored"],
                            "finding_code": "STATION_B_PUMP_RESTORED",
                        },
                    },
                ],
            },
        )
        if created.status_code != 201:
            raise RuntimeError(f"Could not prepare the fictional exercise: {created.text}")


def main() -> None:
    import uvicorn

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--port", type=int, default=8000)
    args = parser.parse_args()
    if not 1 <= args.port <= 65535:
        raise SystemExit("Port must be between 1 and 65535.")
    _prepare_exercise()
    print(f"Fictional Phase 3 OCR exercise ready: {EXERCISE_ID}", flush=True)
    print(
        "This local synthetic demo uses a disposable SQLite database and scanner-disabled test mode.",
        flush=True,
    )
    print("Upload only evals/phase3/sources/phase3_same_page_mixed_water_log.pdf.", flush=True)
    print(f"Open http://127.0.0.1:{args.port} with {DEMO_USERNAME} / {DEMO_PASSWORD}.", flush=True)
    uvicorn.run(app, host="127.0.0.1", port=args.port, log_level="warning")


if __name__ == "__main__":
    main()
