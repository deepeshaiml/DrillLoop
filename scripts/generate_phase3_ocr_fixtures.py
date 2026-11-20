#!/usr/bin/env python3
"""Generate varied, fictional PDFs for Phase 3 OCR robustness evaluation."""

from __future__ import annotations

import hashlib
import json
from io import BytesIO
from pathlib import Path

import pypdfium2 as pdfium
from PIL import Image, ImageEnhance, ImageFilter, ImageOps
from reportlab.lib.pagesizes import landscape, letter
from reportlab.lib.utils import ImageReader
from reportlab.pdfgen import canvas

ROOT = Path(__file__).resolve().parents[1]
OUTPUT = ROOT / "evals" / "phase3" / "sources"

MIXED_NATIVE = [
    "FICTIONAL UTILITY EXERCISE - SYNTHETIC ONLY",
    "Water utility control room shift log",
    "14:00 Low-pressure alarm activated at Station B.",
    "14:04 Dispatcher acknowledged the alarm.",
]
MIXED_IMAGE = [
    "14:04 Dispatcher acknowledged the alarm.",
    "14:11 Station B pump restored; pressure stable.",
]
MIXED_HANDOVER = [
    "FICTIONAL EXERCISE HANDOVER SUMMARY",
    "14:11 Station B pump restored; pressure stable.",
    "14:16 Field supervisor reported service stable.",
]

TWO_COLUMN_LEFT = [
    "13:52 Alarm logged at Booster 4.",
    "13:54 Call-out issued to crew 0-1.",
    "14:03 Crew 0-1 arrived at Booster 4.",
]
TWO_COLUMN_RIGHT = [
    "14:07 Isolation switch I-01 verified open.",
    "14:13 Flow measured at 42 L/s.",
    "14:18 Shift lead declared the exercise complete.",
]
TWO_COLUMN = [
    "FICTIONAL EXERCISE FIELD SHEET - COPY",
    "Column A: Control room",
    *TWO_COLUMN_LEFT,
    # The source-code note appears directly under column A in the fictional page.
    "The source code O1 is visually similar to 01; verify against the original.",
    "Column B: Field team",
    *TWO_COLUMN_RIGHT,
]

TABLE_PAGES = [
    [
        "FICTIONAL WATER EXERCISE - EVENT REGISTER",
        "Record 1 of 2 · synthetic evaluation copy",
        "TIME LOCATION SOURCE WORDING",
        "15:02 Gate 0 Isolation test initiated.",
        "15:17 Valve V-10 Closed; pressure held.",
        "15:20 Gate 1 Controller announced the stop.",
    ],
    [
        "FICTIONAL WATER EXERCISE - EVENT REGISTER",
        "Record 2 of 2 · synthetic evaluation copy",
        "TIME LOCATION SOURCE WORDING",
        "15:17 Valve V-10 Closed; pressure held.",
        "No time Compressor C-1 Noise was reported; time not recorded.",
        "15:2? Pump P-10 The handwritten minute digit is unreadable.",
    ],
]

TABLE_ROWS = [
    [
        ("15:02", "Gate 0", "Isolation test initiated."),
        ("15:17", "Valve V-10", "Closed; pressure held."),
        ("15:20", "Gate 1", "Controller announced the stop."),
    ],
    [
        ("15:17", "Valve V-10", "Closed; pressure held."),
        ("No time", "Compressor C-1", "Noise was reported; time not recorded."),
        ("15:2?", "Pump P-10", "The handwritten minute digit is unreadable."),
    ],
]

CONFLICT_MEMO = [
    "FICTIONAL RADIO CLARIFICATION - SYNTHETIC ONLY",
    "Typed dispatch memorandum",
    "14:12 Station B pump restored; pressure stable.",
    "15:19 Valve V-10 closed; pressure held.",
    "The controller did not resolve the different reported times.",
]

UNREADABLE_INTENDED = [
    "FICTIONAL EXERCISE FIELD NOTE - SYNTHETIC ONLY",
    "15:36 Crew 0-1 reported the north valve condition.",
    "No second time or action is recoverable from this damaged copy.",
]


def _new_pdf(size=letter, *, title: str) -> tuple[BytesIO, canvas.Canvas]:
    output = BytesIO()
    page = canvas.Canvas(output, pagesize=size, invariant=1)
    page.setTitle(title)
    page.setAuthor("DrillLoop fictional Phase 3 fixture generator")
    return output, page


def _text_page(lines: list[str], *, size=letter, font_size=11.5) -> bytes:
    output, page = _new_pdf(size, title="Fictional exercise evidence")
    width, height = size
    y = height - 54
    for index, line in enumerate(lines):
        page.setFont(
            "Helvetica-Bold" if index == 0 else "Helvetica", font_size + (0.5 if index == 0 else 0)
        )
        page.drawString(46, y, line)
        y -= font_size * 2.2
    page.showPage()
    page.save()
    return output.getvalue()


def _text_image(lines: list[str], *, width=330, height=80) -> Image.Image:
    output, page = _new_pdf((width, height), title="Fictional embedded field slip")
    page.setFillColorRGB(0.97, 0.97, 0.94)
    page.rect(0, 0, width, height, stroke=0, fill=1)
    page.setStrokeColorRGB(0.5, 0.5, 0.5)
    page.rect(2, 2, width - 4, height - 4, stroke=1, fill=0)
    y = height - 22
    for line in lines:
        page.setFont("Helvetica", 12)
        page.setFillColorRGB(0.08, 0.08, 0.08)
        page.drawString(12, y, line)
        y -= 28
    page.showPage()
    page.save()
    data = output.getvalue()
    output.close()
    document = pdfium.PdfDocument(data)
    rendered_page = document[0]
    bitmap = rendered_page.render(scale=300 / 72, grayscale=False)
    image = bitmap.to_pil().convert("RGB")
    bitmap.close()
    rendered_page.close()
    document.close()
    return image


def _render_pdf_pages(data: bytes, *, dpi=300) -> list[Image.Image]:
    document = pdfium.PdfDocument(data)
    images = []
    for index in range(len(document)):
        page = document[index]
        bitmap = page.render(scale=dpi / 72, grayscale=True)
        images.append(bitmap.to_pil().convert("RGB"))
        bitmap.close()
        page.close()
    document.close()
    return images


def _degrade(
    image: Image.Image,
    *,
    page_size=letter,
    low_dpi: int | None = None,
    blur: float = 0,
    skew_degrees: float = 0,
    noise: float = 0,
) -> Image.Image:
    result = ImageOps.grayscale(image).convert("RGB")
    if low_dpi is not None:
        page_width, page_height = page_size
        width = max(1, round(page_width * low_dpi / 72))
        height = max(1, round(page_height * low_dpi / 72))
        result = result.resize((width, height), Image.Resampling.LANCZOS).resize(
            image.size, Image.Resampling.BICUBIC
        )
    if blur:
        result = result.filter(ImageFilter.GaussianBlur(blur))
    if noise:
        noise_image = Image.effect_noise(result.size, 18).convert("RGB")
        result = Image.blend(result, noise_image, noise)
        noise_image.close()
    if skew_degrees:
        result = result.rotate(
            skew_degrees,
            resample=Image.Resampling.BICUBIC,
            expand=False,
            fillcolor="white",
        )
    return result


def _image_pdf(images: list[Image.Image], *, title: str, size=letter) -> bytes:
    output, page = _new_pdf(size, title=title)
    width, height = size
    for image in images:
        page.drawImage(ImageReader(image), 0, 0, width=width, height=height)
        page.showPage()
    page.save()
    data = output.getvalue()
    output.close()
    return data


def _same_page_mixed_pdf() -> bytes:
    output, page = _new_pdf(title="Fictional same-page mixed evidence")
    page.setFont("Helvetica-Bold", 12)
    page.drawString(46, 746, MIXED_NATIVE[0])
    page.setFont("Helvetica", 11)
    page.drawString(46, 720, MIXED_NATIVE[1])
    page.drawString(46, 684, MIXED_NATIVE[2])
    page.drawString(46, 660, MIXED_NATIVE[3])
    slip = _text_image(MIXED_IMAGE)
    page.drawImage(ImageReader(slip), 46, 535, width=330, height=80)
    slip.close()
    page.showPage()
    page.setFont("Helvetica-Bold", 12)
    page.drawString(46, 746, MIXED_HANDOVER[0])
    page.setFont("Helvetica", 11)
    page.drawString(46, 710, MIXED_HANDOVER[1])
    page.drawString(46, 684, MIXED_HANDOVER[2])
    page.showPage()
    page.save()
    data = output.getvalue()
    output.close()
    return data


def _two_column_native_pdf() -> bytes:
    output, page = _new_pdf(title="Fictional two-column exercise field sheet")
    page.setFont("Helvetica-Bold", 10)
    page.drawString(42, 748, TWO_COLUMN[0])
    page.setFont("Helvetica", 8)
    page.drawString(42, 722, "Column A: Control room")
    page.drawString(330, 722, "Column B: Field team")
    page.setStrokeColorRGB(0.55, 0.60, 0.60)
    page.line(306, 706, 306, 640)
    rows = list(zip(TWO_COLUMN_LEFT, TWO_COLUMN_RIGHT, strict=True))
    y = 695
    for left, right in rows:
        page.setFont("Helvetica", 8)
        page.drawString(42, y, left)
        page.drawString(330, y, right)
        y -= 22
    page.setFont("Helvetica", 7)
    page.drawString(42, 620, "The source code O1 is visually similar to 01; verify the original.")
    page.showPage()
    page.save()
    data = output.getvalue()
    output.close()
    return data


def _table_native_pdf() -> bytes:
    output, page = _new_pdf(landscape(letter), title="Fictional two-page valve event table")
    width, height = landscape(letter)
    column_x = (52, 142, 285, 520)
    for page_index, rows in enumerate(TABLE_PAGES):
        page.setFont("Helvetica-Bold", 12)
        page.drawString(52, height - 48, rows[0])
        page.setFont("Helvetica", 9)
        page.drawString(52, height - 67, rows[1])
        top = height - 110
        row_height = 46
        page.setFillColorRGB(0.90, 0.94, 0.94)
        page.rect(46, top, width - 92, 28, stroke=0, fill=1)
        page.setFillColorRGB(0.05, 0.12, 0.15)
        page.setFont("Helvetica-Bold", 9)
        page.drawString(column_x[0], top + 9, "TIME")
        page.drawString(column_x[1], top + 9, "LOCATION")
        page.drawString(column_x[2], top + 9, "SOURCE WORDING")
        for row_index, (time_value, location, wording) in enumerate(TABLE_ROWS[page_index]):
            y = top - (row_index + 1) * row_height
            page.setStrokeColorRGB(0.70, 0.73, 0.73)
            page.line(46, y, width - 46, y)
            page.setFont("Helvetica", 8)
            page.drawString(column_x[0], y + 17, time_value)
            page.drawString(column_x[1], y + 17, location)
            page.drawString(column_x[2], y + 17, wording)
        page.setStrokeColorRGB(0.70, 0.73, 0.73)
        for x in column_x:
            page.line(x - 8, top + 28, x - 8, top - (len(rows) - 1) * row_height)
        page.showPage()
    page.save()
    data = output.getvalue()
    output.close()
    return data


def _unreadable_scan_pdf() -> bytes:
    source = _text_page(UNREADABLE_INTENDED, font_size=14)
    images = _render_pdf_pages(source, dpi=240)
    damaged = []
    for image in images:
        tiny = ImageOps.grayscale(image).resize((28, 36), Image.Resampling.BILINEAR)
        blurred = tiny.resize(image.size, Image.Resampling.BICUBIC).filter(
            ImageFilter.GaussianBlur(5.5)
        )
        damaged.append(ImageEnhance.Contrast(blurred).enhance(0.4).convert("RGB"))
        tiny.close()
        blurred.close()
        image.close()
    return _image_pdf(damaged, title="Fictional damaged field note")


def _document(filename: str, variant: str, pages: list[dict], **extra) -> dict:
    return {"filename": filename, "variant": variant, "pages": pages, **extra}


def _labels(files: dict[str, bytes]) -> dict:
    mixed_lines_page_1 = MIXED_NATIVE + [MIXED_IMAGE[1]]
    docs = [
        _document(
            "phase3_same_page_mixed_water_log.pdf",
            "same_page_native_plus_scanned_image",
            [
                {
                    "page": 1,
                    "method": "native_text_plus_ocr",
                    "source_lines": mixed_lines_page_1,
                    "native_source_lines": MIXED_NATIVE,
                    "image_source_lines": MIXED_IMAGE,
                    "overlap_source_lines": [MIXED_IMAGE[0]],
                },
                {
                    "page": 2,
                    "method": "native_text",
                    "source_lines": MIXED_HANDOVER,
                    "native_source_lines": MIXED_HANDOVER,
                    "image_source_lines": [],
                    "overlap_source_lines": [],
                },
            ],
            repeated_event_groups=[
                {
                    "event_key": "station_b_pump_restored",
                    "source_lines": [
                        {"page": 1, "text": MIXED_IMAGE[1]},
                        {"page": 2, "text": MIXED_HANDOVER[1]},
                    ],
                    "should_remain_separate_by_page": True,
                }
            ],
            required_citations=[{"page": 1, "source_line": MIXED_IMAGE[1], "required": True}],
        ),
        _document(
            "phase3_two_column_low_resolution_scan.pdf",
            "two_column_low_resolution_blurred_skewed_scan",
            [
                {
                    "page": 1,
                    "method": "ocr",
                    "source_lines": TWO_COLUMN,
                    "native_source_lines": [],
                    "image_source_lines": TWO_COLUMN,
                    "overlap_source_lines": [],
                }
            ],
            challenge_factors=[
                "two columns",
                "small font",
                "low resolution",
                "blur",
                "1.15 degree skew",
                "0/O and 1/I glyphs",
            ],
        ),
        _document(
            "phase3_two_page_valve_event_table_scan.pdf",
            "two_page_scanned_table_with_repeated_and_ambiguous_events",
            [
                {
                    "page": page_number,
                    "method": "ocr",
                    "source_lines": rows,
                    "native_source_lines": [],
                    "image_source_lines": rows,
                    "overlap_source_lines": [],
                }
                for page_number, rows in enumerate(TABLE_PAGES, 1)
            ],
            challenge_factors=[
                "table",
                "two pages",
                "repeated event",
                "small font",
                "ambiguous minute digit",
                "missing time",
            ],
            expected_unknown_source_lines=[
                {"page": 2, "text": TABLE_PAGES[1][4]},
                {"page": 2, "text": TABLE_PAGES[1][5]},
            ],
        ),
        _document(
            "phase3_conflicting_dispatch_memo.pdf",
            "native_dispatch_memo_with_cross_source_conflict",
            [
                {
                    "page": 1,
                    "method": "native_text",
                    "source_lines": CONFLICT_MEMO,
                    "native_source_lines": CONFLICT_MEMO,
                    "image_source_lines": [],
                    "overlap_source_lines": [],
                }
            ],
            challenge_factors=["independent memo layout", "time claims conflict with table scan"],
        ),
        _document(
            "phase3_unreadable_damaged_field_note.pdf",
            "damaged_scan_with_no_recoverable_text",
            [
                {
                    "page": 1,
                    "method": "ocr",
                    "source_lines": UNREADABLE_INTENDED,
                    "native_source_lines": [],
                    "image_source_lines": [],
                    "overlap_source_lines": [],
                    "recoverable": False,
                    "recognition_metrics_available": False,
                }
            ],
            challenge_factors=[
                "downsampled to 28 by 36 pixels then blurred; intended wording retained in labels"
            ],
            expected_unsupported_observations=0,
            recognition_metrics_available=False,
        ),
    ]
    for document in docs:
        data = files[document["filename"]]
        document["path"] = f"evals/phase3/sources/{document['filename']}"
        document["sha256"] = hashlib.sha256(data).hexdigest()
        document["bytes"] = len(data)
    return {
        "schema_version": "drillloop-ocr-phase3/v1",
        "exercise_date": "2026-11-19",
        "fictional": True,
        "labeling_note": "Expected source wording, times, page numbers, overlaps, and challenge factors were initially defined from the fictional sources before OCR. After the initial extraction run, a source-driven audit corrected the unknown-time category: the explicit 15:17 repeat is timed, while the no-time and 15:2? rows are unknown. The correction was based on source content, not OCR output. Labels are developer-authored and have not been independently adjudicated.",
        "label_audit_after_initial_ocr_run": True,
        "initial_labels_written_before_ocr": True,
        "labels_authored_from_source_content": True,
        "independently_adjudicated": False,
        "documents": docs,
        "cross_source_conflicts": [
            {
                "event_key": "station_b_pump_restored",
                "claims": [
                    {
                        "filename": "phase3_same_page_mixed_water_log.pdf",
                        "page": 1,
                        "time": "14:11",
                    },
                    {
                        "filename": "phase3_conflicting_dispatch_memo.pdf",
                        "page": 1,
                        "time": "14:12",
                    },
                ],
            },
            {
                "event_key": "valve_v10_closed",
                "claims": [
                    {
                        "filename": "phase3_two_page_valve_event_table_scan.pdf",
                        "page": 1,
                        "time": "15:17",
                    },
                    {
                        "filename": "phase3_conflicting_dispatch_memo.pdf",
                        "page": 1,
                        "time": "15:19",
                    },
                ],
            },
        ],
        "objective_labels": [
            {
                "objective_id": "OBJ-STATION-B-RESTORED",
                "event_key": "station_b_pump_restored",
                "expected_finding_code": "STATION_B_PUMP_RESTORED",
                "expected_finding_status": "proposed",
                "expected_review_decision": None,
                "expected_required_citation": {
                    "source": "phase3_same_page_mixed_water_log.pdf",
                    "locator": "page 1",
                },
            }
        ],
        "measurements_not_available": [
            "Production OCR accuracy: all Phase 3 PDFs and labels are fictional and developer-authored.",
            "Calibrated word confidence: OCR confidence is not calibrated for this application.",
            "Text character error rate for the intentionally unrecoverable page: no OCR transcription target is available for scoring; intended source wording is retained separately in labels.",
            "Pixel-level PDF highlighting accuracy: the application exposes page-level citations only.",
        ],
    }


def main() -> None:
    if OUTPUT.exists() and any(OUTPUT.iterdir()):
        raise SystemExit(f"Refusing to overwrite existing Phase 3 fixtures: {OUTPUT}")
    OUTPUT.mkdir(parents=True, exist_ok=True)

    mixed = _same_page_mixed_pdf()
    two_column_native = _two_column_native_pdf()
    two_column_render = _render_pdf_pages(two_column_native)[0]
    two_column_scan = _degrade(
        two_column_render,
        low_dpi=92,
        blur=0.42,
        skew_degrees=1.15,
        noise=0.06,
    )
    two_column = _image_pdf([two_column_scan], title="Fictional low-resolution two-column copy")
    two_column_render.close()
    two_column_scan.close()

    table_native = _table_native_pdf()
    table_images = _render_pdf_pages(table_native, dpi=300)
    table_scans = []
    for index, image in enumerate(table_images):
        table_scans.append(
            _degrade(
                image,
                low_dpi=135,
                page_size=landscape(letter),
                blur=0.18,
                skew_degrees=0.22 if index == 1 else 0,
                noise=0.025,
            )
        )
        image.close()
    table_scan = _image_pdf(
        table_scans,
        title="Fictional two-page scanned valve event table",
        size=landscape(letter),
    )
    for image in table_scans:
        image.close()

    conflict = _text_page(CONFLICT_MEMO, size=(600, 760), font_size=10)
    unreadable = _unreadable_scan_pdf()
    files = {
        "phase3_same_page_mixed_water_log.pdf": mixed,
        "phase3_two_column_low_resolution_scan.pdf": two_column,
        "phase3_two_page_valve_event_table_scan.pdf": table_scan,
        "phase3_conflicting_dispatch_memo.pdf": conflict,
        "phase3_unreadable_damaged_field_note.pdf": unreadable,
    }
    for filename, data in files.items():
        path = OUTPUT / filename
        if path.exists():
            raise SystemExit(f"Refusing to overwrite existing fixture: {path}")
        path.write_bytes(data)

    labels = _labels(files)
    label_path = ROOT / "evals" / "phase3" / "ground_truth.json"
    if label_path.exists():
        raise SystemExit(f"Refusing to overwrite existing labels: {label_path}")
    label_path.write_text(json.dumps(labels, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(
        json.dumps(
            {
                "result": "generated fictional Phase 3 OCR fixtures",
                "files": sorted(files),
                "ground_truth": str(label_path.relative_to(ROOT)),
                "ocr_was_not_run": True,
                "previous_phase2_data_modified": False,
            },
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
