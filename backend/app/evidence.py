from __future__ import annotations

import csv
import hashlib
import io
import json
import math
import re
import time
from dataclasses import dataclass
from datetime import date, datetime
from typing import Literal

SourcePurpose = Literal["performance", "planning", "published_evaluation"]
REFERENCE_SOURCE_LABELS = {
    "planning": "Planning document",
    "published_evaluation": "Published evaluation",
}


@dataclass
class ParsedObservation:
    text: str
    event_time_raw: str | None
    event_time_normalized: str | None
    time_confidence: str
    source_locator: str
    observation_type: str = "note"
    extraction_method: str = "parser"
    recognition_confidence: float | None = None


@dataclass
class ParsedEvidence:
    kind: str
    content_text: str
    observations: list[ParsedObservation]
    provenance: dict


class EvidenceError(Exception):
    def __init__(self, code: str, message: str, status_code: int = 400):
        self.code = code
        self.message = message
        self.status_code = status_code
        super().__init__(message)


TIME_RE = re.compile(r"\b(\d{1,2}:\d{2}(?::\d{2})?)\b")
PREFIX_TIME_RE = re.compile(r"^\s*(?:\[([^\]]+)\]|(\d{1,2}:\d{2}(?::\d{2})?))\s*[-–:]?\s*(.*)$")
MAX_EVIDENCE_BYTES = 15 * 1024 * 1024
MAX_PDF_PAGES = 250
MAX_EXTRACTED_CHARACTERS = 2_000_000
MAX_STRUCTURED_ROWS = 10_000
MAX_PDF_OBSERVATIONS = 10_000
MAX_OCR_PAGES = 20


def safe_filename(value: str | None) -> str:
    """Return a portable display filename without path components or controls."""
    normalized = (value or "evidence").replace("\\", "/").split("/")[-1]
    normalized = "".join(character for character in normalized if character.isprintable()).strip()
    return normalized[:255] or "evidence"


def normalize_time(
    raw: str | None, exercise_date: date, *, explicit: bool = False
) -> tuple[str | None, str]:
    if not raw:
        return None, "unknown"
    candidate = raw.strip()
    if not explicit or re.search(r"[Tt ]\d", candidate):
        try:
            parsed = datetime.fromisoformat(candidate.replace("Z", "+00:00"))
            if parsed.tzinfo:
                return parsed.isoformat(timespec="seconds"), "certain"
            return parsed.isoformat(timespec="seconds"), "medium"
        except ValueError:
            pass
    match = TIME_RE.fullmatch(candidate) if explicit else TIME_RE.search(candidate)
    if not match:
        return None, "unknown"
    time_text = match.group(1)
    fmt = "%H:%M:%S" if time_text.count(":") == 2 else "%H:%M"
    try:
        parsed_time = datetime.strptime(time_text, fmt).time()
    except ValueError:
        return None, "unknown"
    normalized = datetime.combine(exercise_date, parsed_time)
    return normalized.isoformat(timespec="seconds"), "medium"


def _observation(
    text: str,
    raw_time: str | None,
    locator: str,
    exercise_date: date,
    observation_type: str = "note",
    method: str = "parser",
    confidence: float | None = None,
) -> ParsedObservation:
    normalized, certainty = normalize_time(raw_time, exercise_date)
    if raw_time and normalized is None and method != "ocr":
        raise EvidenceError(
            "INVALID_TIMESTAMP",
            f"Timestamp {raw_time!r} is invalid. Use a valid ISO date/time or 24-hour time.",
        )
    if method == "asr" and confidence is not None and confidence < 0.75:
        certainty = "uncertain"
    if method == "ocr" and raw_time:
        # OCR-derived timestamps are reviewable source claims, not verified event times.
        certainty = "uncertain"
    return ParsedObservation(
        text=text.strip(),
        event_time_raw=raw_time,
        event_time_normalized=normalized,
        time_confidence=certainty,
        source_locator=locator,
        observation_type=observation_type,
        extraction_method=method,
        recognition_confidence=confidence,
    )


def parse_evidence(
    filename: str, mime_type: str, data: bytes, exercise_date: date
) -> ParsedEvidence:
    suffix = filename.lower().rsplit(".", 1)[-1] if "." in filename else ""
    normalized_mime = (mime_type or "").split(";", 1)[0].strip().lower()
    if not data:
        raise EvidenceError("EMPTY_FILE", "The uploaded file is empty.")
    if len(data) > MAX_EVIDENCE_BYTES:
        raise EvidenceError("FILE_TOO_LARGE", "Files are limited to 15 MB in the demo.", 413)
    mime_types = {
        "txt": {"text/plain"},
        "md": {"text/plain", "text/markdown"},
        "log": {"text/plain"},
        "csv": {"text/csv", "application/csv", "application/vnd.ms-excel"},
        "json": {"application/json", "text/json"},
        "pdf": {"application/pdf"},
    }
    if suffix not in mime_types:
        raise EvidenceError(
            "UNSUPPORTED_EVIDENCE", "Supported files: TXT, MD, LOG, CSV, JSON, PDF."
        )
    if normalized_mime not in {"", "application/octet-stream"} | mime_types[suffix]:
        raise EvidenceError(
            "CONTENT_TYPE_MISMATCH",
            f"The declared content type does not match the .{suffix} file format.",
            415,
        )
    digest = hashlib.sha256(data).hexdigest()

    if suffix in {"txt", "md", "log"}:
        try:
            content = data.decode("utf-8-sig")
        except UnicodeDecodeError as exc:
            raise EvidenceError(
                "UNSUPPORTED_ENCODING", "Text evidence must use UTF-8 encoding."
            ) from exc
        observations: list[ParsedObservation] = []
        for number, line in enumerate(content.splitlines(), 1):
            if not line.strip():
                continue
            match = PREFIX_TIME_RE.match(line)
            raw_time = (match.group(1) or match.group(2)) if match else None
            text = match.group(3) if match else line
            observations.append(_observation(text, raw_time, f"line {number}", exercise_date))
        return ParsedEvidence(
            "text", content, observations, {"sha256": digest, "encoding": "utf-8"}
        )

    if suffix == "csv" or mime_type == "text/csv":
        try:
            content = data.decode("utf-8-sig")
            reader = csv.DictReader(io.StringIO(content), strict=True)
            if not reader.fieldnames:
                raise EvidenceError("MALFORMED_CSV", "CSV must include a header row.")
            normalized_names = {field.lower().strip(): field for field in reader.fieldnames}
            if "" in normalized_names or len(normalized_names) != len(reader.fieldnames):
                raise EvidenceError("MALFORMED_CSV", "CSV headers must be non-empty and unique.")
            text_field = next(
                (
                    normalized_names[k]
                    for k in ("event", "text", "description", "observation")
                    if k in normalized_names
                ),
                None,
            )
            time_field = next(
                (
                    normalized_names[k]
                    for k in ("timestamp", "time", "event_time")
                    if k in normalized_names
                ),
                None,
            )
            if not text_field:
                raise EvidenceError(
                    "MALFORMED_CSV", "CSV needs an event, text, description, or observation column."
                )
            observations = []
            for row_no, row in enumerate(reader, 2):
                if row_no > MAX_STRUCTURED_ROWS + 1:
                    raise EvidenceError(
                        "TOO_MANY_ROWS", "CSV evidence is limited to 10,000 rows.", 413
                    )
                text = (row.get(text_field) or "").strip()
                if not text:
                    continue
                raw_time = (row.get(time_field) or "").strip() if time_field else None
                identifier = next(
                    (
                        value
                        for key, value in row.items()
                        if key and key.lower().strip() in {"id", "event_id"} and value
                    ),
                    None,
                )
                locator = f"row {row_no}" + (f" · {identifier}" if identifier else "")
                observations.append(
                    _observation(text, raw_time, locator, exercise_date, "event_log")
                )
            return ParsedEvidence(
                "csv", content, observations, {"sha256": digest, "columns": reader.fieldnames}
            )
        except UnicodeDecodeError as exc:
            raise EvidenceError(
                "UNSUPPORTED_ENCODING", "CSV evidence must use UTF-8 encoding."
            ) from exc
        except csv.Error as exc:
            raise EvidenceError("MALFORMED_CSV", f"Could not read CSV: {exc}") from exc

    if suffix == "json" or "json" in mime_type:
        try:
            payload = json.loads(data.decode("utf-8-sig"))
        except (UnicodeDecodeError, json.JSONDecodeError) as exc:
            raise EvidenceError("MALFORMED_JSON", "JSON evidence is not valid UTF-8 JSON.") from exc
        if isinstance(payload, dict) and isinstance(payload.get("segments"), list):
            if len(payload["segments"]) > MAX_STRUCTURED_ROWS:
                raise EvidenceError(
                    "TOO_MANY_ROWS", "JSON evidence is limited to 10,000 records.", 413
                )
            observations = []
            for index, segment in enumerate(payload["segments"], 1):
                if not isinstance(segment, dict) or not str(segment.get("text", "")).strip():
                    continue
                try:
                    start = float(segment.get("start", 0))
                    end = float(segment.get("end", start))
                except (TypeError, ValueError, OverflowError) as exc:
                    raise EvidenceError(
                        "INVALID_SEGMENT", f"Transcript segment {index} has invalid offsets."
                    ) from exc
                if not math.isfinite(start) or not math.isfinite(end) or start < 0 or end < start:
                    raise EvidenceError(
                        "INVALID_SEGMENT", f"Transcript segment {index} has invalid offsets."
                    )
                # Segment offsets locate speech inside the recording. They do not
                # establish when the event described by that speech occurred.
                # Only an explicitly supplied event_time is treated as event time.
                raw_time = segment.get("event_time")
                if raw_time is not None and not isinstance(raw_time, str):
                    raise EvidenceError(
                        "INVALID_TIMESTAMP",
                        f"Transcript segment {index} event_time must be an ISO timestamp or time string.",
                    )
                confidence = segment.get("confidence")
                try:
                    confidence = float(confidence) if confidence is not None else None
                except (TypeError, ValueError, OverflowError) as exc:
                    raise EvidenceError(
                        "INVALID_CONFIDENCE", f"Transcript segment {index} has invalid confidence."
                    ) from exc
                if confidence is not None and (
                    not math.isfinite(confidence) or not 0 <= confidence <= 1
                ):
                    raise EvidenceError(
                        "INVALID_CONFIDENCE", f"Transcript segment {index} has invalid confidence."
                    )
                obs = _observation(
                    str(segment["text"]),
                    raw_time,
                    f"segment {index} · {start:.2f}–{end:.2f}s",
                    exercise_date,
                    "transcript",
                    "asr" if payload.get("model") else "transcript",
                    confidence,
                )
                observations.append(obs)
            return ParsedEvidence(
                "transcript",
                json.dumps(payload, ensure_ascii=False),
                observations,
                {
                    "sha256": digest,
                    "model": payload.get("model", "unknown"),
                    "language": payload.get("language", "unknown"),
                    "uncertain_terms": payload.get("uncertain_terms", []),
                },
            )
        events = payload.get("events", []) if isinstance(payload, dict) else payload
        if not isinstance(events, list):
            raise EvidenceError(
                "UNSUPPORTED_JSON", "JSON must contain an events or segments array."
            )
        if len(events) > MAX_STRUCTURED_ROWS:
            raise EvidenceError("TOO_MANY_ROWS", "JSON evidence is limited to 10,000 records.", 413)
        observations = []
        for index, event in enumerate(events, 1):
            if not isinstance(event, dict):
                continue
            text = next(
                (
                    str(event[k])
                    for k in ("event", "text", "description", "observation")
                    if event.get(k)
                ),
                "",
            )
            if text:
                raw_time = next(
                    (str(event[k]) for k in ("timestamp", "time", "event_time") if event.get(k)),
                    None,
                )
                observations.append(
                    _observation(text, raw_time, f"event {index}", exercise_date, "event_log")
                )
        return ParsedEvidence(
            "json", json.dumps(payload, ensure_ascii=False), observations, {"sha256": digest}
        )

    if suffix == "pdf":
        if not data.startswith(b"%PDF-"):
            raise EvidenceError(
                "MALFORMED_PDF", "The uploaded file does not have a valid PDF header."
            )
        try:
            from pypdf import PdfReader

            document = PdfReader(io.BytesIO(data), strict=True)
            if len(document.pages) > MAX_PDF_PAGES:
                raise EvidenceError("TOO_MANY_PAGES", "PDF evidence is limited to 250 pages.", 413)
        except Exception as exc:
            if isinstance(exc, EvidenceError):
                raise
            raise EvidenceError("MALFORMED_PDF", "Could not open this PDF.") from exc
        page_texts: list[str] = []
        extracted_size = 0
        try:
            for page in document.pages:
                page_text = (page.extract_text() or "").strip()
                extracted_size += len(page_text)
                if extracted_size > MAX_EXTRACTED_CHARACTERS:
                    raise EvidenceError(
                        "EXTRACTED_TEXT_TOO_LARGE",
                        "Extracted PDF text exceeds the 2 MB limit.",
                        413,
                    )
                page_texts.append(page_text)
        except EvidenceError:
            raise
        except Exception as exc:
            raise EvidenceError(
                "MALFORMED_PDF", "Could not safely extract text from this PDF."
            ) from exc

        ocr_page_indices = [index for index, text in enumerate(page_texts) if not text]
        try:
            mixed_image_page_indices = [
                index
                for index, text in enumerate(page_texts)
                if text and len(document.pages[index].images) > 0
            ]
        except Exception as exc:
            raise EvidenceError(
                "MALFORMED_PDF", "Could not safely inspect embedded PDF images."
            ) from exc
        if len(ocr_page_indices) > MAX_OCR_PAGES:
            raise EvidenceError(
                "TOO_MANY_OCR_PAGES",
                f"PDF evidence is limited to {MAX_OCR_PAGES} pages requiring OCR.",
                413,
            )
        mixed_page_capacity = MAX_OCR_PAGES - len(ocr_page_indices)
        processed_mixed_page_indices = mixed_image_page_indices[:mixed_page_capacity]
        skipped_mixed_page_indices = mixed_image_page_indices[mixed_page_capacity:]
        ocr_target_indices = sorted(set(ocr_page_indices + processed_mixed_page_indices))
        page_extraction = [
            {
                "page": page_index,
                "method": (
                    "native_text_plus_ocr"
                    if page_index - 1 in mixed_image_page_indices
                    else "native_text"
                    if page_texts[page_index - 1]
                    else "ocr"
                ),
                "status": "pending"
                if page_index - 1 in ocr_target_indices
                else "partial"
                if page_index - 1 in skipped_mixed_page_indices
                else "skipped",
            }
            for page_index in range(1, len(page_texts) + 1)
        ]
        ocr_issues: list[dict[str, object]] = []
        ocr_image_regions: dict[int, int] = {}
        ocr_partial_pages: list[int] = [index + 1 for index in skipped_mixed_page_indices]
        if skipped_mixed_page_indices:
            ocr_issues.append(
                {
                    "page": skipped_mixed_page_indices[0] + 1,
                    "code": "OCR_PAGE_LIMIT",
                    "message": (
                        f"The {MAX_OCR_PAGES}-page OCR limit was reached. Selectable text was retained, "
                        f"but embedded image areas on {len(skipped_mixed_page_indices)} later page(s) "
                        "were not processed. Review those original pages."
                    ),
                }
            )
        provenance = {
            "sha256": digest,
            "pages": len(page_texts),
            "parser": "pypdf",
            "ocr_status": "partial"
            if skipped_mixed_page_indices
            else "not_required"
            if not ocr_target_indices
            else "completed",
            "page_extraction": page_extraction,
        }
        ocr_page_durations: dict[int, float] = {}
        ocr_page_segmentation_modes: dict[int, list[int]] = {}
        ocr_page_texts: dict[int, str] = {}

        def mark_ocr_partial(page_index: int, code: str, message: str) -> None:
            ocr_partial_pages.append(page_index + 1)
            page_extraction[page_index]["status"] = "partial"
            ocr_issues.append({"page": page_index + 1, "code": code, "message": message})

        if ocr_target_indices:
            from app.pdf_ocr import (
                PdfOcrError,
                check_pdf_ocr_runtime,
                ocr_pdf_image_regions,
                ocr_pdf_page,
            )

            has_native_text = any(page_texts)
            rendered_document = None
            try:
                runtime, pdfium = check_pdf_ocr_runtime()
                try:
                    rendered_document = pdfium.PdfDocument(data)
                except Exception as exc:
                    raise PdfOcrError(
                        "OCR_RENDER_FAILED", "Could not open this PDF for OCR."
                    ) from exc
            except PdfOcrError as exc:
                if not has_native_text:
                    raise EvidenceError(exc.code, exc.message, exc.status_code) from exc
                for page_index in ocr_target_indices:
                    mark_ocr_partial(page_index, exc.code, exc.message)

            if rendered_document is not None:
                ocr_started = time.perf_counter()
                try:
                    for page_index in ocr_target_indices:
                        try:
                            if page_index in ocr_page_indices:
                                page_text, page_duration, segmentation_modes = ocr_pdf_page(
                                    rendered_document, page_index, runtime
                                )
                                page_texts[page_index] = page_text
                                ocr_page_segmentation_modes[page_index + 1] = list(
                                    segmentation_modes
                                )
                                if not page_text:
                                    mark_ocr_partial(
                                        page_index,
                                        "OCR_NO_READABLE_TEXT",
                                        "OCR recovered no readable text. Review the original page.",
                                    )
                                else:
                                    page_extraction[page_index]["status"] = "completed"
                            else:
                                result = ocr_pdf_image_regions(
                                    rendered_document, page_index, runtime
                                )
                                page_text = result.text
                                page_duration = result.duration_seconds
                                ocr_page_texts[page_index] = page_text
                                ocr_image_regions[page_index + 1] = result.attempted_regions
                                if result.attempted_regions:
                                    ocr_page_segmentation_modes[page_index + 1] = [6]
                                page_extraction[page_index]["status"] = "completed"
                                for code, message in result.issues:
                                    mark_ocr_partial(page_index, code, message)
                        except PdfOcrError as exc:
                            if not has_native_text:
                                raise EvidenceError(exc.code, exc.message, exc.status_code) from exc
                            mark_ocr_partial(page_index, exc.code, exc.message)
                            continue
                        extracted_size += len(page_text)
                        if extracted_size > MAX_EXTRACTED_CHARACTERS:
                            raise EvidenceError(
                                "EXTRACTED_TEXT_TOO_LARGE",
                                "Extracted PDF text exceeds the 2 MB limit.",
                                413,
                            )
                        ocr_page_durations[page_index + 1] = round(page_duration, 4)
                finally:
                    rendered_document.close()

                duplicate_ocr_lines_suppressed = 0
                for page_index, ocr_text in ocr_page_texts.items():
                    native_lines = {
                        re.sub(r"\s+", " ", line).strip().casefold()
                        for line in page_texts[page_index].splitlines()
                        if line.strip()
                    }
                    kept_lines = []
                    for line in ocr_text.splitlines():
                        if not line.strip():
                            continue
                        key = re.sub(r"\s+", " ", line).strip().casefold()
                        if key in native_lines:
                            duplicate_ocr_lines_suppressed += 1
                            continue
                        kept_lines.append(line.strip())
                    ocr_page_texts[page_index] = "\n".join(kept_lines)
                provenance.update(
                    {
                        "ocr_engine": "Tesseract",
                        "ocr_engine_version": runtime.engine_version,
                        "ocr_language": "eng",
                        "ocr_renderer": "pypdfium2",
                        "ocr_renderer_version": runtime.renderer_version,
                        "ocr_dpi": 200,
                        "ocr_page_limit": MAX_OCR_PAGES,
                        "ocr_page_timeout_seconds": 4,
                        "ocr_pages": [index + 1 for index in ocr_target_indices],
                        "ocr_duration_seconds": round(time.perf_counter() - ocr_started, 4),
                        "ocr_page_durations_seconds": ocr_page_durations,
                        "ocr_page_segmentation_modes": ocr_page_segmentation_modes,
                        "ocr_word_confidence_available": False,
                        "ocr_line_positions_available": False,
                        "ocr_timestamp_confidence": "uncertain",
                        "ocr_image_regions": ocr_image_regions,
                        "ocr_duplicate_lines_suppressed": duplicate_ocr_lines_suppressed,
                        "ocr_issues": ocr_issues,
                        "ocr_partial_pages": [],
                    }
                )
        if ocr_partial_pages:
            provenance["ocr_status"] = "partial"
            provenance["ocr_partial_pages"] = sorted(set(ocr_partial_pages))
            provenance["ocr_issues"] = ocr_issues

        pages: list[str] = []
        observations = []
        for page_index, page_text in enumerate(page_texts, 1):
            ocr_text = ocr_page_texts.get(page_index - 1, "")
            combined_page_text = "\n".join(part for part in (page_text, ocr_text) if part.strip())
            pages.append(combined_page_text)
            method = page_extraction[page_index - 1]["method"]
            native_page = method in {"native_text", "native_text_plus_ocr"}
            lines_with_provenance = [
                (line, "parser" if native_page else "ocr", line_no)
                for line_no, line in enumerate(page_text.splitlines(), 1)
            ]
            if native_page:
                lines_with_provenance.extend((line, "ocr", None) for line in ocr_text.splitlines())
            for line, extraction_method, line_no in lines_with_provenance:
                if not line.strip():
                    continue
                match = PREFIX_TIME_RE.match(line)
                raw_time = (match.group(1) or match.group(2)) if match else None
                # A clock inside a bracketed instruction or example is source wording.
                if (
                    match
                    and match.group(1)
                    and normalize_time(raw_time, exercise_date, explicit=True)[0] is None
                ):
                    match = None
                    raw_time = None
                text = match.group(3) if match else line
                observations.append(
                    _observation(
                        text,
                        raw_time,
                        f"page {page_index}"
                        if extraction_method == "ocr"
                        else f"page {page_index}, line {line_no}",
                        exercise_date,
                        "document",
                        extraction_method,
                    )
                )
                if len(observations) > MAX_PDF_OBSERVATIONS:
                    raise EvidenceError(
                        "TOO_MANY_OBSERVATIONS",
                        f"PDF evidence is limited to {MAX_PDF_OBSERVATIONS:,} observations.",
                        413,
                    )
        content = "\n".join(f"[page {i + 1}]\n{text}" for i, text in enumerate(pages))
        if not any(page.strip() for page in pages):
            raise EvidenceError(
                "EMPTY_PDF", "No selectable or OCR-readable text was found in this PDF."
            )
        return ParsedEvidence("pdf", content, observations, provenance)

    raise EvidenceError(
        "UNSUPPORTED_EVIDENCE", "Supported files: TXT, MD, CSV, JSON transcript, and PDF."
    )
