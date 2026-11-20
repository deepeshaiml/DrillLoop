#!/usr/bin/env python3
"""Measure OCR on paired fictional PDFs and exercise the isolated application workflow."""

from __future__ import annotations

import argparse
import hashlib
import io
import json
import os
import re
import resource
import subprocess
import sys
import time
from collections import Counter
from datetime import UTC, date, datetime
from difflib import SequenceMatcher
from io import BytesIO
from pathlib import Path

from pypdf import PdfReader

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from scripts.isolated_runtime import configure  # noqa: E402

TEMP_ROOT = configure()

from app import db as database  # noqa: E402
from app.evidence import (  # noqa: E402
    MAX_PDF_PAGES,
    PREFIX_TIME_RE,
    ParsedEvidence,
    ParsedObservation,
    normalize_time,
)
from app.main import app  # noqa: E402
from app.pdf_ocr import check_pdf_ocr_runtime  # noqa: E402
from app.upload_processing import UploadProcessingFailure, process_upload_isolated  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402

FIXTURE_LABELS = ROOT / "evals" / "phase2" / "ground_truth.json"
EXERCISE_DATE = date(2026, 11, 13)
MATCH_THRESHOLD = 0.6


def _norm(value: str) -> str:
    return re.sub(r"\s+", " ", value).strip().casefold()


def _source_line(value: str) -> tuple[str | None, str]:
    match = PREFIX_TIME_RE.match(value)
    if not match:
        return None, value.strip()
    return (match.group(1) or match.group(2)), (match.group(3) or "").strip()


def _edit_distance(left: list, right: list) -> int:
    previous = list(range(len(right) + 1))
    for row_index, left_item in enumerate(left, 1):
        current = [row_index]
        for column_index, right_item in enumerate(right, 1):
            current.append(
                min(
                    current[-1] + 1,
                    previous[column_index] + 1,
                    previous[column_index - 1] + (left_item != right_item),
                )
            )
        previous = current
    return previous[-1]


def _error_rate(expected: str, actual: str, *, word: bool) -> dict:
    expected_norm = _norm(expected)
    actual_norm = _norm(actual)
    expected_units = expected_norm.split() if word else list(expected_norm)
    actual_units = actual_norm.split() if word else list(actual_norm)
    errors = _edit_distance(expected_units, actual_units)
    denominator = len(expected_units)
    return {
        "errors": errors,
        "reference_units": denominator,
        "rate": round(errors / denominator, 4) if denominator else None,
        "definition": "casefolded, whitespace-normalized words"
        if word
        else "casefolded, whitespace-normalized characters",
    }


def _read_page_text(content_text: str) -> dict[int, str]:
    pages: dict[int, str] = {}
    current_page: int | None = None
    lines = content_text.splitlines()
    for line in lines:
        marker = re.fullmatch(r"\[page (\d+)\]", line.strip())
        if marker:
            current_page = int(marker.group(1))
            pages[current_page] = ""
        elif current_page is not None:
            pages[current_page] += ("\n" if pages[current_page] else "") + line
    return pages


def _locator_page(locator: str) -> int | None:
    match = re.match(r"page (\d+)", locator)
    return int(match.group(1)) if match else None


def _fixture_metrics(document: dict, parsed, processing_seconds: float) -> dict:
    actual_pages = _read_page_text(parsed.content_text)
    expected_by_page = {row["page"]: row for row in document["pages"]}
    expected_text_by_page = {
        page: "\n".join(row["source_lines"])
        for page, row in expected_by_page.items()
        if row.get("recognition_metrics_available", True)
    }
    actual_observations = [
        {
            "page": _locator_page(row.source_locator),
            "text": row.text,
            "event_time_raw": row.event_time_raw,
            "time_confidence": row.time_confidence,
            "source_locator": row.source_locator,
            "extraction_method": row.extraction_method,
        }
        for row in parsed.observations
    ]
    expected_observations = []
    for page, label in expected_by_page.items():
        if not label.get("recognition_metrics_available", True):
            continue
        for line in label["source_lines"]:
            raw_time, wording = _source_line(line)
            expected_observations.append({"page": page, "text": wording, "time": raw_time})

    unused_actual = set(range(len(actual_observations)))
    matched_lines = []
    missing_lines = []
    incorrect_assignments = []
    timestamp_matches = 0
    for expected in expected_observations:
        ranked = sorted(
            (
                (
                    SequenceMatcher(
                        None, _norm(expected["text"]), _norm(actual_observations[index]["text"])
                    ).ratio(),
                    actual_observations[index]["page"] == expected["page"],
                    index,
                )
                for index in unused_actual
            ),
            reverse=True,
        )
        score, _same_page, selected = ranked[0] if ranked else (0.0, False, -1)
        if score < MATCH_THRESHOLD:
            missing_lines.append(expected)
            continue
        unused_actual.remove(selected)
        actual = actual_observations[selected]
        row = {
            "expected_page": expected["page"],
            "actual_page": actual["page"],
            "expected_text": expected["text"],
            "actual_text": actual["text"],
            "text_similarity": round(score, 4),
            "expected_timestamp": expected["time"],
            "actual_timestamp": actual["event_time_raw"],
        }
        matched_lines.append(row)
        if expected["time"] is not None and actual["event_time_raw"] == expected["time"]:
            timestamp_matches += 1
        if expected["page"] != actual["page"] or expected["time"] != actual["event_time_raw"]:
            incorrect_assignments.append(row)

    page_methods = {
        row["page"]: (row["method"], row["status"])
        for row in parsed.provenance.get("page_extraction", [])
    }
    method_expected_pages = {
        page: expected
        for page, expected in expected_by_page.items()
        if expected.get("method") in {"native_text", "ocr", "native_text_plus_ocr"}
        and expected.get("recognition_metrics_available", True)
    }
    page_method_matches = sum(
        page_methods.get(page, (None, None))[0] == expected["method"]
        for page, expected in method_expected_pages.items()
    )
    duplicate_keys = Counter(
        (row["page"], _norm(row["text"]), row["event_time_raw"]) for row in actual_observations
    )
    duplicate_count = sum(count - 1 for count in duplicate_keys.values())
    expected_timestamps = sum(1 for row in expected_observations if row["time"] is not None)
    expected_unknown_lines = []
    for source_line_label in document.get("expected_unknown_source_lines", []):
        source_line = (
            source_line_label["text"] if isinstance(source_line_label, dict) else source_line_label
        )
        page = next(
            (
                source_line_label.get("page") if isinstance(source_line_label, dict) else page
                for page, label in expected_by_page.items()
                if source_line in label["source_lines"]
            ),
            None,
        )
        if page is not None:
            expected_unknown_lines.append({"page": page, "text": source_line})
    unknown_observed = sum(
        not any(
            row["page"] == expected["page"]
            and SequenceMatcher(
                None, _norm(row["text"]), _norm(_source_line(expected["text"])[1])
            ).ratio()
            >= MATCH_THRESHOLD
            and row["event_time_raw"] is None
            for row in actual_observations
        )
        for expected in expected_unknown_lines
    )

    expected_flat = "\n".join(expected_text_by_page.values())
    actual_flat = "\n".join(actual_pages.get(page, "") for page in expected_text_by_page)
    required_citations = document.get("required_citations", [])
    citation_matches = []
    for citation in required_citations:
        expected_time, expected_text = _source_line(citation["source_line"])
        matched = any(
            row["page"] == citation["page"]
            and SequenceMatcher(None, _norm(row["text"]), _norm(expected_text)).ratio()
            >= MATCH_THRESHOLD
            and (expected_time is None or row["event_time_raw"] == expected_time)
            for row in actual_observations
        )
        citation_matches.append(matched)
    repeated_event_groups = []
    for group in document.get("repeated_event_groups", []):
        matched_pages = []
        for claim in group["source_lines"]:
            expected_time, expected_text = _source_line(claim["text"])
            if any(
                row["page"] == claim["page"]
                and SequenceMatcher(None, _norm(row["text"]), _norm(expected_text)).ratio()
                >= MATCH_THRESHOLD
                and (expected_time is None or row["event_time_raw"] == expected_time)
                for row in actual_observations
            ):
                matched_pages.append(claim["page"])
        repeated_event_groups.append(
            {
                "event_key": group["event_key"],
                "expected_pages": [claim["page"] for claim in group["source_lines"]],
                "recognized_pages": matched_pages,
                "kept_separate_by_page": len(matched_pages) == len(group["source_lines"])
                and len(set(matched_pages)) == len(matched_pages),
            }
        )
    recognition_available = bool(expected_text_by_page)
    return {
        "filename": document["filename"],
        "variant": document["variant"],
        "sha256": hashlib.sha256((ROOT / document["path"]).read_bytes()).hexdigest(),
        "extraction": parsed.provenance,
        "metrics": {
            "character_error_rate": _error_rate(expected_flat, actual_flat, word=False)
            if recognition_available
            else None,
            "word_error_rate": _error_rate(expected_flat, actual_flat, word=True)
            if recognition_available
            else None,
            "page_method_attribution": {
                "matched": page_method_matches,
                "expected": len(method_expected_pages),
                "accuracy": round(page_method_matches / len(method_expected_pages), 4)
                if method_expected_pages
                else None,
            },
            "observation_source_attribution": {
                "correct_page": sum(
                    row["expected_page"] == row["actual_page"] for row in matched_lines
                ),
                "recognized_expected_lines": len(matched_lines),
                "accuracy": round(
                    sum(row["expected_page"] == row["actual_page"] for row in matched_lines)
                    / len(matched_lines),
                    4,
                )
                if matched_lines
                else None,
            },
            "timestamps": {
                "matched_with_source_line": timestamp_matches,
                "expected": expected_timestamps,
                "accuracy": round(timestamp_matches / expected_timestamps, 4)
                if expected_timestamps
                else None,
                "time_uncertain_count": sum(
                    row["event_time_raw"] is not None and row["time_confidence"] == "uncertain"
                    for row in actual_observations
                ),
                "expected_unknown_lines_preserved_without_time": len(expected_unknown_lines)
                - unknown_observed,
                "expected_unknown_information_lines": len(expected_unknown_lines),
                "unknown_lines_missing_or_assigned_a_time": unknown_observed,
            },
            "observations": {
                "metrics_available": recognition_available,
                "matched": len(matched_lines),
                "expected": len(expected_observations),
                "precision": (
                    round(len(matched_lines) / len(actual_observations), 4)
                    if actual_observations
                    else (1.0 if not expected_observations else 0.0)
                )
                if recognition_available
                else None,
                "recall": round(len(matched_lines) / len(expected_observations), 4)
                if expected_observations
                else 1.0
                if recognition_available
                else None,
                "missed": missing_lines,
                "unmatched_actual": [actual_observations[index] for index in sorted(unused_actual)],
                "duplicate_observations": duplicate_count,
                "incorrect_event_assignments": incorrect_assignments,
                "unsupported_observations": len(unused_actual),
                "repeated_events": repeated_event_groups,
            },
            "required_citations": {
                "matched": sum(citation_matches),
                "expected": len(citation_matches),
                "recall": round(sum(citation_matches) / len(citation_matches), 4)
                if citation_matches
                else None,
            },
            "processing": {
                "isolated_worker_wall_seconds": round(processing_seconds, 4),
                "ocr_wall_seconds": parsed.provenance.get("ocr_duration_seconds", 0),
                "ocr_page_seconds": parsed.provenance.get("ocr_page_durations_seconds", {}),
            },
        },
    }


def _processing_failure_metrics(document: dict, code: str, message: str, seconds: float) -> dict:
    return {
        "filename": document["filename"],
        "variant": document["variant"],
        "sha256": hashlib.sha256((ROOT / document["path"]).read_bytes()).hexdigest(),
        "processing_error": {"code": code, "message": message},
        "metrics": {
            "character_error_rate": None,
            "word_error_rate": None,
            "page_method_attribution": {"matched": 0, "expected": 0, "accuracy": None},
            "observation_source_attribution": {
                "correct_page": 0,
                "recognized_expected_lines": 0,
                "accuracy": None,
            },
            "timestamps": {"matched_with_source_line": 0, "expected": 0, "accuracy": None},
            "observations": {
                "metrics_available": False,
                "matched": 0,
                "expected": 0,
                "precision": None,
                "recall": None,
                "missed": [],
                "unmatched_actual": [],
                "duplicate_observations": 0,
                "incorrect_event_assignments": [],
                "unsupported_observations": 0,
            },
            "required_citations": {"matched": 0, "expected": 0, "recall": None},
            "processing": {
                "isolated_worker_wall_seconds": round(seconds, 4),
                "ocr_wall_seconds": None,
            },
        },
    }


def _phase2_baseline_metrics(document: dict, runtime, exercise_date: date) -> dict:
    """Reproduce Phase 2's native-page skip and scanned-page PSM 6 policy for comparison."""
    import pypdfium2 as pdfium

    source_path = ROOT / document["path"]
    source_bytes = source_path.read_bytes()
    reader = PdfReader(io.BytesIO(source_bytes), strict=True)
    if len(reader.pages) > MAX_PDF_PAGES:
        raise RuntimeError(f"Baseline PDF exceeds the existing {MAX_PDF_PAGES}-page limit.")
    started = time.perf_counter()
    pages = []
    page_extraction = []
    ocr_pages = []
    ocr_durations = {}
    render_document = pdfium.PdfDocument(source_bytes)
    try:
        for index, source_page in enumerate(reader.pages):
            native_text = (source_page.extract_text() or "").strip()
            if native_text:
                pages.append(native_text)
                page_extraction.append(
                    {"page": index + 1, "method": "native_text", "status": "skipped"}
                )
                continue
            page = render_document[index]
            try:
                width_points, height_points = page.get_size()
                width_pixels = int(width_points * 200 / 72 + 0.999)
                height_pixels = int(height_points * 200 / 72 + 0.999)
                if width_pixels * height_pixels > 12_000_000:
                    raise RuntimeError(
                        f"Baseline PDF page {index + 1} exceeds the OCR pixel limit."
                    )
                bitmap = page.render(scale=200 / 72, grayscale=True, limit_image_cache=True)
                image = bitmap.to_pil()
                image_bytes = io.BytesIO()
                image.save(image_bytes, format="PNG", optimize=False)
                image.close()
                bitmap.close()
            finally:
                page.close()
            ocr_started = time.perf_counter()
            result = subprocess.run(
                [runtime.command, "stdin", "stdout", "-l", "eng", "--psm", "6"],
                input=image_bytes.getvalue(),
                capture_output=True,
                timeout=4,
                check=False,
                env={**os.environ, "OMP_THREAD_LIMIT": "1", "OMP_NUM_THREADS": "1"},
            )
            if result.returncode != 0:
                raise RuntimeError(f"Phase 2 baseline OCR failed on page {index + 1}.")
            text = result.stdout.decode("utf-8", errors="replace").strip()
            pages.append(text)
            page_extraction.append(
                {
                    "page": index + 1,
                    "method": "ocr",
                    "status": "completed" if text else "completed_empty",
                }
            )
            ocr_pages.append(index + 1)
            ocr_durations[index + 1] = round(time.perf_counter() - ocr_started, 4)
    finally:
        render_document.close()

    observations = []
    for page_number, (page_text, extraction) in enumerate(
        zip(pages, page_extraction, strict=True), 1
    ):
        method = "ocr" if extraction["method"] == "ocr" else "parser"
        for line_number, line in enumerate(page_text.splitlines(), 1):
            if not line.strip():
                continue
            raw_time, wording = _source_line(line)
            normalized, certainty = normalize_time(raw_time, exercise_date)
            if method == "ocr" and raw_time:
                certainty = "uncertain"
            observations.append(
                ParsedObservation(
                    text=wording,
                    event_time_raw=raw_time,
                    event_time_normalized=normalized,
                    time_confidence=certainty,
                    source_locator=f"page {page_number}"
                    if method == "ocr"
                    else f"page {page_number}, line {line_number}",
                    observation_type="document",
                    extraction_method=method,
                )
            )
    content = "\n".join(f"[page {index + 1}]\n{text}" for index, text in enumerate(pages))
    parsed = ParsedEvidence(
        kind="pdf",
        content_text=content,
        observations=observations,
        provenance={
            "page_extraction": page_extraction,
            "ocr_pages": ocr_pages,
            "ocr_duration_seconds": round(sum(ocr_durations.values()), 4),
            "ocr_page_durations_seconds": ocr_durations,
        },
    )
    metrics = _fixture_metrics(document, parsed, time.perf_counter() - started)
    if not any(pages):
        metrics["processing_outcome"] = "accepted_without_readable_text_under_phase2_policy"
    return metrics


def _aggregate_metrics(fixture_results: list[dict]) -> dict:
    metrics = [row["metrics"] for row in fixture_results]
    text_metrics = [row for row in metrics if row["character_error_rate"] is not None]
    observation_metrics = [
        row["observations"] for row in metrics if row["observations"]["metrics_available"]
    ]
    timestamp_metrics = [row["timestamps"] for row in metrics if row["timestamps"]["expected"]]
    page_metrics = [
        row["page_method_attribution"]
        for row in metrics
        if row["page_method_attribution"]["expected"]
    ]
    citation_metrics = [
        row["required_citations"] for row in metrics if row["required_citations"]["expected"]
    ]

    def micro_error_rate(key: str) -> dict | None:
        values = [row[key] for row in text_metrics if row[key] is not None]
        if not values:
            return None
        errors = sum(value["errors"] for value in values)
        units = sum(value["reference_units"] for value in values)
        return {
            "errors": errors,
            "reference_units": units,
            "rate": round(errors / units, 4) if units else None,
        }

    matched_observations = sum(row["matched"] for row in observation_metrics)
    expected_observations = sum(row["expected"] for row in observation_metrics)
    actual_observations = sum(
        row["matched"] + len(row["unmatched_actual"]) for row in observation_metrics
    )
    matched_timestamps = sum(row["matched_with_source_line"] for row in timestamp_metrics)
    expected_timestamps = sum(row["expected"] for row in timestamp_metrics)
    matched_pages = sum(row["matched"] for row in page_metrics)
    expected_pages = sum(row["expected"] for row in page_metrics)
    matched_citations = sum(row["matched"] for row in citation_metrics)
    expected_citations = sum(row["expected"] for row in citation_metrics)
    return {
        "character_error_rate_micro": micro_error_rate("character_error_rate"),
        "word_error_rate_micro": micro_error_rate("word_error_rate"),
        "observation_precision_micro": round(matched_observations / actual_observations, 4)
        if actual_observations
        else None,
        "observation_recall_micro": round(matched_observations / expected_observations, 4)
        if expected_observations
        else None,
        "observation_counts": {
            "matched": matched_observations,
            "expected": expected_observations,
            "actual": actual_observations,
        },
        "timestamp_accuracy_micro": round(matched_timestamps / expected_timestamps, 4)
        if expected_timestamps
        else None,
        "timestamp_counts": {"matched": matched_timestamps, "expected": expected_timestamps},
        "page_method_attribution_micro": round(matched_pages / expected_pages, 4)
        if expected_pages
        else None,
        "page_method_counts": {"matched": matched_pages, "expected": expected_pages},
        "required_citation_recall_micro": round(matched_citations / expected_citations, 4)
        if expected_citations
        else None,
        "required_citation_counts": {"matched": matched_citations, "expected": expected_citations},
        "duplicate_observations": sum(
            row["observations"]["duplicate_observations"] for row in metrics
        ),
        "unsupported_observations": sum(
            row["observations"]["unsupported_observations"] for row in metrics
        ),
        "metrics_documents": len(fixture_results),
        "recognition_scored_documents": len(text_metrics),
        "recognition_unavailable_documents": len(fixture_results) - len(text_metrics),
        "latency_seconds_per_document": {
            row["filename"]: row["metrics"]["processing"]["isolated_worker_wall_seconds"]
            for row in fixture_results
        },
    }


def _api_workflow(scanned_document: dict, labels: dict) -> dict:
    exercise_id = "OCR-PHASE2-DEMO"
    source_path = ROOT / scanned_document["path"]
    source_bytes = source_path.read_bytes()
    database.migrate_database()
    with TestClient(app) as client:
        login = client.post(
            "/api/auth/login",
            json={
                "username": "evaluation-admin",
                "password": "synthetic-evaluation-only-password",
            },
        )
        if login.status_code != 200:
            raise RuntimeError(f"OCR demo login failed: HTTP {login.status_code}")
        client.headers.update({"X-CSRF-Token": login.json()["csrf_token"]})
        created = client.post(
            "/api/exercises",
            json={
                "id": exercise_id,
                "title": "Fictional water utility scanned-PDF exercise",
                "scenario": "A wholly fictional OCR workflow fixture for evidence traceability.",
                "exercise_date": EXERCISE_DATE.isoformat(),
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
            raise RuntimeError(f"OCR demo exercise setup failed: HTTP {created.status_code}")
        uploaded = client.post(
            f"/api/exercises/{exercise_id}/evidence",
            files={"files": (source_path.name, source_bytes, "application/pdf")},
        )
        if uploaded.status_code != 201:
            raise RuntimeError(
                f"Scanned PDF upload failed: HTTP {uploaded.status_code}: {uploaded.text}"
            )
        source_id = uploaded.json()["sources"][0]["id"]
        source = client.get(f"/api/sources/{source_id}/download")
        if source.status_code != 200 or source.content != source_bytes:
            raise RuntimeError("The original uploaded PDF was not preserved byte for byte.")
        analyzed = client.post(f"/api/exercises/{exercise_id}/analyze")
        if analyzed.status_code != 200:
            raise RuntimeError(f"OCR objective analysis failed: HTTP {analyzed.status_code}")
        detail = client.get(f"/api/exercises/{exercise_id}")
        if detail.status_code != 200:
            raise RuntimeError(f"OCR exercise detail failed: HTTP {detail.status_code}")
        payload = detail.json()
        report = client.get(f"/api/exercises/{exercise_id}/report.pdf")
        if report.status_code != 200 or report.headers.get("content-type") != "application/pdf":
            raise RuntimeError("OCR exercise report export failed.")
        report_text = "\n".join(
            page.extract_text() or "" for page in PdfReader(BytesIO(report.content)).pages
        )

    source_record = payload["sources"][0]
    finding = next(
        (row for row in payload["findings"] if row["code"] == "STATION_B_RESTORED"), None
    )
    assessments = {row["objective_id"]: row for row in payload["objective_assessments"]}
    pressure_assessment = assessments.get("OBJ-PRESSURE-15", {})
    presence_assessment = assessments.get("OBJ-STATION-B", {})
    expected_citation = labels["objective_labels"][1]["expected_citation"]
    cited = [] if finding is None else finding["supporting_evidence"]
    citation_matches = any(
        row["source_filename"] == expected_citation["source"]
        and row["source_locator"] == expected_citation["locator"]
        for row in cited
    )
    return {
        "workflow": [
            "fictional exercise created in disposable SQLite database",
            "image-only PDF passed through upload scan boundary and isolated OCR parser",
            "original PDF was byte-for-byte downloadable",
            "page-cited OCR observations entered the timeline",
            "existing objective rules ran without threshold changes",
            "source-linked finding remained proposed with no reviewer decision",
            "PDF report exported",
        ],
        "source": {
            "filename": source_record["filename"],
            "sha256_matches_original": source_record["sha256"]
            == hashlib.sha256(source_bytes).hexdigest(),
            "scan_status": source_record["scan_status"],
            "ocr_status": source_record["provenance"].get("ocr_status"),
            "ocr_pages": source_record["provenance"].get("ocr_pages"),
            "timeline_observations": len(
                [row for row in payload["timeline"] if row["source_id"] == source_id]
            ),
        },
        "objective_assessments": {
            "elapsed_time": {
                "state": pressure_assessment.get("state"),
                "elapsed_seconds": pressure_assessment.get("elapsed_seconds"),
                "unknowns": pressure_assessment.get("unknowns"),
            },
            "station_b_presence": {
                "state": presence_assessment.get("state"),
                "expected": "confirmed_success",
            },
        },
        "finding": {
            "present": finding is not None,
            "code": finding.get("code") if finding else None,
            "status": finding.get("status") if finding else None,
            "reviewer_decision": finding.get("reviewer") if finding else None,
            "citation_page_matches_label": citation_matches,
            "citations": [
                {"filename": row["source_filename"], "locator": row["source_locator"]}
                for row in cited
            ],
        },
        "report": {
            "status": "exported",
            "content_type": "application/pdf",
            "contains_finding_title": bool(finding and finding["title"] in report_text),
            "contains_page_citation": "page 2" in report_text.casefold(),
        },
    }


def _duplicate_upload_check(
    scanned_document: dict, exercise_id: str = "OCR-PHASE2-DUPLICATE"
) -> dict:
    source_path = ROOT / scanned_document["path"]
    source_bytes = source_path.read_bytes()
    database.migrate_database()
    with TestClient(app) as client:
        login = client.post(
            "/api/auth/login",
            json={
                "username": "evaluation-admin",
                "password": "synthetic-evaluation-only-password",
            },
        )
        client.headers.update({"X-CSRF-Token": login.json()["csrf_token"]})
        created = client.post(
            "/api/exercises",
            json={
                "id": exercise_id,
                "title": "Fictional duplicate upload check",
                "scenario": "A disposable synthetic duplicate-upload behavior check.",
                "exercise_date": EXERCISE_DATE.isoformat(),
                "duration_minutes": 30,
                "objectives": [{"id": "OBJ-01", "text": "Review source evidence."}],
            },
        )
        if created.status_code != 201:
            raise RuntimeError("Could not create disposable duplicate-upload exercise.")
        ids = []
        for _ in range(2):
            uploaded = client.post(
                f"/api/exercises/{exercise_id}/evidence",
                files={"files": (source_path.name, source_bytes, "application/pdf")},
            )
            if uploaded.status_code != 201:
                raise RuntimeError("Repeated synthetic PDF upload failed unexpectedly.")
            ids.append(uploaded.json()["sources"][0]["id"])
        detail = client.get(f"/api/exercises/{exercise_id}").json()
        sources = detail["sources"]
        source_ids = {row["id"] for row in sources}
        observations_per_source = Counter(row["source_id"] for row in detail["timeline"])
        observation_duplicates = Counter(
            (row["source_id"], _norm(row["text"]), row["event_time_raw"], row["source_locator"])
            for row in detail["timeline"]
        )
        return {
            "same_file_uploads_are_separate_sources": len(sources) == 2 and len(source_ids) == 2,
            "observations_per_source": dict(observations_per_source),
            "within_source_duplicate_observation_count": sum(
                count - 1 for count in observation_duplicates.values() if count > 1
            ),
            "behavior": "Each explicit upload creates a distinct source record; identical-file deduplication is not implemented.",
        }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--labels",
        default=str(FIXTURE_LABELS),
        help="Fictional ground-truth JSON (defaults to the Phase 2 dataset).",
    )
    parser.add_argument(
        "--skip-application-workflow",
        action="store_true",
        help="Measure extraction only; do not create disposable application exercises.",
    )
    parser.add_argument(
        "--compare-phase2-baseline",
        action="store_true",
        help="Run the Phase 2 native-skip/PSM 6 extraction policy on the same fixtures and labels.",
    )
    parser.add_argument(
        "--verify-duplicate-upload",
        action="store_true",
        help="Upload one fictional fixture twice through the disposable application API.",
    )
    parser.add_argument(
        "--output", help="Write a new JSON result file; existing paths are refused."
    )
    args = parser.parse_args()
    label_path = Path(args.labels).expanduser()
    if not label_path.is_absolute():
        label_path = ROOT / label_path
    labels = json.loads(label_path.read_text(encoding="utf-8"))
    if labels.get("fictional") is not True:
        raise SystemExit("OCR evaluation accepts only explicitly fictional fixtures.")
    exercise_date = date.fromisoformat(labels.get("exercise_date", EXERCISE_DATE.isoformat()))
    runtime, _ = check_pdf_ocr_runtime()
    fixture_results = []
    phase2_baseline_results = []
    for document in labels["documents"]:
        source = ROOT / document["path"]
        if (
            not source.is_file()
            or hashlib.sha256(source.read_bytes()).hexdigest() != document["sha256"]
        ):
            raise SystemExit(f"Fictional source is missing or changed: {document['path']}")
        expected_error = document.get("expected_processing_error")
        start = time.perf_counter()
        usage_before = resource.getrusage(resource.RUSAGE_CHILDREN)
        try:
            parsed, scan = process_upload_isolated(
                document["filename"],
                "application/pdf",
                source.read_bytes(),
                exercise_date,
            )
        except UploadProcessingFailure as exc:
            if exc.code != expected_error:
                raise SystemExit(
                    f"{document['filename']}: unexpected extraction error {exc.code}: {exc.message}"
                ) from exc
            result = _processing_failure_metrics(
                document, exc.code, exc.message, time.perf_counter() - start
            )
            result["scan_status"] = exc.details.get("scan_status", "unknown")
        else:
            if expected_error is not None:
                raise SystemExit(
                    f"{document['filename']}: expected extraction error {expected_error}, got an import."
                )
            if parsed.kind != "pdf":
                raise RuntimeError(
                    f"Unexpected evidence kind for {document['filename']}: {parsed.kind}"
                )
            result = _fixture_metrics(document, parsed, time.perf_counter() - start)
            result["scan_status"] = scan.status
        usage_after = resource.getrusage(resource.RUSAGE_CHILDREN)
        result["metrics"]["processing"]["isolated_parser_child_cpu_seconds"] = round(
            usage_after.ru_utime
            + usage_after.ru_stime
            - usage_before.ru_utime
            - usage_before.ru_stime,
            4,
        )
        fixture_results.append(result)
        if args.compare_phase2_baseline:
            phase2_baseline_results.append(
                _phase2_baseline_metrics(document, runtime, exercise_date)
            )

    workflow = {"status": "not_run", "reason": "--skip-application-workflow"}
    duplicates = {"status": "not_run", "reason": "--skip-application-workflow"}
    if not args.skip_application_workflow:
        scanned_document = next(
            (row for row in labels["documents"] if row["variant"] == "image_only_scan"), None
        )
        if scanned_document is None:
            raise SystemExit(
                "This label set has no image_only_scan demo. Use --skip-application-workflow "
                "or run its dedicated application walkthrough."
            )
        workflow = _api_workflow(scanned_document, labels)
        duplicates = _duplicate_upload_check(scanned_document)
    elif args.verify_duplicate_upload:
        duplicate_document = next(
            (
                row
                for row in labels["documents"]
                if row["variant"] == "same_page_native_plus_scanned_image"
            ),
            labels["documents"][0],
        )
        duplicates = _duplicate_upload_check(duplicate_document, exercise_id="OCR-PHASE3-DUPLICATE")
    usage = resource.getrusage(resource.RUSAGE_CHILDREN)
    max_rss = usage.ru_maxrss
    max_rss_bytes = int(max_rss if sys.platform == "darwin" else max_rss * 1024)
    native = next((row for row in fixture_results if row["variant"] == "selectable_text"), None)
    scanned = next((row for row in fixture_results if row["variant"] == "image_only_scan"), None)
    result = {
        "schema_version": "drillloop-ocr-evaluation/v2",
        "created_at_utc": datetime.now(UTC).isoformat(),
        "fictional": True,
        "labels": {
            "path": str(label_path.relative_to(ROOT)),
            "sha256": hashlib.sha256(label_path.read_bytes()).hexdigest(),
            "initial_labels_written_before_ocr": labels.get(
                "initial_labels_written_before_ocr", False
            ),
            "label_audit_after_initial_ocr_run": labels.get(
                "label_audit_after_initial_ocr_run", False
            ),
            "labels_authored_from_source_content": labels.get(
                "labels_authored_from_source_content", False
            ),
            "independently_adjudicated": labels.get("independently_adjudicated", False),
        },
        "stack": {
            "tesseract": runtime.engine_version,
            "language": "eng",
            "renderer": f"pypdfium2 {runtime.renderer_version}",
            "native_extractor": "pypdf 6.21.4",
            "resource_limits": {
                "max_ocr_pages": 20,
                "dpi": 200,
                "max_pixels_per_page": 12_000_000,
                "tesseract_timeout_seconds_per_page": 4,
                "max_embedded_image_objects_per_mixed_page": 64,
                "max_embedded_image_regions_per_mixed_page": 8,
                "mixed_page_tesseract_deadline_seconds": 4,
                "parser_timeout_seconds": 15,
                "parser_cpu_seconds": 10,
                "parser_memory_limit_mb": 768,
                "ocr_temporary_files": 0,
            },
        },
        "paired_native_vs_scanned": {
            "native_character_error_rate": native["metrics"]["character_error_rate"]["rate"]
            if native and native["metrics"]["character_error_rate"]
            else None,
            "scanned_character_error_rate": scanned["metrics"]["character_error_rate"]["rate"]
            if scanned and scanned["metrics"]["character_error_rate"]
            else None,
            "native_word_error_rate": native["metrics"]["word_error_rate"]["rate"]
            if native and native["metrics"]["word_error_rate"]
            else None,
            "scanned_word_error_rate": scanned["metrics"]["word_error_rate"]["rate"]
            if scanned and scanned["metrics"]["word_error_rate"]
            else None,
            "native_page_attribution_accuracy": native["metrics"]["page_method_attribution"][
                "accuracy"
            ]
            if native
            else None,
            "scanned_page_attribution_accuracy": scanned["metrics"]["page_method_attribution"][
                "accuracy"
            ]
            if scanned
            else None,
        },
        "resource_usage": {
            "isolated_parser_children_user_cpu_seconds": round(usage.ru_utime, 4),
            "isolated_parser_children_system_cpu_seconds": round(usage.ru_stime, 4),
            "peak_child_rss_bytes": max_rss_bytes,
            "scope": "Child CPU times are aggregated across isolated OCR/parser workers; RSS is the maximum per-child high-water measurement in this run, not a sum or production capacity measure.",
        },
        "fixtures": fixture_results,
        "aggregate_metrics": _aggregate_metrics(fixture_results),
        "application_workflow": workflow,
        "duplicate_upload_behavior": duplicates,
        "metrics_unavailable": labels["measurements_not_available"],
        "limitations": [
            "All evidence is developer-generated fiction; results are fixture measurements, not production accuracy.",
            "OCR word confidence is not available or calibrated.",
            "Per-pixel page navigation or highlighting is not supported by the existing source viewer.",
            "The worker uses the configured upload scanner; this synthetic local run explicitly used scan_status=not_scanned.",
        ],
    }
    if args.compare_phase2_baseline:
        baseline_by_name = {row["filename"]: row for row in phase2_baseline_results}
        current_by_name = {row["filename"]: row for row in fixture_results}
        comparison = {}
        for filename, baseline in baseline_by_name.items():
            current = current_by_name[filename]
            before_metrics = baseline["metrics"]
            after_metrics = current["metrics"]
            comparison[filename] = {
                "before_phase2_policy": {
                    "character_error_rate": before_metrics["character_error_rate"],
                    "word_error_rate": before_metrics["word_error_rate"],
                    "observation_precision": before_metrics["observations"]["precision"],
                    "observation_recall": before_metrics["observations"]["recall"],
                    "timestamp_accuracy": before_metrics["timestamps"]["accuracy"],
                    "page_method_attribution": before_metrics["page_method_attribution"][
                        "accuracy"
                    ],
                    "required_citation_recall": before_metrics["required_citations"]["recall"],
                },
                "after_phase3_policy": {
                    "character_error_rate": after_metrics["character_error_rate"],
                    "word_error_rate": after_metrics["word_error_rate"],
                    "observation_precision": after_metrics["observations"]["precision"],
                    "observation_recall": after_metrics["observations"]["recall"],
                    "timestamp_accuracy": after_metrics["timestamps"]["accuracy"],
                    "page_method_attribution": after_metrics["page_method_attribution"]["accuracy"],
                    "required_citation_recall": after_metrics["required_citations"]["recall"],
                },
                "recognition_policy": "Phase 2 skipped all pages with native selectable text and used Tesseract PSM 6 on image-only pages. Phase 3 adds bounded same-page image-region OCR and a PSM 3 retry only when PSM 6 output puts multiple timestamps on one line.",
            }
        result["phase2_baseline_fixtures"] = phase2_baseline_results
        result["phase2_vs_phase3_comparison"] = {
            "same_fixture_files_and_final_reference_labels": True,
            "baseline_execution": "Phase 2 policy re-run by the evaluator in-process; production Phase 3 parses remain in the isolated worker.",
            "phase2_aggregate_metrics": _aggregate_metrics(phase2_baseline_results),
            "phase3_aggregate_metrics": _aggregate_metrics(fixture_results),
            "per_document": comparison,
        }
    rendered = json.dumps(result, indent=2, sort_keys=True) + "\n"
    if args.output:
        output_path = Path(args.output).expanduser().absolute()
        if output_path.exists() or output_path.is_symlink():
            raise SystemExit("Output exists; refusing to overwrite evaluation results.")
        output_path.parent.mkdir(parents=True, exist_ok=True)
        with output_path.open("x", encoding="utf-8") as output:
            output.write(rendered)
    print(rendered, end="")


if __name__ == "__main__":
    main()
