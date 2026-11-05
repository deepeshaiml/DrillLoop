from __future__ import annotations

import csv
import hashlib
import io
import json
import math
import re
from dataclasses import dataclass
from datetime import date, datetime


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


def safe_filename(value: str | None) -> str:
    """Return a portable display filename without path components or controls."""
    normalized = (value or "evidence").replace("\\", "/").split("/")[-1]
    normalized = "".join(character for character in normalized if character.isprintable()).strip()
    return normalized[:255] or "evidence"


def normalize_time(raw: str | None, exercise_date: date) -> tuple[str | None, str]:
    if not raw:
        return None, "unknown"
    candidate = raw.strip()
    try:
        parsed = datetime.fromisoformat(candidate.replace("Z", "+00:00"))
        if parsed.tzinfo:
            return parsed.isoformat(timespec="seconds"), "certain"
        return parsed.isoformat(timespec="seconds"), "medium"
    except ValueError:
        pass
    match = TIME_RE.search(candidate)
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
    if raw_time and normalized is None:
        raise EvidenceError(
            "INVALID_TIMESTAMP",
            f"Timestamp {raw_time!r} is invalid. Use a valid ISO date/time or 24-hour time.",
        )
    if method == "asr" and confidence is not None and confidence < 0.75:
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
        pages: list[str] = []
        observations = []
        extracted_size = 0
        try:
            for page_index, page in enumerate(document.pages, 1):
                page_text = (page.extract_text() or "").strip()
                extracted_size += len(page_text)
                if extracted_size > MAX_EXTRACTED_CHARACTERS:
                    raise EvidenceError(
                        "EXTRACTED_TEXT_TOO_LARGE",
                        "Extracted PDF text exceeds the 2 MB limit.",
                        413,
                    )
                pages.append(page_text)
                for line_no, line in enumerate(page_text.splitlines(), 1):
                    if not line.strip():
                        continue
                    match = PREFIX_TIME_RE.match(line)
                    raw_time = (match.group(1) or match.group(2)) if match else None
                    text = match.group(3) if match else line
                    observations.append(
                        _observation(
                            text,
                            raw_time,
                            f"page {page_index}, line {line_no}",
                            exercise_date,
                            "document",
                        )
                    )
        except EvidenceError:
            raise
        except Exception as exc:
            raise EvidenceError(
                "MALFORMED_PDF", "Could not safely extract text from this PDF."
            ) from exc
        content = "\n".join(f"[page {i + 1}]\n{text}" for i, text in enumerate(pages))
        if not content.strip():
            raise EvidenceError(
                "EMPTY_PDF", "No selectable text was found. OCR is not available in this demo."
            )
        return ParsedEvidence(
            "pdf", content, observations, {"sha256": digest, "pages": len(pages), "parser": "pypdf"}
        )

    raise EvidenceError(
        "UNSUPPORTED_EVIDENCE", "Supported files: TXT, MD, CSV, JSON transcript, and text PDF."
    )
