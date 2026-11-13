from __future__ import annotations

from datetime import datetime
from io import BytesIO
from xml.sax.saxutils import escape

from reportlab.lib import colors
from reportlab.lib.enums import TA_CENTER
from reportlab.lib.pagesizes import letter
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import inch
from reportlab.platypus import (
    PageBreak,
    Paragraph,
    SimpleDocTemplate,
    Spacer,
    Table,
    TableStyle,
)

NAVY = colors.HexColor("#122a3a")
TEAL = colors.HexColor("#0c8d8a")
INK = colors.HexColor("#263849")
MUTED = colors.HexColor("#607487")
PALE = colors.HexColor("#edf3f5")
PACKAGED_DEMO_EXERCISE_ID = "HOSP-PO-2026-01"


def _is_known_synthetic_demo(exercise: dict) -> bool:
    return (
        exercise.get("id") == PACKAGED_DEMO_EXERCISE_ID
        and "fictional" in str(exercise.get("scenario", "")).casefold()
    )


def _events_for(detail: dict, object_id: str, actions: set[str]) -> list[dict]:
    return sorted(
        (
            event
            for event in detail.get("audit_events", [])
            if event.get("object_id") == object_id and event.get("action") in actions
        ),
        key=lambda event: event.get("created_at", ""),
    )


def _latest_event(detail: dict, object_id: str, action: str) -> dict | None:
    events = _events_for(detail, object_id, {action})
    return events[-1] if events else None


def _paragraph(text: object, style: ParagraphStyle) -> Paragraph:
    return Paragraph(escape(str(text or "")), style)


def _format_timestamp(value: object) -> str:
    timestamp = str(value or "Not recorded")
    try:
        parsed = datetime.fromisoformat(timestamp.replace("Z", "+00:00"))
    except ValueError:
        return timestamp
    offset = parsed.strftime("%z")
    if offset:
        offset = f" {offset[:3]}:{offset[3:]}"
    return f"{parsed:%Y-%m-%d} {parsed:%H:%M:%S}{offset}"


def _timestamp_markup(value: object) -> str:
    timestamp = _format_timestamp(value)
    if timestamp == str(value or "Not recorded") or " " not in timestamp:
        return escape(timestamp)
    date_part, time_part = timestamp.split(" ", 1)
    return f"{escape(date_part)}<br/>{escape(time_part)}"


def _decision_label(status: str) -> str:
    return {
        "proposed": "Proposed · no reviewer decision recorded",
        "approved": "Approved",
        "rejected": "Rejected",
        "closed": "Closed",
    }.get(status, status.replace("_", " ").title() or "Not recorded")


def make_report_pdf(detail: dict) -> bytes:
    exercise = detail["exercise"]
    known_synthetic_demo = _is_known_synthetic_demo(exercise)
    buffer = BytesIO()
    doc = SimpleDocTemplate(
        buffer,
        pagesize=letter,
        rightMargin=0.62 * inch,
        leftMargin=0.62 * inch,
        topMargin=0.62 * inch,
        bottomMargin=0.62 * inch,
        title=f"{exercise['title']} · After-Action Report / Improvement Plan",
        author="DrillLoop",
        subject=f"Exercise {exercise['id']} report",
    )
    styles = getSampleStyleSheet()
    styles.add(
        ParagraphStyle(
            name="DLTitle",
            parent=styles["Title"],
            fontName="Helvetica-Bold",
            fontSize=25,
            leading=30,
            textColor=NAVY,
            alignment=TA_CENTER,
            spaceAfter=9,
        )
    )
    styles.add(
        ParagraphStyle(
            name="DLSub",
            parent=styles["Normal"],
            fontSize=10,
            leading=15,
            textColor=MUTED,
            alignment=TA_CENTER,
            spaceAfter=18,
        )
    )
    styles.add(
        ParagraphStyle(
            name="DLHead",
            parent=styles["Heading2"],
            fontName="Helvetica-Bold",
            fontSize=14,
            leading=18,
            textColor=NAVY,
            spaceBefore=15,
            spaceAfter=8,
        )
    )
    styles.add(
        ParagraphStyle(
            name="DLBody",
            parent=styles["BodyText"],
            fontSize=9.2,
            leading=13,
            textColor=INK,
            spaceAfter=5,
        )
    )
    styles.add(
        ParagraphStyle(
            name="DLSmall",
            parent=styles["BodyText"],
            fontSize=8,
            leading=11,
            textColor=MUTED,
            spaceAfter=3,
        )
    )
    styles.add(
        ParagraphStyle(
            name="DLTableCell",
            parent=styles["Normal"],
            fontSize=7.2,
            leading=9,
            textColor=INK,
            spaceAfter=0,
        )
    )
    styles.add(
        ParagraphStyle(
            name="DLTableHeader",
            parent=styles["Normal"],
            fontName="Helvetica-Bold",
            fontSize=7.2,
            leading=9,
            textColor=colors.white,
            spaceAfter=0,
        )
    )
    styles.add(
        ParagraphStyle(
            name="DLSummaryLabel",
            parent=styles["Normal"],
            fontName="Helvetica-Bold",
            fontSize=8,
            leading=10,
            textColor=TEAL,
            spaceAfter=0,
        )
    )
    styles.add(
        ParagraphStyle(
            name="DLCallout",
            parent=styles["BodyText"],
            fontSize=8.5,
            leading=12,
            textColor=NAVY,
            backColor=PALE,
            borderPadding=8,
            spaceBefore=5,
            spaceAfter=8,
        )
    )
    story = [
        Paragraph("DRILLLOOP", styles["DLSub"]),
        Paragraph("After-Action Report &amp; Improvement Plan", styles["DLTitle"]),
        Paragraph(
            (
                "Fictional synthetic exercise · evaluator review copy"
                if known_synthetic_demo
                else "Exercise report · evaluator review copy"
            ),
            styles["DLSub"],
        ),
    ]
    findings = detail.get("findings", [])
    actions = detail.get("actions", [])
    finding_counts = {
        status: sum(1 for finding in findings if finding.get("status") == status)
        for status in ("proposed", "approved", "rejected")
    }
    action_counts = {
        status: sum(1 for action in actions if action.get("status") == status)
        for status in ("proposed", "approved", "rejected", "closed")
    }
    review_summary = (
        f"Findings: {finding_counts['proposed']} proposed · "
        f"{finding_counts['approved']} approved · {finding_counts['rejected']} rejected. "
        f"Actions: {action_counts['proposed']} proposed · {action_counts['approved']} approved · "
        f"{action_counts['rejected']} rejected · {action_counts['closed']} closed."
    )
    summary_rows = [
        ["EXERCISE NAME", _paragraph(exercise.get("title", "Not provided"), styles["DLBody"])],
        ["EXERCISE ID", _paragraph(exercise.get("id", "Not recorded"), styles["DLBody"])],
        [
            "DATE / DURATION",
            _paragraph(
                f"{exercise.get('exercise_date') or 'Not recorded'} · "
                f"{exercise.get('duration_minutes', 'Not recorded')} minutes",
                styles["DLBody"],
            ),
        ],
        ["CURRENT REVIEW STATE", _paragraph(review_summary, styles["DLBody"])],
    ]
    table = Table(
        [
            [
                _paragraph(label, styles["DLSummaryLabel"]),
                value if isinstance(value, Paragraph) else _paragraph(value, styles["DLBody"]),
            ]
            for label, value in summary_rows
        ],
        colWidths=[1.7 * inch, 5.5 * inch],
        splitInRow=1,
    )
    table.setStyle(
        TableStyle(
            [
                ("BACKGROUND", (0, 0), (0, -1), PALE),
                ("TEXTCOLOR", (0, 0), (0, -1), TEAL),
                ("FONTNAME", (0, 0), (0, -1), "Helvetica-Bold"),
                ("FONTSIZE", (0, 0), (-1, -1), 8.5),
                ("TEXTCOLOR", (1, 0), (1, -1), INK),
                ("GRID", (0, 0), (-1, -1), 0.35, colors.HexColor("#d6e0e5")),
                ("VALIGN", (0, 0), (-1, -1), "TOP"),
                ("LEFTPADDING", (0, 0), (-1, -1), 8),
                ("RIGHTPADDING", (0, 0), (-1, -1), 8),
                ("TOPPADDING", (0, 0), (-1, -1), 7),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 7),
            ]
        )
    )
    story += [
        table,
        Spacer(1, 10),
        Paragraph(
            escape(exercise.get("scenario", "Exercise description not provided.")), styles["DLBody"]
        ),
        Paragraph("Review status and use", styles["DLHead"]),
        Paragraph(
            "This report reflects the exercise records available at export time. Proposed findings have no recorded reviewer decision; approved and rejected labels reflect the current stored decision. Interpretation is shown separately from source wording. Conflicting and missing timestamps remain unresolved. This working format draws on HSEEP AAR/IP concepts and is not FEMA certification.",
            styles["DLCallout"],
        ),
    ]

    story.append(Paragraph("Objectives and expected milestones", styles["DLHead"]))
    for objective in exercise["objectives"]:
        story.append(
            Paragraph(
                f"<b>{escape(objective.get('id', 'Objective'))}</b> — {escape(objective.get('text', ''))}",
                styles["DLBody"],
            )
        )
    if not exercise.get("objectives"):
        story.append(Paragraph("No objectives are recorded for this exercise.", styles["DLBody"]))
    milestones = exercise.get("expected_milestones", [])
    if milestones:
        story.append(Paragraph("Expected milestones", styles["DLHead"]))
        for milestone in milestones:
            milestone_text = milestone.get("expected", "")
            milestone_id = milestone.get("id")
            objective_id = milestone.get("objective_id")
            references = " · ".join(value for value in (milestone_id, objective_id) if value)
            prefix = f"<b>{escape(references)}</b> — " if references else ""
            story.append(Paragraph(f"{prefix}{escape(milestone_text)}", styles["DLBody"]))
    story.append(Paragraph("Exercise timeline", styles["DLHead"]))
    timeline = detail["timeline"]
    if timeline:
        timeline_data = [
            [
                Paragraph(label, styles["DLTableHeader"])
                for label in ("TIME", "OBSERVATION", "SOURCE", "CERTAINTY")
            ]
        ]
        for row in timeline:
            when = row["event_time_normalized"] or "Time unknown"
            snippet = row["text"][:165]
            source = f"{row['source_filename']} · {row['source_locator']}"
            timeline_data.append(
                [
                    Paragraph(escape(when[-8:] if "T" in when else when), styles["DLTableCell"]),
                    Paragraph(escape(snippet), styles["DLTableCell"]),
                    Paragraph(escape(source), styles["DLTableCell"]),
                    Paragraph(escape(row["time_confidence"]), styles["DLTableCell"]),
                ]
            )
        table = Table(
            timeline_data,
            repeatRows=1,
            colWidths=[0.68 * inch, 3.65 * inch, 2.05 * inch, 0.82 * inch],
        )
        table.setStyle(
            TableStyle(
                [
                    ("BACKGROUND", (0, 0), (-1, 0), NAVY),
                    ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
                    ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
                    ("FONTSIZE", (0, 0), (-1, -1), 7.2),
                    ("LEADING", (0, 0), (-1, -1), 9),
                    ("TEXTCOLOR", (0, 1), (-1, -1), INK),
                    ("GRID", (0, 0), (-1, -1), 0.25, colors.HexColor("#d6e0e5")),
                    ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, PALE]),
                    ("VALIGN", (0, 0), (-1, -1), "TOP"),
                    ("LEFTPADDING", (0, 0), (-1, -1), 5),
                    ("RIGHTPADDING", (0, 0), (-1, -1), 5),
                    ("TOPPADDING", (0, 0), (-1, -1), 4),
                    ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
                ]
            )
        )
        story.append(table)
    else:
        story.append(Paragraph("No extracted observations are available.", styles["DLBody"]))
    if detail["timeline_conflicts"]:
        story.append(Paragraph("Unresolved timing conflicts", styles["DLHead"]))
        for conflict in detail["timeline_conflicts"]:
            story.append(
                Paragraph(
                    f"• {escape(conflict['description'])} — {escape(conflict['source_locator'])}",
                    styles["DLBody"],
                )
            )

    story.append(PageBreak())
    story.append(Paragraph("Findings and objective analysis", styles["DLHead"]))
    if not findings:
        story.append(Paragraph("No findings are recorded for this exercise.", styles["DLBody"]))
    for finding in findings:
        finding_id = finding.get("id", "")
        status = finding.get("status", "proposed")
        label = "STRENGTH" if finding.get("category") == "strength" else "AREA FOR IMPROVEMENT"
        decision_event = (
            _latest_event(detail, finding_id, f"finding_{status}")
            if status in {"approved", "rejected"}
            else None
        )
        reviewer = (
            (decision_event or {}).get("actor")
            or (finding.get("reviewer") if status in {"approved", "rejected"} else None)
            or "Not recorded"
        )
        decision_time = _format_timestamp(
            (decision_event or {}).get("created_at") or "Not recorded in audit history"
        )
        decision_details = (decision_event or {}).get("details") or {}
        review_note = (
            finding.get("review_note")
            or decision_details.get("note")
            or "No reviewer note recorded."
        )
        citations = finding.get("evidence_labels") or []
        story.append(
            Paragraph(
                f"<b>{escape(label)} · {escape(finding.get('title', 'Untitled finding'))}</b> "
                f"<font color='#0c8d8a'>[{escape(status.upper())}]</font>",
                styles["DLBody"],
            )
        )
        story.append(
            Paragraph(
                f"<b>Objective:</b> {escape(finding.get('objective_id') or 'Not mapped')}",
                styles["DLSmall"],
            )
        )
        story.append(
            Paragraph(
                f"<b>Observed evidence summary:</b> {escape(finding.get('observation') or 'Not provided')}",
                styles["DLBody"],
            )
        )
        story.append(
            Paragraph(
                f"<b>Analysis-time interpretation</b> <font color='#607487'>(stored with the finding; may predate the current reviewer decision)</font><br/>{escape(finding.get('interpretation') or 'Not provided')}",
                styles["DLBody"],
            )
        )
        if status in {"approved", "rejected"}:
            reviewer_status = (
                f"{_decision_label(status)} by {reviewer} · {decision_time}. "
                f"Reviewer note: {review_note}"
            )
        else:
            reviewer_status = "Proposed · no reviewer decision is recorded."
        story.append(
            Paragraph(
                f"<b>Current reviewer status:</b> {escape(reviewer_status)}", styles["DLSmall"]
            )
        )
        story.append(
            Paragraph(
                f"<b>Evidence citations:</b> {escape('; '.join(citations) if citations else 'No linked source references are recorded.')}",
                styles["DLSmall"],
            )
        )
    if actions:
        story.append(PageBreak())
    story.append(Paragraph("Improvement plan / corrective-action register", styles["DLHead"]))
    finding_by_id = {finding.get("id"): finding for finding in findings}
    if not actions:
        story.append(
            Paragraph("No corrective actions are recorded for this exercise.", styles["DLBody"])
        )
    for action in actions:
        action_id = action.get("id", "")
        status = action.get("status", "proposed")
        reviewer_decision = action.get("reviewer_decision") or "Not recorded"
        approval_event = (
            _latest_event(detail, action_id, f"action_{reviewer_decision}")
            if reviewer_decision in {"approved", "rejected"}
            else None
        )
        closure_event = _latest_event(detail, action_id, "action_closed")
        approval_actor = (
            (approval_event or {}).get("actor")
            or (action.get("reviewer") if reviewer_decision in {"approved", "rejected"} else None)
            or "Not recorded"
        )
        approval_time = _format_timestamp(
            (approval_event or {}).get("created_at") or "Not recorded in audit history"
        )
        approval_note = ((approval_event or {}).get("details") or {}).get(
            "note"
        ) or "No reviewer note recorded."
        finding = finding_by_id.get(action.get("finding_id"))
        linked_finding = (
            finding.get("title")
            if finding
            else action.get("finding_title") or "Not found in current report records"
        )
        owner = action.get("owner") or "Not recorded"
        due_date = action.get("due_date") or "Not recorded"
        acceptance = action.get("acceptance_criteria") or "Not provided"
        closure_evidence = action.get("closure_evidence") or ""
        if status == "closed" and closure_evidence.strip():
            closure_state = "Closed with recorded evidence. This is not independent verification of completed work."
        elif status == "closed":
            closure_state = "Closed status is recorded; closure evidence is not present in the current action record."
        elif closure_evidence.strip():
            closure_state = f"Closure evidence text is recorded; current action status is {_decision_label(status)}."
        else:
            closure_state = "No closure evidence recorded."
        story.append(
            Paragraph(
                f"<b>{escape(action.get('title') or 'Untitled action')}</b> "
                f"<font color='#0c8d8a'>[{escape(status.upper())}]</font>",
                styles["DLBody"],
            )
        )
        story.append(
            Paragraph(f"<b>Linked finding:</b> {escape(linked_finding)}", styles["DLSmall"])
        )
        story.append(
            Paragraph(
                f"<b>Owner:</b> {escape(owner)} · <b>Due date:</b> {escape(due_date)} · "
                f"<b>Priority:</b> {escape(action.get('priority') or 'Not recorded')}",
                styles["DLSmall"],
            )
        )
        if reviewer_decision in {"approved", "rejected"}:
            action_decision_text = (
                f"{reviewer_decision.title()} by {approval_actor} at {approval_time}. "
                f"Reviewer note: {approval_note}"
            )
        else:
            action_decision_text = (
                f"{reviewer_decision.title()} · no reviewer decision is recorded."
            )
        story.append(
            Paragraph(
                f"<b>Current reviewer decision:</b> {escape(action_decision_text)} · "
                f"<b>Current action status:</b> {escape(_decision_label(status))}.",
                styles["DLSmall"],
            )
        )
        if closure_event:
            story.append(
                Paragraph(
                    f"<b>Closure attribution:</b> {escape(closure_event.get('actor') or 'Not recorded')} · "
                    f"{escape(_format_timestamp(closure_event.get('created_at') or 'Time not recorded'))}",
                    styles["DLSmall"],
                )
            )
        story.append(
            Paragraph(f"<b>Acceptance criteria:</b> {escape(acceptance)}", styles["DLBody"])
        )
        story.append(Paragraph(f"<b>{escape(closure_state)}</b>", styles["DLSmall"]))
        if closure_evidence.strip():
            story.append(
                Paragraph(
                    f"<b>Recorded closure evidence:</b> {escape(closure_evidence)}",
                    styles["DLBody"],
                )
            )
        story.append(Spacer(1, 8))
    review_events = [
        event
        for event in detail.get("audit_events", [])
        if event.get("action")
        in {
            "finding_approved",
            "finding_rejected",
            "action_approved",
            "action_rejected",
            "action_closed",
        }
    ]
    if review_events:
        story.append(PageBreak())
    story += [Spacer(1, 12), Paragraph("Finding and action decision history", styles["DLHead"])]
    if review_events:
        finding_by_id = {finding.get("id"): finding for finding in findings}
        action_by_id = {action.get("id"): action for action in actions}
        history_rows = [
            [
                Paragraph(label, styles["DLTableHeader"])
                for label in ("RECORDED AT", "RECORD", "EVENT", "REVIEWER / ACTOR", "NOTE")
            ]
        ]
        for event in sorted(review_events, key=lambda row: row.get("created_at", "")):
            record = (
                finding_by_id.get(event.get("object_id"))
                or action_by_id.get(event.get("object_id"))
                or {}
            )
            record_title = record.get("title") or event.get("object_id") or "Record not identified"
            event_label = event.get("action", "").replace("_", " ").title()
            note = ((event.get("details") or {}).get("note") or "").strip()
            if event.get("action") == "action_closed" and not note:
                note = "Closure evidence is shown in the action register."
            if not note:
                note = "No note recorded."
            history_rows.append(
                [
                    Paragraph(_timestamp_markup(event.get("created_at")), styles["DLTableCell"]),
                    Paragraph(escape(record_title), styles["DLTableCell"]),
                    Paragraph(escape(event_label), styles["DLTableCell"]),
                    Paragraph(escape(event.get("actor") or "Not recorded"), styles["DLTableCell"]),
                    Paragraph(escape(note), styles["DLTableCell"]),
                ]
            )
        history_table = Table(
            history_rows,
            repeatRows=1,
            splitInRow=1,
            colWidths=[1.2 * inch, 1.55 * inch, 1.05 * inch, 1.1 * inch, 2.3 * inch],
        )
        history_table.setStyle(
            TableStyle(
                [
                    ("BACKGROUND", (0, 0), (-1, 0), NAVY),
                    ("GRID", (0, 0), (-1, -1), 0.3, colors.HexColor("#d6e0e5")),
                    ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, PALE]),
                    ("VALIGN", (0, 0), (-1, -1), "TOP"),
                    ("LEFTPADDING", (0, 0), (-1, -1), 5),
                    ("RIGHTPADDING", (0, 0), (-1, -1), 5),
                    ("TOPPADDING", (0, 0), (-1, -1), 4),
                    ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
                ]
            )
        )
        story.append(history_table)
    else:
        story.append(
            Paragraph(
                "No finding or action review/closure audit events are recorded.", styles["DLBody"]
            )
        )
    story += [Spacer(1, 12), Paragraph("Source register", styles["DLHead"])]
    for source in detail.get("sources", []):
        story.append(
            Paragraph(
                f"{escape(source.get('filename') or 'Filename not recorded')} · "
                f"{escape(source.get('kind') or 'Type not recorded')} · SHA-256 "
                f"{escape(source.get('sha256') or 'Not recorded')[:16]}…",
                styles["DLSmall"],
            )
        )
    story.append(Spacer(1, 12))
    story.append(
        Paragraph(
            "Human reviewers retain authority over findings, action decisions, and closure. Recorded closure evidence is not independent verification that corrective work is complete."
            + (
                " This packaged exercise is fictional; do not use its synthetic content as real operational guidance."
                if known_synthetic_demo
                else ""
            ),
            styles["DLSmall"],
        )
    )

    def footer(canvas, _doc):
        canvas.saveState()
        canvas.setStrokeColor(colors.HexColor("#d6e0e5"))
        canvas.line(0.62 * inch, 0.45 * inch, 7.88 * inch, 0.45 * inch)
        canvas.setFont("Helvetica", 7.5)
        canvas.setFillColor(MUTED)
        footer_label = (
            "DRILLLOOP · Fictional synthetic exercise · Draft for evaluator review"
            if known_synthetic_demo
            else "DRILLLOOP · Exercise report · Draft for evaluator review"
        )
        canvas.drawString(0.62 * inch, 0.29 * inch, footer_label)
        canvas.drawRightString(7.88 * inch, 0.29 * inch, f"Page {_doc.page}")
        canvas.restoreState()

    doc.build(story, onFirstPage=footer, onLaterPages=footer)
    return buffer.getvalue()
