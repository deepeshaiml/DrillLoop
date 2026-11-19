from __future__ import annotations

import builtins
import hashlib
import subprocess
from datetime import date
from io import BytesIO
from pathlib import Path
from types import SimpleNamespace

import pytest
from app import pdf_ocr
from app.evidence import EvidenceError, parse_evidence
from pypdf import PdfReader, PdfWriter

ROOT = Path(__file__).resolve().parents[2]
FIXTURES = ROOT / "evals" / "phase2" / "sources"
PHASE3_FIXTURES = ROOT / "evals" / "phase3" / "sources"
EXERCISE_DATE = date(2026, 11, 13)


def _fixture(name: str) -> bytes:
    return (FIXTURES / name).read_bytes()


def _phase3_fixture(name: str) -> bytes:
    return (PHASE3_FIXTURES / name).read_bytes()


def test_native_pdf_keeps_existing_page_line_extraction_without_ocr():
    parsed = parse_evidence(
        "utility_emergency_log_native.pdf",
        "application/pdf",
        _fixture("utility_emergency_log_native.pdf"),
        EXERCISE_DATE,
    )

    assert parsed.provenance["ocr_status"] == "not_required"
    assert [page["method"] for page in parsed.provenance["page_extraction"]] == [
        "native_text",
        "native_text",
    ]
    assert parsed.observations[0].source_locator == "page 1, line 1"
    assert parsed.observations[0].extraction_method == "parser"
    assert parsed.observations[2].event_time_raw == "09:00"
    assert parsed.observations[2].event_time_normalized == "2026-11-13T09:00:00"
    assert parsed.observations[2].time_confidence == "medium"


def test_scanned_pdf_ocr_retains_page_provenance_and_uncertain_timestamps():
    filename = "utility_emergency_log_scanned.pdf"
    parsed = parse_evidence(filename, "application/pdf", _fixture(filename), EXERCISE_DATE)

    assert parsed.kind == "pdf"
    assert parsed.provenance["ocr_status"] == "completed"
    assert parsed.provenance["ocr_pages"] == [1, 2]
    assert parsed.provenance["ocr_engine"] == "Tesseract"
    assert parsed.provenance["ocr_word_confidence_available"] is False
    assert parsed.provenance["ocr_line_positions_available"] is False
    assert len(parsed.observations) == 10
    assert {row.extraction_method for row in parsed.observations} == {"ocr"}
    assert {row.source_locator for row in parsed.observations} == {"page 1", "page 2"}
    timed = [row for row in parsed.observations if row.event_time_raw]
    assert [row.event_time_raw for row in timed] == ["09:00", "09:03", "09:12", "09:14"]
    assert all(row.time_confidence == "uncertain" for row in timed)
    assert all(row.event_time_normalized is not None for row in timed)
    assert "[page 2]" in parsed.content_text
    assert hashlib.sha256(_fixture(filename)).hexdigest() == parsed.provenance["sha256"]


def test_mixed_pdf_skips_native_page_and_ocr_processes_only_scanned_page():
    filename = "utility_emergency_log_mixed.pdf"
    parsed = parse_evidence(filename, "application/pdf", _fixture(filename), EXERCISE_DATE)

    assert parsed.provenance["page_extraction"] == [
        {"page": 1, "method": "native_text", "status": "skipped"},
        {"page": 2, "method": "ocr", "status": "completed"},
    ]
    assert parsed.provenance["ocr_pages"] == [2]
    page_one = [row for row in parsed.observations if row.source_locator.startswith("page 1")]
    page_two = [row for row in parsed.observations if row.source_locator == "page 2"]
    assert len(page_one) == 5
    assert len(page_two) == 5
    assert {row.extraction_method for row in page_one} == {"parser"}
    assert {row.extraction_method for row in page_two} == {"ocr"}
    assert [row.event_time_raw for row in page_one if row.event_time_raw] == [
        "09:00",
        "09:03",
        "09:12",
    ]
    assert [row.event_time_raw for row in page_two if row.event_time_raw] == ["09:14"]


def test_same_page_native_and_image_text_are_combined_without_duplicate_observations():
    filename = "phase3_same_page_mixed_water_log.pdf"
    raw = _phase3_fixture(filename)
    parsed = parse_evidence(filename, "application/pdf", raw, EXERCISE_DATE)

    assert parsed.provenance["sha256"] == hashlib.sha256(raw).hexdigest()
    assert parsed.provenance["ocr_status"] == "completed"
    assert parsed.provenance["ocr_pages"] == [1]
    assert parsed.provenance["ocr_image_regions"] == {1: 1}
    assert parsed.provenance["ocr_duplicate_lines_suppressed"] == 1
    assert parsed.provenance["page_extraction"] == [
        {"page": 1, "method": "native_text_plus_ocr", "status": "completed"},
        {"page": 2, "method": "native_text", "status": "skipped"},
    ]

    native_ack = [row for row in parsed.observations if "Dispatcher acknowledged" in row.text]
    scanned_restoration = [
        row
        for row in parsed.observations
        if row.source_locator == "page 1" and "Station B pump restored" in row.text
    ]
    repeated_native_restoration = [
        row
        for row in parsed.observations
        if row.source_locator.startswith("page 2") and "Station B pump restored" in row.text
    ]
    assert len(native_ack) == 1
    assert native_ack[0].source_locator == "page 1, line 4"
    assert native_ack[0].extraction_method == "parser"
    assert len(scanned_restoration) == 1
    assert scanned_restoration[0].event_time_raw == "14:11"
    assert scanned_restoration[0].time_confidence == "uncertain"
    assert scanned_restoration[0].extraction_method == "ocr"
    assert len(repeated_native_restoration) == 1
    assert "14:11 Station B pump restored; pressure stable." in parsed.content_text


def test_same_page_image_ocr_timeout_keeps_native_text_and_marks_partial(monkeypatch):
    from app import pdf_ocr

    def timeout_image_ocr(*_args, **_kwargs):
        return pdf_ocr.PdfOcrRegionsResult(
            text="",
            duration_seconds=pdf_ocr.OCR_PAGE_TIMEOUT_SECONDS,
            attempted_regions=0,
            omitted_regions=0,
            issues=(("OCR_TIMEOUT", "Image OCR exceeded the page limit."),),
        )

    monkeypatch.setattr(pdf_ocr, "ocr_pdf_image_regions", timeout_image_ocr)
    parsed = parse_evidence(
        "phase3_same_page_mixed_water_log.pdf",
        "application/pdf",
        _phase3_fixture("phase3_same_page_mixed_water_log.pdf"),
        EXERCISE_DATE,
    )

    assert parsed.provenance["ocr_status"] == "partial"
    assert parsed.provenance["ocr_partial_pages"] == [1]
    assert parsed.provenance["page_extraction"][0]["status"] == "partial"
    assert parsed.provenance["ocr_issues"][0]["code"] == "OCR_TIMEOUT"
    assert any("Dispatcher acknowledged" in row.text for row in parsed.observations)
    assert not any(
        row.source_locator == "page 1" and "Station B pump restored" in row.text
        for row in parsed.observations
    )


def test_two_column_scan_retries_with_auto_segmentation_when_rows_mix_timestamps():
    parsed = parse_evidence(
        "phase3_two_column_low_resolution_scan.pdf",
        "application/pdf",
        _phase3_fixture("phase3_two_column_low_resolution_scan.pdf"),
        EXERCISE_DATE,
    )

    assert parsed.provenance["ocr_page_segmentation_modes"] == {1: [6, 3]}
    assert [row.event_time_raw for row in parsed.observations if row.event_time_raw] == [
        "13:52",
        "13:54",
        "14:03",
        "14:07",
        "14:13",
        "14:18",
    ]
    assert all(
        row.time_confidence == "uncertain" for row in parsed.observations if row.event_time_raw
    )


def test_unreadable_scan_does_not_create_observations_or_a_false_success():
    with pytest.raises(EvidenceError) as error:
        parse_evidence(
            "phase3_unreadable_damaged_field_note.pdf",
            "application/pdf",
            _phase3_fixture("phase3_unreadable_damaged_field_note.pdf"),
            EXERCISE_DATE,
        )

    assert error.value.code == "EMPTY_PDF"
    assert "No selectable or OCR-readable text" in error.value.message


def test_mixed_page_ocr_limit_keeps_native_text_and_marks_remaining_pages_partial(monkeypatch):
    from app import pdf_ocr
    from app.evidence import MAX_OCR_PAGES

    reader = PdfReader(BytesIO(_phase3_fixture("phase3_same_page_mixed_water_log.pdf")))
    writer = PdfWriter()
    for _ in range(MAX_OCR_PAGES + 1):
        writer.add_page(reader.pages[0])
    source = BytesIO()
    writer.write(source)

    monkeypatch.setattr(
        pdf_ocr,
        "ocr_pdf_image_regions",
        lambda *_args, **_kwargs: pdf_ocr.PdfOcrRegionsResult(
            text="", duration_seconds=0.001, attempted_regions=1, omitted_regions=0
        ),
    )
    parsed = parse_evidence(
        "many-mixed-pages.pdf", "application/pdf", source.getvalue(), EXERCISE_DATE
    )

    assert parsed.provenance["ocr_status"] == "partial"
    assert parsed.provenance["ocr_pages"] == list(range(1, MAX_OCR_PAGES + 1))
    assert parsed.provenance["ocr_partial_pages"] == [MAX_OCR_PAGES + 1]
    assert parsed.provenance["page_extraction"][-1] == {
        "page": MAX_OCR_PAGES + 1,
        "method": "native_text_plus_ocr",
        "status": "partial",
    }
    assert parsed.provenance["ocr_issues"][0]["code"] == "OCR_PAGE_LIMIT"
    assert any(
        row.source_locator == f"page {MAX_OCR_PAGES + 1}, line 4" for row in parsed.observations
    )


def test_moderately_rotated_degraded_scan_is_read_without_claiming_positions():
    filename = "utility_emergency_log_rotated_degraded.pdf"
    parsed = parse_evidence(filename, "application/pdf", _fixture(filename), EXERCISE_DATE)

    assert parsed.provenance["ocr_pages"] == [1, 2]
    assert len(parsed.observations) == 10
    assert any("low-pressure alarm activated" in row.text for row in parsed.observations)
    assert any("Station B confirmed service restored" in row.text for row in parsed.observations)
    assert all(row.source_locator in {"page 1", "page 2"} for row in parsed.observations)


def test_ambiguous_and_missing_information_does_not_gain_an_event_time():
    filename = "utility_ambiguous_missing_scanned.pdf"
    parsed = parse_evidence(filename, "application/pdf", _fixture(filename), EXERCISE_DATE)
    ambiguous = next(row for row in parsed.observations if "09:12 or 09:17" in row.text)
    missing_time = next(row for row in parsed.observations if "acknowledgement time" in row.text)
    unknown_cause = next(row for row in parsed.observations if "Cause of the pump trip" in row.text)

    assert ambiguous.event_time_raw is None
    assert ambiguous.event_time_normalized is None
    assert ambiguous.time_confidence == "unknown"
    assert missing_time.event_time_raw is None
    assert unknown_cause.event_time_raw is None
    assert all(row.source_locator == "page 1" for row in parsed.observations)


def test_missing_tesseract_returns_controlled_unavailable_error(monkeypatch):
    monkeypatch.setattr(pdf_ocr.shutil, "which", lambda _command: None)

    with pytest.raises(EvidenceError) as error:
        parse_evidence(
            "scan.pdf",
            "application/pdf",
            _fixture("utility_emergency_log_scanned.pdf"),
            EXERCISE_DATE,
        )

    assert error.value.code == "OCR_UNAVAILABLE"
    assert error.value.status_code == 503


def test_missing_pdf_renderer_returns_controlled_unavailable_error(monkeypatch):
    real_import = builtins.__import__

    def missing_renderer(name, *args, **kwargs):
        if name == "pypdfium2":
            raise ImportError("simulated missing pypdfium2")
        return real_import(name, *args, **kwargs)

    monkeypatch.setattr(builtins, "__import__", missing_renderer)
    with pytest.raises(EvidenceError) as error:
        parse_evidence(
            "scan.pdf",
            "application/pdf",
            _fixture("utility_emergency_log_scanned.pdf"),
            EXERCISE_DATE,
        )

    assert error.value.code == "OCR_UNAVAILABLE"
    assert error.value.status_code == 503


def test_missing_english_data_returns_controlled_error(monkeypatch):
    real_run = subprocess.run

    def unavailable_language(command, *args, **kwargs):
        if command[-1] == "--list-langs":
            return SimpleNamespace(
                returncode=0, stdout=b"List of available languages:\nfra\n", stderr=b""
            )
        return real_run(command, *args, **kwargs)

    monkeypatch.setattr(pdf_ocr.subprocess, "run", unavailable_language)
    with pytest.raises(EvidenceError) as error:
        parse_evidence(
            "scan.pdf",
            "application/pdf",
            _fixture("utility_emergency_log_scanned.pdf"),
            EXERCISE_DATE,
        )
    assert error.value.code == "OCR_LANGUAGE_UNAVAILABLE"
    assert error.value.status_code == 503


def test_tesseract_page_timeout_returns_controlled_error(monkeypatch):
    real_run = subprocess.run

    def timeout_ocr(command, *args, **kwargs):
        if len(command) > 2 and command[1:3] == ["stdin", "stdout"]:
            raise subprocess.TimeoutExpired(command, timeout=pdf_ocr.OCR_PAGE_TIMEOUT_SECONDS)
        return real_run(command, *args, **kwargs)

    monkeypatch.setattr(pdf_ocr.subprocess, "run", timeout_ocr)
    with pytest.raises(EvidenceError) as error:
        parse_evidence(
            "scan.pdf",
            "application/pdf",
            _fixture("utility_emergency_log_scanned.pdf"),
            EXERCISE_DATE,
        )
    assert error.value.code == "OCR_TIMEOUT"
    assert error.value.status_code == 422


def test_ocr_page_count_is_bounded_before_rendering():
    writer = PdfWriter()
    for _ in range(21):
        writer.add_blank_page(width=612, height=792)
    source = BytesIO()
    writer.write(source)

    with pytest.raises(EvidenceError) as error:
        parse_evidence("many-pages.pdf", "application/pdf", source.getvalue(), EXERCISE_DATE)
    assert error.value.code == "TOO_MANY_OCR_PAGES"
    assert error.value.status_code == 413


def test_oversized_render_page_is_rejected_before_rasterizing():
    writer = PdfWriter()
    writer.add_blank_page(width=20_000, height=20_000)
    source = BytesIO()
    writer.write(source)

    with pytest.raises(EvidenceError) as error:
        parse_evidence("oversized-page.pdf", "application/pdf", source.getvalue(), EXERCISE_DATE)
    assert error.value.code == "OCR_PAGE_TOO_LARGE"
    assert error.value.status_code == 413


def test_ocr_writes_no_temporary_page_files(monkeypatch, tmp_path):
    temporary_root = tmp_path / "tmp"
    temporary_root.mkdir()
    monkeypatch.setenv("TMPDIR", str(temporary_root))

    parsed = parse_evidence(
        "scan.pdf",
        "application/pdf",
        _fixture("utility_emergency_log_scanned.pdf"),
        EXERCISE_DATE,
    )

    assert parsed.provenance["ocr_status"] == "completed"
    assert list(temporary_root.iterdir()) == []


def test_same_page_mixed_region_ocr_writes_no_temporary_page_files(monkeypatch, tmp_path):
    temporary_root = tmp_path / "tmp"
    temporary_root.mkdir()
    monkeypatch.setenv("TMPDIR", str(temporary_root))

    parsed = parse_evidence(
        "phase3_same_page_mixed_water_log.pdf",
        "application/pdf",
        _phase3_fixture("phase3_same_page_mixed_water_log.pdf"),
        EXERCISE_DATE,
    )

    assert parsed.provenance["ocr_status"] == "completed"
    assert parsed.provenance["ocr_image_regions"] == {1: 1}
    assert list(temporary_root.iterdir()) == []
