from datetime import date
from io import BytesIO

import pytest
from app.evidence import EvidenceError, normalize_time, parse_evidence
from reportlab.pdfgen import canvas


def test_csv_keeps_row_provenance_and_normalizes_time():
    parsed = parse_evidence(
        "events.csv",
        "text/csv",
        b"event_id,timestamp,event\nE1,09:02,Power failed\n",
        date(2026, 10, 16),
    )
    assert parsed.kind == "csv"
    assert parsed.observations[0].source_locator == "row 2 \u00b7 E1"
    assert parsed.observations[0].event_time_normalized == "2026-10-16T09:02:00"
    assert parsed.observations[0].time_confidence == "medium"


def test_missing_time_remains_unknown():
    normalized, confidence = normalize_time(None, date(2026, 10, 16))
    assert normalized is None
    assert confidence == "unknown"


def test_transcript_low_confidence_is_uncertain():
    payload = b'{"model":"demo","language":"en","segments":[{"start":2,"end":3,"text":"two minutes","confidence":0.5}]}'
    parsed = parse_evidence("transcript.json", "application/json", payload, date(2026, 10, 16))
    assert parsed.observations[0].time_confidence == "uncertain"
    assert parsed.observations[0].recognition_confidence == 0.5


def test_unsupported_and_malformed_inputs_return_clear_errors():
    with pytest.raises(EvidenceError, match="Supported files"):
        parse_evidence("image.png", "image/png", b"png", date(2026, 10, 16))
    with pytest.raises(EvidenceError, match="header row"):
        parse_evidence("bad.csv", "text/csv", b"\n", date(2026, 10, 16))


def test_selectable_text_pdf_is_extracted_with_page_locator():
    output = BytesIO()
    pdf = canvas.Canvas(output)
    pdf.drawString(72, 720, "[09:14] Generator check complete")
    pdf.save()
    parsed = parse_evidence("notes.pdf", "application/pdf", output.getvalue(), date(2026, 10, 16))
    assert parsed.kind == "pdf"
    assert parsed.observations[0].source_locator == "page 1, line 1"
    assert parsed.observations[0].event_time_normalized == "2026-10-16T09:14:00"
