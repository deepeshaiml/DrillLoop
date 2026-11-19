#!/usr/bin/env python3
"""Generate a small paired set of entirely fictional PDF OCR fixtures."""

from __future__ import annotations

import hashlib
import json
from io import BytesIO
from pathlib import Path

import pypdfium2 as pdfium
from PIL import Image, ImageEnhance, ImageFilter, ImageOps
from pypdf import PdfReader, PdfWriter
from reportlab.lib.pagesizes import letter
from reportlab.lib.utils import ImageReader
from reportlab.pdfgen import canvas

ROOT = Path(__file__).resolve().parents[1]
OUTPUT = ROOT / "evals" / "phase2" / "sources"
PAGE_SIZE = letter

LOG_PAGES = [
    [
        "FICTIONAL EXERCISE RECORD - SYNTHETIC ONLY",
        "Water utility emergency exercise log",
        "[09:00] Primary pump P-4 tripped; low-pressure alarm activated.",
        "[09:03] Control room operator acknowledged the alarm.",
        "[09:12] Backup pump P-7 reached stable pressure at 42 psi.",
    ],
    [
        "FICTIONAL EXERCISE RECORD - SYNTHETIC ONLY",
        "[09:14] Station B confirmed service restored.",
        "The field crew acknowledgement time was not recorded.",
        "The cause of the P-4 trip is unknown.",
        "Objective: restore stable pressure within 15 minutes.",
    ],
]

AMBIGUOUS_PAGE = [
    "FICTIONAL EXERCISE RECORD - SYNTHETIC ONLY",
    "Water utility response note",
    "Pressure may have stabilized near 09:12 or 09:17; verify against the control record.",
    "The field crew acknowledgement time was not recorded.",
    "Cause of the pump trip: unknown.",
]


def _native_pdf(pages: list[list[str]]) -> bytes:
    output = BytesIO()
    page = canvas.Canvas(output, pagesize=PAGE_SIZE, invariant=1)
    page.setTitle("Fictional Water Utility Exercise Evidence")
    page.setAuthor("DrillLoop fictional fixture generator")
    for lines in pages:
        y = PAGE_SIZE[1] - 64
        for index, line in enumerate(lines):
            page.setFont("Helvetica-Bold" if index == 0 else "Helvetica", 13 if index == 0 else 12)
            page.drawString(54, y, line)
            y -= 28
        page.showPage()
    page.save()
    return output.getvalue()


def _render_pages(pdf_bytes: bytes, *, degraded: bool = False) -> list:
    document = pdfium.PdfDocument(pdf_bytes)
    images = []
    for page_number in range(len(document)):
        page = document[page_number]
        bitmap = page.render(scale=300 / 72)
        image = bitmap.to_pil().convert("RGB")
        if degraded and page_number == 0:
            image = ImageOps.grayscale(image).convert("RGB")
            image = image.rotate(0.6, resample=Image.Resampling.BICUBIC, fillcolor="white")
            image = ImageEnhance.Contrast(image).enhance(1.2).filter(ImageFilter.GaussianBlur(0.18))
        images.append(image)
        bitmap.close()
        page.close()
    document.close()
    return images


def _scan_pdf(images: list) -> bytes:
    output = BytesIO()
    page = canvas.Canvas(output, pagesize=PAGE_SIZE, invariant=1)
    page.setTitle("Fictional scanned Water Utility Exercise Evidence")
    page.setAuthor("DrillLoop fictional fixture generator")
    for image in images:
        page.drawImage(ImageReader(image), 0, 0, width=PAGE_SIZE[0], height=PAGE_SIZE[1])
        page.showPage()
    page.save()
    return output.getvalue()


def _mixed_pdf(native_pdf: bytes, scanned_pdf: bytes) -> bytes:
    native = PdfReader(BytesIO(native_pdf), strict=True)
    scanned = PdfReader(BytesIO(scanned_pdf), strict=True)
    writer = PdfWriter()
    writer.add_page(native.pages[0])
    writer.add_page(scanned.pages[1])
    output = BytesIO()
    writer.write(output)
    return output.getvalue()


def _labels() -> dict:
    return {
        "fictional": True,
        "labeling_note": "Developer-authored expected wording, times, page numbers, and objective labels were recorded before running OCR. They are not inferred from application predictions and are not independently adjudicated.",
        "documents": [
            {
                "filename": "utility_emergency_log_native.pdf",
                "variant": "selectable_text",
                "pages": [
                    {"page": 1, "method": "native_text", "source_lines": LOG_PAGES[0]},
                    {"page": 2, "method": "native_text", "source_lines": LOG_PAGES[1]},
                ],
            },
            {
                "filename": "utility_emergency_log_scanned.pdf",
                "variant": "image_only_scan",
                "pages": [
                    {"page": 1, "method": "ocr", "source_lines": LOG_PAGES[0]},
                    {"page": 2, "method": "ocr", "source_lines": LOG_PAGES[1]},
                ],
            },
            {
                "filename": "utility_emergency_log_mixed.pdf",
                "variant": "native_page_plus_scanned_page",
                "pages": [
                    {"page": 1, "method": "native_text", "source_lines": LOG_PAGES[0]},
                    {"page": 2, "method": "ocr", "source_lines": LOG_PAGES[1]},
                ],
            },
            {
                "filename": "utility_emergency_log_rotated_degraded.pdf",
                "variant": "moderately_rotated_and_degraded_scan",
                "pages": [
                    {"page": 1, "method": "ocr", "source_lines": LOG_PAGES[0]},
                    {"page": 2, "method": "ocr", "source_lines": LOG_PAGES[1]},
                ],
            },
            {
                "filename": "utility_ambiguous_missing_scanned.pdf",
                "variant": "ambiguous_and_missing_information_scan",
                "pages": [{"page": 1, "method": "ocr", "source_lines": AMBIGUOUS_PAGE}],
                "expected_unknowns": [
                    "Two alternative pressure stabilization times are reported in the wording.",
                    "The field crew acknowledgement time is explicitly not recorded.",
                    "The pump-trip cause is unknown.",
                ],
                "expected_unknown_source_lines": [
                    "Pressure may have stabilized near 09:12 or 09:17; verify against the control record.",
                    "The field crew acknowledgement time was not recorded.",
                    "Cause of the pump trip: unknown.",
                ],
            },
        ],
        "objective_labels": [
            {
                "objective_id": "OBJ-PRESSURE-15",
                "expected_source_claim": "Stable pressure was reported at 09:12 after the low-pressure alarm at 09:00.",
                "expected_elapsed_seconds": 720,
                "threshold_seconds": 900,
                "ocr_time_confidence": "uncertain",
                "expected_scanned_assessment": "insufficient_information",
            },
            {
                "objective_id": "OBJ-STATION-B",
                "expected_source_claim": "Station B confirmed service restored.",
                "expected_scanned_assessment": "confirmed_success",
                "expected_finding_code": "STATION_B_RESTORED",
                "expected_finding_decision": "proposed",
                "expected_review_decision": None,
                "expected_citation": {
                    "source": "utility_emergency_log_scanned.pdf",
                    "locator": "page 2",
                },
            },
        ],
        "measurements_not_available": [
            "OCR confidence calibration and word-level confidence, because the OCR path intentionally stores no confidence values.",
            "Pixel-level citation or PDF highlight accuracy, because the source viewer supports page locators and original-file download only.",
            "Production OCR accuracy, because all files and labels are fictional and developer-authored.",
        ],
    }


def main() -> None:
    if OUTPUT.exists() and any(OUTPUT.iterdir()):
        raise SystemExit(f"Refusing to overwrite existing Phase 2 fixtures: {OUTPUT}")
    label_path = ROOT / "evals" / "phase2" / "ground_truth.json"
    if label_path.exists():
        raise SystemExit(f"Refusing to overwrite existing labels: {label_path}")
    OUTPUT.mkdir(parents=True, exist_ok=True)
    native_pdf = _native_pdf(LOG_PAGES)
    native_document = PdfReader(BytesIO(native_pdf), strict=True)
    scanned_images = _render_pages(native_pdf)
    degraded_images = _render_pages(native_pdf, degraded=True)
    ambiguous_pdf = _native_pdf([AMBIGUOUS_PAGE])
    ambiguous_images = _render_pages(ambiguous_pdf)

    files = {
        "utility_emergency_log_native.pdf": native_pdf,
        "utility_emergency_log_scanned.pdf": _scan_pdf(scanned_images),
        "utility_emergency_log_mixed.pdf": _mixed_pdf(native_pdf, _scan_pdf(scanned_images)),
        "utility_emergency_log_rotated_degraded.pdf": _scan_pdf(degraded_images),
        "utility_ambiguous_missing_scanned.pdf": _scan_pdf(ambiguous_images),
    }
    for filename, content in files.items():
        (OUTPUT / filename).write_bytes(content)

    labels = _labels()
    for document in labels["documents"]:
        source = OUTPUT / document["filename"]
        document["path"] = f"evals/phase2/sources/{source.name}"
        document["sha256"] = hashlib.sha256(source.read_bytes()).hexdigest()
        document["bytes"] = source.stat().st_size
    labels["native_pdf_page_count"] = len(native_document.pages)
    label_path.write_text(json.dumps(labels, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(
        json.dumps(
            {
                "result": "generated fictional fixtures",
                "files": sorted(files),
                "ground_truth": str(label_path.relative_to(ROOT)),
                "ocr_was_not_run": True,
            },
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
