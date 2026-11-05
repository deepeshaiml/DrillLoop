#!/usr/bin/env python3
"""Evaluate analysis against a versioned dataset in a throwaway local database."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import shutil
import sys
import time
from collections import Counter
from datetime import UTC, datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from scripts.isolated_runtime import configure  # noqa: E402

TEMP_ROOT = configure()

from app import db as database  # noqa: E402
from app.main import APP_REVISION, APP_VERSION, app  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _load_dataset(path: Path) -> dict:
    dataset = json.loads(path.read_text(encoding="utf-8"))
    if dataset.get("schema_version") != "drillloop-evaluation/v1":
        raise SystemExit("Unsupported evaluation dataset schema_version.")
    if not dataset.get("fictional"):
        raise SystemExit("This runner accepts only explicitly fictional datasets.")
    for source in dataset.get("sources", []):
        source_path = (ROOT / source["path"]).resolve()
        if ROOT not in source_path.parents or not source_path.is_file():
            raise SystemExit(
                f"Dataset source is missing or outside the repository: {source['path']}"
            )
        if _sha256(source_path) != source["sha256"]:
            raise SystemExit(f"Dataset source fingerprint mismatch: {source['path']}")
    for required in ("observations", "findings", "unknowns", "conflicts"):
        if not isinstance(dataset.get("expected", {}).get(required), list):
            raise SystemExit(f"Dataset expected.{required} must be a list.")
    return dataset


def _rate(expected: set, actual: set, *, labels_complete: bool = True) -> dict:
    true_positive = len(expected & actual)
    false_positive = len(actual - expected)
    false_negative = len(expected - actual)
    precision = true_positive / len(actual) if actual else (1.0 if not expected else 0.0)
    recall = true_positive / len(expected) if expected else (1.0 if not actual else 0.0)
    return {
        "true_positive": true_positive,
        "false_positive": false_positive,
        "false_negative": false_negative,
        "labels_complete": labels_complete,
        "precision": round(precision, 4) if labels_complete else None,
        "recall": round(recall, 4) if labels_complete else None,
        "f1": (
            round(2 * precision * recall / (precision + recall), 4) if precision + recall else 0.0
        )
        if labels_complete
        else None,
    }


def _locator_key(row: dict) -> tuple[str, str]:
    locator = row.get("source_locator", "").split(" · ", 1)[0]
    return row.get("source_filename", ""), locator


def evaluate(dataset: dict, dataset_path: Path) -> dict:
    database.migrate_database()
    exercise = dataset["exercise"]
    exercise_id = exercise["id"]
    expected_findings = {row["code"] for row in dataset["expected"]["findings"]}
    expected_observations = {
        (row["source"], row["locator"]) for row in dataset["expected"]["observations"]
    }
    with TestClient(app) as client:
        login = client.post(
            "/api/auth/login",
            json={"username": "evaluation-admin", "password": "synthetic-evaluation-only-password"},
        )
        if login.status_code != 200:
            raise RuntimeError(f"Isolated evaluation login failed: HTTP {login.status_code}")
        client.headers.update({"X-CSRF-Token": login.json()["csrf_token"]})
        created = client.post(
            "/api/exercises",
            json={
                "id": exercise_id,
                "title": exercise["title"],
                "scenario": exercise["scenario"],
                "exercise_date": exercise["date"],
                "duration_minutes": exercise["duration_minutes"],
                "objectives": exercise["objectives"],
            },
        )
        if created.status_code != 201:
            raise RuntimeError(f"Fictional exercise setup failed: HTTP {created.status_code}")
        mime_types = {
            ".csv": "text/csv",
            ".json": "application/json",
            ".txt": "text/plain",
            ".md": "text/markdown",
            ".log": "text/plain",
            ".pdf": "application/pdf",
        }
        for source in dataset["sources"]:
            source_path = (ROOT / source["path"]).resolve()
            suffix = source_path.suffix.casefold()
            uploaded = client.post(
                f"/api/exercises/{exercise_id}/evidence",
                files={
                    "files": (
                        source_path.name,
                        source_path.read_bytes(),
                        mime_types.get(suffix, "application/octet-stream"),
                    )
                },
            )
            if uploaded.status_code != 201:
                raise RuntimeError(
                    f"Fictional source import failed for {source_path.name}: HTTP {uploaded.status_code}"
                )
        started = time.perf_counter()
        analyzed = client.post(f"/api/exercises/{exercise_id}/analyze")
        analysis_latency_ms = (time.perf_counter() - started) * 1000
        if analyzed.status_code != 200:
            raise RuntimeError(f"Analysis failed: HTTP {analyzed.status_code}")
        response = client.get(f"/api/exercises/{exercise_id}")
        if response.status_code != 200:
            raise RuntimeError(f"Exercise detail failed: HTTP {response.status_code}")
        detail = response.json()

    actual_findings = {row["code"] for row in detail["findings"]}
    finding_labels_complete = bool(
        dataset.get("labeling", {}).get("finding_labels_complete", False)
    )
    observation_labels_complete = bool(
        dataset.get("labeling", {}).get("observation_labels_complete", False)
    )
    finding_metrics = _rate(
        expected_findings, actual_findings, labels_complete=finding_labels_complete
    )
    actual_observations = {_locator_key(row) for row in detail["timeline"]}
    observation_metrics = _rate(
        expected_observations, actual_observations, labels_complete=observation_labels_complete
    )

    expected_citations = {
        (finding["code"], evidence["source"], evidence["locator"])
        for finding in dataset["expected"]["findings"]
        for evidence in finding["evidence"]
    }
    actual_citations = {
        (finding["code"], *_locator_key(row))
        for finding in detail["findings"]
        for row in finding.get("supporting_evidence", [])
    }
    citation_matches = expected_citations & actual_citations
    unlabeled_citations = actual_citations - expected_citations
    citation_occurrences = [
        (finding["code"], *_locator_key(row))
        for finding in detail["findings"]
        for row in finding.get("supporting_evidence", [])
    ]
    citation_counts = Counter(citation_occurrences)
    citation_labels_complete = bool(
        dataset.get("labeling", {}).get("citation_labels_complete", False)
    )
    citation_precision = (
        round(len(citation_matches) / len(actual_citations), 4)
        if citation_labels_complete and actual_citations
        else (1.0 if citation_labels_complete else None)
    )
    citations = {
        "matched": len(citation_matches),
        "missing": len(expected_citations - actual_citations),
        "expected": len(expected_citations),
        "recall": round(len(citation_matches) / len(expected_citations), 4)
        if expected_citations
        else 1.0,
        "precision": citation_precision,
        "unsupported_citation_rate": (
            round(len(unlabeled_citations) / len(actual_citations), 4)
            if citation_labels_complete and actual_citations
            else None
        ),
        "label_scope": "exhaustive" if citation_labels_complete else "canonical_required_only",
        "additional_unlabeled_references": len(unlabeled_citations),
        "additional_references_need_review": bool(unlabeled_citations),
        "duplicate_reference_occurrences": sum(count - 1 for count in citation_counts.values()),
        "additional_references": [
            {
                "finding_code": code,
                "source": source,
                "locator": locator,
                "occurrences": citation_counts[(code, source, locator)],
                "classification": "unmatched_label_requires_review",
            }
            for code, source, locator in sorted(unlabeled_citations)
        ],
    }

    expected_times = {
        (row["source"], row["locator"]): row["timestamp"]
        for row in dataset["expected"]["observations"]
        if row["timestamp"] is not None
    }
    expected_unknown_times = {
        (row["source"], row["locator"])
        for row in dataset["expected"]["observations"]
        if row["timestamp"] is None
    }
    expected_rows = {
        (row["source"], row["locator"]): row for row in dataset["expected"]["observations"]
    }
    observed_timed_rows = {
        _locator_key(row): row.get("event_time_normalized") for row in detail["timeline"]
    }
    actual_rows = {_locator_key(row): row for row in detail["timeline"]}
    timestamp_matches = sum(
        observed_timed_rows.get(locator) == timestamp
        for locator, timestamp in expected_times.items()
    )
    timestamp_result = {
        "matched": timestamp_matches,
        "expected": len(expected_times),
        "accuracy": round(timestamp_matches / len(expected_times), 4) if expected_times else None,
        "unknown_expected": len(expected_unknown_times),
        "unknown_observed": sum(
            observed_timed_rows.get(locator) is None
            and actual_rows.get(locator, {}).get("time_confidence") in {"unknown", "uncertain"}
            for locator in expected_unknown_times
        ),
    }
    wording_matches = sum(
        actual_rows.get(locator, {}).get("text") == expected["wording"]
        for locator, expected in expected_rows.items()
    )
    confidence_matches = sum(
        actual_rows.get(locator, {}).get("time_confidence") == expected["time_confidence"]
        for locator, expected in expected_rows.items()
    )

    per_objective = {}
    actual_by_objective: dict[str, set[str]] = {}
    for finding in detail["findings"]:
        actual_by_objective.setdefault(finding.get("objective_id") or "unknown", set()).add(
            finding["code"]
        )
    for objective in dataset["exercise"]["objectives"]:
        per_objective[objective["id"]] = _rate(
            set(objective["expected_finding_codes"]),
            actual_by_objective.get(objective["id"], set()),
            labels_complete=finding_labels_complete,
        )

    expected_findings_by_code = {row["code"]: row for row in dataset["expected"]["findings"]}
    incorrect_objective_interpretations = []
    for actual in detail["findings"]:
        expected = expected_findings_by_code.get(actual["code"])
        if expected and (
            actual.get("objective_id") != expected.get("objective_id")
            or actual.get("category") != expected.get("category")
        ):
            incorrect_objective_interpretations.append(
                {
                    "finding_code": actual["code"],
                    "expected_objective_id": expected.get("objective_id"),
                    "actual_objective_id": actual.get("objective_id"),
                    "expected_category": expected.get("category"),
                    "actual_category": actual.get("category"),
                }
            )

    expected_assessments = {
        row["objective_id"]: row for row in dataset["expected"].get("objective_assessments", [])
    }
    actual_assessments = {
        row.get("objective_id"): row for row in detail.get("objective_assessments", [])
    }
    duration_results = []
    for objective_id, expected in expected_assessments.items():
        actual = actual_assessments.get(objective_id, {})
        checks = {}
        for field in ("state", "elapsed_seconds", "reported_seconds", "threshold_seconds"):
            if field in expected:
                checks[field] = {
                    "expected": expected[field],
                    "actual": actual.get(field),
                    "matched": actual.get(field) == expected[field],
                }
        duration_results.append(
            {
                "objective_id": objective_id,
                "checks": checks,
                "matched": all(value["matched"] for value in checks.values()),
            }
        )

    found_unknowns = []
    for expected in dataset["expected"]["unknowns"]:
        row = next(
            (
                item
                for item in detail["timeline"]
                if _locator_key(item) == (expected["source"], expected["locator"])
            ),
            None,
        )
        found_unknowns.append(
            {
                **expected,
                "observed": bool(
                    row
                    and (
                        row.get("time_confidence") in {"unknown", "uncertain"}
                        or (
                            row.get("recognition_confidence") is not None
                            and row["recognition_confidence"] < 0.75
                        )
                    )
                ),
            }
        )
    conflict_refs = {_locator_key(row) for row in detail.get("timeline_conflicts", [])}
    found_conflicts = [
        {
            **expected,
            "observed": (expected["source"], expected["locators"][0]) in conflict_refs,
        }
        for expected in dataset["expected"]["conflicts"]
    ]
    proposal_state = {
        "all_findings_proposed": all(row.get("status") == "proposed" for row in detail["findings"]),
        "all_reviewer_decisions_null": all(
            row.get("reviewer") is None for row in detail["findings"]
        ),
    }
    limitations = [
        "This result measures one fictional developer-authored dataset, not real exercise accuracy.",
        "The labels have not been independently reviewed; passing them does not establish generalization or reviewer utility.",
        "Analysis latency is a single local deterministic request measurement and is not a capacity benchmark.",
    ]
    if not citation_labels_complete:
        limitations.append(
            "Citation labels list required canonical references but are not exhaustive; citation precision and unsupported-citation rate are intentionally undefined."
        )

    result = {
        "schema_version": "drillloop-evaluation-result/v1",
        "created_at_utc": datetime.now(UTC).isoformat(),
        "dataset_id": dataset["dataset_id"],
        "dataset_revision": dataset["revision"],
        "dataset_sha256": _sha256(dataset_path),
        "dataset_labeling": dataset["labeling"],
        "fictional": True,
        "application": {"version": APP_VERSION, "revision": APP_REVISION},
        "metrics": {
            "observations": observation_metrics,
            "findings": finding_metrics,
            "citations": citations,
            "timestamps": timestamp_result,
            "source_wording": {"matched": wording_matches, "expected": len(expected_rows)},
            "time_confidence": {"matched": confidence_matches, "expected": len(expected_rows)},
            "per_objective": per_objective,
            "per_exercise": {
                exercise_id: {
                    "findings": finding_metrics,
                    "observations": observation_metrics,
                    "canonical_citations": citations,
                }
            },
            "incorrect_objective_interpretations": incorrect_objective_interpretations,
            "timestamp_and_duration": {
                "timestamp_errors": len(expected_times) - timestamp_matches,
                "duration_cases": duration_results,
                "duration_errors": sum(not row["matched"] for row in duration_results),
                "actual_objective_assessments": detail.get("objective_assessments", []),
            },
            "unknowns": {
                "observed": sum(item["observed"] for item in found_unknowns),
                "expected": len(found_unknowns),
                "cases": found_unknowns,
            },
            "conflicts": {
                "observed": sum(item["observed"] for item in found_conflicts),
                "expected": len(found_conflicts),
                "cases": found_conflicts,
            },
            "proposed_decisions": proposal_state,
            "analysis_latency_ms": round(analysis_latency_ms, 2),
        },
        "failure_cases": {
            "false_positive_findings": sorted(actual_findings - expected_findings),
            "false_negative_findings": sorted(expected_findings - actual_findings),
            "duplicate_finding_codes": sorted(
                code
                for code, count in Counter(row["code"] for row in detail["findings"]).items()
                if count > 1
            ),
            "missing_citations": sorted(expected_citations - actual_citations),
            "additional_unlabeled_citations_requiring_review": sorted(unlabeled_citations),
            "incorrect_objective_interpretations": incorrect_objective_interpretations,
            "insufficient_evidence_assessments": [
                row
                for row in detail.get("objective_assessments", [])
                if row.get("state") == "insufficient_information"
            ],
            "source_wording_mismatches": [
                {
                    "source": source,
                    "locator": locator,
                    "expected": expected["wording"],
                    "actual": actual_rows.get((source, locator), {}).get("text"),
                }
                for (source, locator), expected in expected_rows.items()
                if actual_rows.get((source, locator), {}).get("text") != expected["wording"]
            ],
            "time_confidence_mismatches": [
                {
                    "source": source,
                    "locator": locator,
                    "expected": expected["time_confidence"],
                    "actual": actual_rows.get((source, locator), {}).get("time_confidence"),
                }
                for (source, locator), expected in expected_rows.items()
                if actual_rows.get((source, locator), {}).get("time_confidence")
                != expected["time_confidence"]
            ],
            "timestamp_mismatches": [
                {
                    "source": source,
                    "locator": locator,
                    "expected": timestamp,
                    "actual": observed_timed_rows.get((source, locator)),
                }
                for (source, locator), timestamp in expected_times.items()
                if observed_timed_rows.get((source, locator)) != timestamp
            ],
            "unexpected_timestamps_on_unknown_events": [
                {
                    "source": source,
                    "locator": locator,
                    "expected": None,
                    "actual": observed_timed_rows.get((source, locator)),
                }
                for source, locator in sorted(expected_unknown_times)
                if observed_timed_rows.get((source, locator)) is not None
            ],
        },
        "limitations": limitations,
    }
    return result


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dataset", default="evals/datasets/synthetic-hospital-v1.json")
    parser.add_argument(
        "--baseline-result", help="Compare metric counts with a previous result JSON."
    )
    parser.add_argument("--output", help="Write to a new file; existing paths are refused.")
    args = parser.parse_args()
    dataset_path = Path(args.dataset).resolve()
    dataset = _load_dataset(dataset_path)
    result = evaluate(dataset, dataset_path)
    if args.baseline_result:
        baseline = json.loads(Path(args.baseline_result).read_text(encoding="utf-8"))
        result["regression_comparison"] = {
            "baseline_dataset_id": baseline.get("dataset_id"),
            "baseline_application": baseline.get("application"),
            "metric_count_deltas": {},
        }
        for metric_name in ("observations", "findings", "citations"):
            current = result["metrics"][metric_name]
            previous = baseline.get("metrics", {}).get(metric_name, {})
            result["regression_comparison"]["metric_count_deltas"][metric_name] = {
                key: current.get(key, 0) - previous.get(key, 0)
                for key in ("true_positive", "false_positive", "false_negative")
            }
    rendered = json.dumps(result, indent=2, sort_keys=True) + "\n"
    if args.output:
        output_path = Path(args.output).expanduser().absolute()
        if output_path.exists() or output_path.is_symlink():
            raise SystemExit("Output already exists; refusing to overwrite evaluation results.")
        descriptor = os.open(output_path, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
        with os.fdopen(descriptor, "w", encoding="utf-8") as stream:
            stream.write(rendered)
    print(rendered, end="")
    marker = TEMP_ROOT / ".drillloop-test-owner"
    if marker.is_file() and marker.read_text(encoding="utf-8").strip() == os.environ.get(
        "DRILLLOOP_TEST_DB_TOKEN"
    ):
        shutil.rmtree(TEMP_ROOT)


if __name__ == "__main__":
    main()
