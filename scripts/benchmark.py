#!/usr/bin/env python3
"""Run the reproducible, fixture-only DrillLoop technical benchmark."""

from __future__ import annotations

import json
import os
import re
import resource
import statistics
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))
os.environ["DATABASE_URL"] = "sqlite:///./.benchmark-drillloop.db"
os.environ["DEMO_SEED"] = "1"

from fastapi.testclient import TestClient  # noqa: E402

from app.evidence import normalize_time, parse_evidence  # noqa: E402
from app.main import app  # noqa: E402


def metric(actual: set[str], expected: set[str]) -> dict:
    tp = len(actual & expected)
    precision = tp / len(actual) if actual else 0.0
    recall = tp / len(expected) if expected else 0.0
    return {"true_positive": tp, "predicted": len(actual), "expected": len(expected),
            "precision": round(precision, 4), "recall": round(recall, 4),
            "f1": round(2 * precision * recall / (precision + recall), 4) if precision + recall else 0}


def main() -> None:
    ground_truth = json.loads((ROOT / "demo/ground_truth.json").read_text())
    fixture = (ROOT / "demo/evidence/control_room_log.csv").read_bytes()
    parsed = parse_evidence("control_room_log.csv", "text/csv", fixture,
                            __import__("datetime").date(2026, 10, 16))
    expected_ids = set(ground_truth["expected_observation_ids"])
    expected_times = {}
    import csv
    from io import StringIO

    for row in csv.DictReader(StringIO(fixture.decode())):
        expected_times[row["event_id"]] = normalize_time(row["timestamp"],
                                                           __import__("datetime").date(2026, 10, 16))[0]

    with TestClient(app) as client:
        detail = client.get("/api/exercises/HOSP-PO-2026-01").json()
        finding_actual = {finding["code"] for finding in detail["findings"]}
        finding_expected = {finding["code"] for finding in ground_truth["expected_findings"]}

        observation_actual = {
            re.search(r"EL-\d+", row["source_locator"]).group(0)
            for row in detail["timeline"]
            if row["source_filename"] == "control_room_log.csv"
            and re.search(r"EL-\d+", row["source_locator"])
        }
        time_matches = 0
        for row in detail["timeline"]:
            match = re.search(r"EL-\d+", row["source_locator"])
            if row["source_filename"] == "control_room_log.csv" and match:
                time_matches += row["event_time_normalized"] == expected_times[match.group(0)]

        expected_citations = {
            finding["code"]: set(finding["evidence_ids"])
            for finding in ground_truth["expected_findings"]
        }
        source_citations = {
            finding["code"]: {
                match.group(0) for row in finding["supporting_evidence"]
                if row["source_filename"] == "control_room_log.csv"
                and (match := re.search(r"EL-\d+", row["source_locator"]))
            }
            for finding in detail["findings"]
        }
        expected_citation_count = sum(map(len, expected_citations.values()))
        exact_citation_count = sum(len(expected_citations[code] & source_citations.get(code, set()))
                                   for code in expected_citations)
        actions = detail["actions"]
        required = ["finding_id", "evidence_ids", "owner", "priority", "due_date",
                    "acceptance_criteria", "status", "reviewer_decision"]
        complete_fields = sum(bool(action.get(key)) for action in actions for key in required)
        possible_fields = len(actions) * len(required)

        latencies = []
        for _ in range(12):
            started = time.perf_counter()
            client.post("/api/exercises/HOSP-PO-2026-01/analyze")
            latencies.append((time.perf_counter() - started) * 1000)

        no_time = [row for row in detail["timeline"] if row["time_confidence"] == "unknown"]
        low_asr = [row for row in detail["timeline"]
                   if row["recognition_confidence"] is not None and row["recognition_confidence"] < .75]
        expected_by_code = {item["code"]: item for item in ground_truth["expected_findings"]}
        unsupported_findings = 0
        for finding in detail["findings"]:
            expected_item = expected_by_code.get(finding["code"])
            cited_ids = source_citations.get(finding["code"], set())
            if (not expected_item or not finding["supporting_evidence"]
                    or not set(expected_item["evidence_ids"]).issubset(cited_ids)):
                unsupported_findings += 1
        uncited_findings = sum(not finding["supporting_evidence"] for finding in detail["findings"])
        peak = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss
        peak_mb = peak / (1024 * 1024 if sys.platform == "darwin" else 1024)

        output = {
            "title": "DrillLoop synthetic fixture technical benchmark",
            "date": "2026-10-26",
            "fixture_label": ground_truth["label"],
            "scope": "One closed, fictional fixture with eight event rows, three files, and five expected findings; scores do not estimate generalization or human performance.",
            "observations": metric(observation_actual, expected_ids),
            "findings": metric(finding_actual, finding_expected),
            "unsupported_finding_rate": round(unsupported_findings / max(len(detail["findings"]), 1), 4),
            "unsupported_finding_count": unsupported_findings,
            "uncited_finding_count": uncited_findings,
            "evidence_citation_accuracy": round(exact_citation_count / expected_citation_count, 4) if expected_citation_count else 0,
            "citations_correct": exact_citation_count,
            "citations_expected": expected_citation_count,
            "timeline": {"timestamp_matches": int(time_matches), "timestamp_rows": len(expected_times),
                         "correctness": round(time_matches / len(expected_times), 4) if expected_times else 0,
                         "unresolved_conflict_count": len(detail["timeline_conflicts"]),
                         "missing_time_observation_count": len(no_time)},
            "corrective_action_completeness": {"complete_required_fields": complete_fields,
                                               "possible_required_fields": possible_fields,
                                               "field_completeness": round(complete_fields / possible_fields, 4) if possible_fields else 0,
                                               "owner_assigned": sum(bool(a["owner"]) for a in actions),
                                               "action_count": len(actions)},
            "edge_cases": {"missing_timestamp_kept_unplaced": bool(no_time),
                           "contradictory_evaluator_times_flagged": bool(detail["timeline_conflicts"]),
                           "ambiguous_untimed_statement_not_promoted": not any("lagged a bit" in f["observation"].lower() for f in detail["findings"]),
                           "low_confidence_asr_retained_for_review": bool(low_asr)},
            "latency_ms": {"runs": len(latencies), "p50": round(statistics.median(latencies), 2),
                           "p95": round(sorted(latencies)[int(.95 * (len(latencies) - 1))], 2),
                           "note": "Measured local deterministic rule pipeline request latency; no LLM inference."},
            "peak_process_rss_mb": round(peak_mb, 1),
            "comparison": {
                "manual_evaluation": {"status": "not measured", "reason": "No participating evaluators or timed manual baseline."},
                "rule_based_offline": {"status": "measured", "finding_precision": metric(finding_actual, finding_expected)["precision"],
                                       "finding_recall": metric(finding_actual, finding_expected)["recall"]},
                "local_llm_assisted": {"status": "not run", "reason": "No Ollama model configured; no model-quality claim is made."},
            },
            "limitations": [
                "This compact benchmark is fixture-locked and built around the labeled synthetic scenario.",
                "No actual evaluator time, correction workload, or labor cost was measured.",
                "The deterministic pipeline is an auditable baseline; results do not validate other organizations, scenarios, languages, or recording quality.",
                "ASR accuracy and latency were not measured; one pre-generated low-confidence transcript segment is only checked for uncertainty handling.",
            ],
        }
    target = ROOT / "demo/benchmark_results.json"
    target.write_text(json.dumps(output, indent=2) + "\n")
    print(json.dumps(output, indent=2))
    try:
        (ROOT / ".benchmark-drillloop.db").unlink()
    except FileNotFoundError:
        pass


if __name__ == "__main__":
    main()
