#!/usr/bin/env python3
"""Run the fictional Phase 4A evaluation or serve its browser demo on disposable storage."""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from scripts.isolated_runtime import configure  # noqa: E402

BASE = "/api/exercises"
USERNAME = "evaluation-admin"
PASSWORD = "synthetic-evaluation-only-password"
MIME_TYPES = {".txt": "text/plain", ".csv": "text/csv", ".pdf": "application/pdf"}


def load_cases() -> tuple[dict, list[dict]]:
    dataset = json.loads((ROOT / "evals/phase4a/cases.json").read_text())
    assert dataset["fictional"]
    for case in dataset["cases"]:
        if "phase1_dataset" in case:
            baseline = json.loads((ROOT / "evals/phase1" / case["phase1_dataset"]).read_text())
            assert baseline["fictional"]
            exercise = baseline["exercise"]
            case["exercise"] = {
                **exercise,
                "exercise_date": exercise["date"],
            }
            case["sources"] = [item["path"] for item in baseline["sources"]]
            for source in baseline["sources"]:
                assert (
                    hashlib.sha256((ROOT / source["path"]).read_bytes()).hexdigest()
                    == source["sha256"]
                )
            case["baseline_findings"] = sorted(
                item["code"] for item in baseline["expected"]["findings"]
            )
    return dataset["labeling"], dataset["cases"]


def expect(response, expected: int) -> dict:
    if response.status_code != expected:
        code = response.json().get("detail")
        raise RuntimeError(f"Expected HTTP {expected}, got {response.status_code}: {code}")
    return response.json()


def sign_in(client) -> None:
    session = expect(
        client.post("/api/auth/login", json={"username": USERNAME, "password": PASSWORD}), 200
    )
    client.headers.update({"X-CSRF-Token": session["csrf_token"]})


def evaluate_case(client, case: dict) -> dict:
    exercise = expect(client.post(BASE, json=case["exercise"]), 201)
    path = f"{BASE}/{exercise['id']}"
    for source in case["sources"]:
        source_path = ROOT / source
        expect(
            client.post(
                f"{path}/evidence",
                files={
                    "files": (
                        source_path.name,
                        source_path.read_bytes(),
                        MIME_TYPES[source_path.suffix],
                    )
                },
            ),
            201,
        )
    start = time.perf_counter()
    expect(client.post(f"{path}/analyze"), 200)
    rule_latency_ms = round(1000 * (time.perf_counter() - start))
    before = expect(client.get(path), 200)
    response = expect(client.post(f"{path}/ai-suggestions"), 200)
    after = expect(client.get(path), 200)
    findings = sorted(item["code"] for item in before["findings"])
    return {
        "exercise_id": exercise["id"],
        "provider": response["provider"],
        "model": response["model"],
        "deterministic": {
            "latency_ms": rule_latency_ms,
            "finding_codes": findings,
            "matches_phase1_finding_labels": findings == case["baseline_findings"]
            if "baseline_findings" in case
            else None,
            "objective_states": {
                item["objective_id"]: item["state"] for item in before["objective_assessments"]
            },
            "entire_exercise_detail_unchanged_after_ai_request": before == after,
        },
        "hybrid": {
            key: response[key]
            for key in (
                "latency_ms",
                "input_tokens",
                "output_tokens",
                "citations_attempted",
                "citations_matched",
                "rejected_suggestion_count",
                "unassessed_objective_ids",
            )
        },
        "developer_label_comparison": score(case["labels"], response["suggestions"]),
    }


def score(labels: dict, suggestions: list[dict]) -> list[dict]:
    results = []
    by_objective = {item["objective_id"]: item for item in suggestions}
    for objective, label in labels.items():
        item = by_objective.get(objective)
        challenge = label["challenge"]
        citations = [] if item is None else item["evidence"] + item["counterevidence"]
        matching_refs = [
            (cite["source_filename"], cite["source_locator"].split(" · ", 1)[0])
            for cite in citations
            if any(
                filename == cite["source_filename"]
                and locator == cite["source_locator"].split(" · ", 1)[0]
                and wording.casefold() in cite["text"].casefold()
                for filename, locator, wording in label["references"]
            )
        ]
        kind = item["kind"] if item else None
        association = (
            item is not None
            and len(matching_refs) == len(citations)
            and (bool(citations) or kind == "insufficient_evidence")
        )
        challenge_met = True
        if challenge == "cross_source_match":
            challenge_met = {
                ("water_utility_log.csv", "row 2"),
                ("fictional_shift_notes.txt", "line 1"),
            } <= set(matching_refs)
        if challenge == "conflict":
            challenge_met = len(set(matching_refs)) == 2 and bool(item and item["counterevidence"])
        if challenge == "ocr_time":
            challenge_met = bool(item and "original page" in item["uncertainty"]) and any(
                cite["extraction_method"] == "ocr"
                and cite["time_confidence"] == "uncertain"
                and "event_time_normalized" not in cite
                for cite in citations
            )
        interpretation_supported = association and kind in label["kinds"] and challenge_met
        results.append(
            {
                "objective_id": objective,
                "challenge": challenge,
                "kind": kind,
                "objective_association_supported": association,
                "interpretation_supported": interpretation_supported,
                "claim_supported": interpretation_supported
                or (association and kind in label.get("also_grounded_kinds", [])),
                "citation_examples": [
                    {
                        key: cite[key]
                        for key in (
                            "source_filename",
                            "source_locator",
                            "text",
                            "time_confidence",
                            "extraction_method",
                        )
                    }
                    for cite in citations
                ],
                "unknowns": item["unknowns"] if item else [],
            }
        )
    return results


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path)
    parser.add_argument(
        "--serve", action="store_true", help="Serve the synthetic exercises before upload."
    )
    parser.add_argument("--port", type=int, default=8000)
    args = parser.parse_args()
    if args.output and args.output.exists():
        parser.error("Output must be a new file.")
    labeling, cases = load_cases()
    configure()

    from app import db
    from app.main import app
    from fastapi.testclient import TestClient

    db.migrate_database()
    with TestClient(app) as client:
        sign_in(client)
        if not args.serve:
            capabilities = expect(client.get("/api/capabilities"), 200)
            if capabilities["analysis"]["ai_assistance"]["state"] != "enabled":
                parser.error(
                    "Enable and configure the installed local model before running inference."
                )
            outcomes = [evaluate_case(client, case) for case in cases]
        else:
            for case in cases:
                expect(client.post(BASE, json=case["exercise"]), 201)

    if args.serve:
        import uvicorn

        print(f"Fictional Phase 4A exercises ready at http://127.0.0.1:{args.port}.", flush=True)
        uvicorn.run(app, host="127.0.0.1", port=args.port, log_level="warning")
        return

    result = {"fictional": True, "labeling": labeling, "real_inference": True, "cases": outcomes}
    rendered = json.dumps(result, indent=2) + "\n"
    if args.output:
        with args.output.open("x", encoding="utf-8") as output:
            output.write(rendered)
    else:
        print(rendered, end="")


if __name__ == "__main__":
    main()
