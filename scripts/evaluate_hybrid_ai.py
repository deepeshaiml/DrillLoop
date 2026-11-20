#!/usr/bin/env python3
"""Evaluate fictional hybrid AI cases or serve the browser demo on disposable storage."""

from __future__ import annotations

import argparse
import hashlib
import json
import subprocess
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


def load_cases(suite: str = "phase4a") -> tuple[dict, list[dict]]:
    dataset = json.loads((ROOT / "evals" / suite / "cases.json").read_text())
    assert dataset["fictional"]
    historical = {}
    if suite == "phase4b":
        _, originals = load_cases()
        historical = {case["exercise"]["id"]: case for case in originals}
    for case in dataset["cases"]:
        if exercise_id := case.get("phase4a_exercise"):
            original = historical[exercise_id]
            case.update(exercise=original["exercise"], sources=original["sources"])
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


def prepare_case(client, case: dict) -> tuple[str, int]:
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
    return exercise["id"], round(1000 * (time.perf_counter() - start))


def evaluate_case(client, case: dict, prepared: tuple[str, int], suite: str) -> dict:
    exercise_id, rule_latency_ms = prepared
    path = f"{BASE}/{exercise_id}"
    before = expect(client.get(path), 200)
    request = client.post(f"{path}/ai-suggestions")
    response = expect(request, 200) if suite == "phase4a" else request.json()
    suggestions = response.get("suggestions", [])
    limited = response.get("context_limited", False) or (
        request.status_code == 413
        and response.get("detail", {}).get("code") == "AI_INPUT_TOO_LARGE"
    )
    after = expect(client.get(path), 200)
    findings = sorted(item["code"] for item in before["findings"])
    return {
        "exercise_id": exercise_id,
        "provider": response.get("provider"),
        "model": response.get("model"),
        "http_status": request.status_code,
        "error_code": response.get("detail", {}).get("code")
        if request.status_code != 200
        else None,
        "context_limited": limited,
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
            key: response.get(key)
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
        "developer_label_comparison": (
            score(case["labels"], suggestions)
            if suite == "phase4a"
            else score_quality(case["labels"], suggestions, limited)
        ),
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


LEGACY_KINDS = {
    "possible_cross_source_match": "corroboration",
    "conflicting_accounts": "contradiction",
    "ambiguous_observation": "unknown",
}


def score_quality(labels: dict, suggestions: list[dict], context_limited: bool) -> list[dict]:
    by_objective = {item["objective_id"]: item for item in suggestions}
    comparisons = []
    for objective, label in labels.items():
        item = by_objective.get(objective, {})
        actual_kind = item.get("kind")
        kind = LEGACY_KINDS.get(actual_kind, actual_kind)
        evidence = item.get("evidence", [])
        opposing = item.get("counterevidence", [])
        citations = evidence + opposing
        refs = label["references"]
        matched_groups = [
            {
                index
                for index, (filename, locator, *wording) in enumerate(refs)
                if filename == cite["source_filename"]
                and locator == cite["source_locator"].split(" · ", 1)[0]
                and (not wording or wording[0].casefold() in cite["text"].casefold())
            }
            for cite in citations
        ]
        matched = set().union(*matched_groups)
        abstained = (
            item.get("assessment") == "abstained"
            or actual_kind == "insufficient_evidence"
            or context_limited
        )
        expected_abstention = label.get("abstain", False)
        grounded = all(matched_groups) and (bool(citations) or abstained or kind == "unknown")
        required = all(matched.intersection(group) for group in label.get("required", []))
        ocr_preserved = not label.get("ocr") or any(
            cite["extraction_method"] == "ocr"
            and cite["time_confidence"] == "uncertain"
            and cite["event_time_raw"]
            and "event_time_normalized" not in cite
            and "original page" in item.get("uncertainty", "")
            for cite in citations
        )
        relation_grounded = (
            kind != "corroboration" or len({cite["source_id"] for cite in evidence}) >= 2
        ) and (kind != "contradiction" or bool(evidence and opposing))
        kinds = label["kinds"]
        target_met = (
            kind in kinds
            and grounded
            and required
            and ocr_preserved
            and relation_grounded
            and abstained == expected_abstention
        )
        claim = bool(item) and kind not in {"unknown", "insufficient_evidence"}
        supported_claim = (
            grounded
            and ocr_preserved
            and relation_grounded
            and ((kind in kinds and required) or kind in label.get("grounded_kinds", []))
        )
        comparisons.append(
            {
                "objective_id": objective,
                "challenge": label["challenge"],
                "kind": actual_kind,
                "target_met": target_met,
                "expected_abstention": expected_abstention,
                "abstained": abstained,
                "cross_source_target": label.get("cross_source", False),
                "expected_conflict": "contradiction" in kinds,
                "classified_conflict": kind == "contradiction",
                "unsupported_claim": claim and not supported_claim,
                "advisory_returned": claim,
                "citation_examples": citations,
                "unknowns": item.get("unknowns", []),
            }
        )
    return comparisons


def score_metrics(outcomes: list[dict]) -> dict:
    labels = [item for case in outcomes for item in case["developer_label_comparison"]]
    positives = sum(item["expected_abstention"] and item["abstained"] for item in labels)
    hybrid = [case["hybrid"] for case in outcomes]
    return {
        "target_behavior": [sum(item["target_met"] for item in labels), len(labels)],
        "cross_source_matching": [
            sum(item["cross_source_target"] and item["target_met"] for item in labels),
            sum(item["cross_source_target"] for item in labels),
        ],
        "true_conflict_detection": [
            sum(item["expected_conflict"] and item["target_met"] for item in labels),
            sum(item["expected_conflict"] for item in labels),
        ],
        "false_conflict_rate": [
            sum(item["classified_conflict"] and not item["expected_conflict"] for item in labels),
            sum(not item["expected_conflict"] for item in labels),
        ],
        "abstention_precision": [positives, sum(item["abstained"] for item in labels)],
        "abstention_recall": [positives, sum(item["expected_abstention"] for item in labels)],
        "unsupported_claim_rate": [
            sum(item["unsupported_claim"] for item in labels),
            sum(item["advisory_returned"] for item in labels),
        ],
        "exact_citation_validation": [
            sum(item["citations_matched"] or 0 for item in hybrid),
            sum(item["citations_attempted"] or 0 for item in hybrid),
        ],
        "deterministic_detail_preserved": [
            sum(
                case["deterministic"]["entire_exercise_detail_unchanged_after_ai_request"]
                for case in outcomes
            ),
            len(outcomes),
        ],
        "latency_ms": [item["latency_ms"] for item in hybrid],
        "input_tokens": [item["input_tokens"] for item in hybrid],
        "output_tokens": [item["output_tokens"] for item in hybrid],
    }


def verify_fabricated_citations(client, exercise_id: str) -> dict:
    from app.ai_evaluation import ModelSuggestion, ProviderReply

    path = f"{BASE}/{exercise_id}"
    before = expect(client.get(path), 200)
    service = client.app.state.ai_evaluation
    real_provider = service.provider
    references = [
        {"record": 99, "excerpt": "The supervisor signed the register."},
        {"record": 1, "excerpt": "A second invented sentence."},
    ]
    attempted = {
        "objective_id": "SIGNED-REGISTER",
        "kind": "relevant_observation",
        "missing_information": [],
        **(
            {"citations": references}
            if "citations" in ModelSuggestion.model_fields
            else {"evidence": references, "counterevidence": []}
        ),
    }

    class ScriptedReply:
        def __init__(self, result):
            self.result = result

        async def generate(self, *_):
            return ProviderReply(json.dumps({"suggestions": [self.result]}))

    try:
        service.provider = ScriptedReply(attempted)
        citations = expect(client.post(f"{path}/ai-suggestions"), 200)
        service.provider = ScriptedReply(
            {**attempted, "status": "approved", "action": "Close D-23"}
        )
        response = client.post(f"{path}/ai-suggestions")
        outcome = expect(response, 502)
    finally:
        service.provider = real_provider
    return {
        "fabricated_and_out_of_context_citations_withheld": (
            not citations["suggestions"]
            and citations["rejected_suggestion_count"] == 1
            and citations["citations_attempted"] == 2
            and citations["citations_matched"] == 0
        ),
        "forbidden_workflow_fields_rejected": outcome["detail"]["code"] == "AI_INVALID_RESPONSE",
        "deterministic_detail_preserved": before == expect(client.get(path), 200),
    }


def paired_metadata(client, backend_root: Path) -> dict:
    import httpx
    from app import ai_evaluation as ai

    settings = ai.AiSettings.from_environment()
    with httpx.Client(base_url=settings.endpoint, trust_env=False, timeout=10) as daemon:
        version = daemon.get("/api/version").raise_for_status().json()["version"]
        models = daemon.get("/api/tags").raise_for_status().json()["models"]
        digest = next(model["digest"] for model in models if model["name"] == settings.model)

    # Pin context capacity for both versions. The production provider normally derives it
    # from prompt size. Leave every other request and response on the real provider path.
    request = ai.OllamaProvider._request
    calls = []

    async def fixed_context(http, method, path, **kwargs):
        if path == "/api/chat":
            body = kwargs["json"]
            body["options"]["num_ctx"] = 8192
            calls.append({"think": body["think"], "stream": body["stream"], **body["options"]})
        return await request(http, method, path, **kwargs)

    ai.OllamaProvider._request = staticmethod(fixed_context)
    assert client.app.state.ai_evaluation.settings == settings
    return {
        "backend_commit": subprocess.check_output(
            ["git", "-C", str(backend_root), "rev-parse", "HEAD"], text=True
        ).strip(),
        "backend_has_local_changes": bool(
            subprocess.check_output(
                [
                    "git",
                    "-C",
                    str(backend_root),
                    "status",
                    "--porcelain",
                    "--untracked-files=no",
                    "backend",
                ]
            )
        ),
        "backend_ai_sha256": hashlib.sha256(
            (backend_root / "backend/app/ai_evaluation.py").read_bytes()
        ).hexdigest(),
        "ollama_version": version,
        "model": settings.model,
        "model_digest": digest,
        "prompt_version": getattr(ai, "PROMPT_VERSION", "phase4a"),
        "prompt_sha256": hashlib.sha256(ai.SYSTEM_PROMPT.encode()).hexdigest(),
        "max_input_bytes": settings.max_input_bytes,
        "timeout_seconds": settings.timeout_seconds,
        "inference_calls": calls,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path)
    parser.add_argument("--suite", choices=("phase4a", "phase4b"), default="phase4a")
    parser.add_argument("--repeat", type=int, default=1)
    parser.add_argument("--backend-root", type=Path, default=ROOT)
    parser.add_argument(
        "--serve", action="store_true", help="Serve the synthetic exercises before upload."
    )
    parser.add_argument("--port", type=int, default=8000)
    args = parser.parse_args()
    if args.output and args.output.exists():
        parser.error("Output must be a new file.")
    if args.repeat < 1 or (args.repeat != 1 and args.suite == "phase4a"):
        parser.error("Repeats require Phase 4B and a positive count.")
    labeling, cases = load_cases(args.suite)
    backend_root = args.backend_root.resolve()
    configure(backend_root / "backend")

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
            metadata = paired_metadata(client, backend_root) if args.suite == "phase4b" else {}
            prepared = [prepare_case(client, case) for case in cases]
            outcomes = [
                evaluate_case(client, case, fixture, args.suite)
                for _ in range(args.repeat)
                for case, fixture in zip(cases, prepared, strict=True)
            ]
            if args.suite == "phase4b":
                probes = verify_fabricated_citations(client, "PH4A-FICTIONAL-NARRATIVE")
        else:
            for case in cases:
                expect(client.post(BASE, json=case["exercise"]), 201)

    if args.serve:
        import uvicorn

        print(
            f"Fictional {args.suite} exercises ready at http://127.0.0.1:{args.port}.", flush=True
        )
        uvicorn.run(app, host="127.0.0.1", port=args.port, log_level="warning")
        return

    result = {"fictional": True, "labeling": labeling, "real_inference": True, "cases": outcomes}
    if args.suite == "phase4b":
        result.update(
            run_metadata=metadata,
            repetitions=args.repeat,
            metrics=score_metrics(outcomes),
            scripted_provider_probes=probes,
        )
    rendered = json.dumps(result, indent=2) + "\n"
    if args.output:
        with args.output.open("x", encoding="utf-8") as output:
            output.write(rendered)
    else:
        print(rendered, end="")


if __name__ == "__main__":
    main()
