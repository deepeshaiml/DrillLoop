from __future__ import annotations

import csv
import hashlib
import io
import json
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
    parsed_time = datetime.strptime(time_text, fmt).time()
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
    if not data:
        raise EvidenceError("EMPTY_FILE", "The uploaded file is empty.")
    if len(data) > 15 * 1024 * 1024:
        raise EvidenceError("FILE_TOO_LARGE", "Files are limited to 15 MB in the demo.", 413)
    digest = hashlib.sha256(data).hexdigest()

    if suffix in {"txt", "md", "log"} or (mime_type.startswith("text/") and suffix != "csv"):
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
            reader = csv.DictReader(io.StringIO(content))
            if not reader.fieldnames:
                raise EvidenceError("MALFORMED_CSV", "CSV must include a header row.")
            normalized_names = {field.lower().strip(): field for field in reader.fieldnames}
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
            base_time = payload.get("recording_started_at")
            observations = []
            for index, segment in enumerate(payload["segments"], 1):
                if not isinstance(segment, dict) or not str(segment.get("text", "")).strip():
                    continue
                start = float(segment.get("start", 0))
                end = float(segment.get("end", start))
                raw_time = None
                if base_time:
                    try:
                        from datetime import timedelta

                        raw_time = (
                            datetime.fromisoformat(base_time.replace("Z", "+00:00"))
                            + timedelta(seconds=start)
                        ).isoformat(timespec="seconds")
                    except ValueError:
                        raw_time = None
                confidence = segment.get("confidence")
                confidence = float(confidence) if confidence is not None else None
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

    if suffix == "pdf" or mime_type == "application/pdf":
        try:
            from pypdf import PdfReader

            document = PdfReader(io.BytesIO(data))
        except Exception as exc:
            raise EvidenceError("MALFORMED_PDF", "Could not open this PDF.") from exc
        pages: list[str] = []
        observations = []
        for page_index, page in enumerate(document.pages, 1):
            page_text = (page.extract_text() or "").strip()
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
