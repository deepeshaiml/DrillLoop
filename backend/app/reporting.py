from __future__ import annotations

from io import BytesIO
from xml.sax.saxutils import escape

from reportlab.lib import colors
from reportlab.lib.enums import TA_CENTER
from reportlab.lib.pagesizes import letter
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import inch
from reportlab.platypus import (
    KeepTogether,
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


def make_report_pdf(detail: dict) -> bytes:
    buffer = BytesIO()
    doc = SimpleDocTemplate(
        buffer,
        pagesize=letter,
        rightMargin=0.62 * inch,
        leftMargin=0.62 * inch,
        topMargin=0.62 * inch,
        bottomMargin=0.62 * inch,
        title="DrillLoop After-Action Report / Improvement Plan",
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
            "Fictional synthetic hospital power-outage exercise · evaluator review copy",
            styles["DLSub"],
        ),
    ]
    exercise = detail["exercise"]
    summary_rows = [
        ["EXERCISE ID", escape(exercise["id"])],
        ["SCENARIO", escape(exercise["title"])],
        [
            "DATE / DURATION",
            f"{escape(exercise['exercise_date'])} · {exercise['duration_minutes']} minutes",
        ],
        ["STATUS", "Draft · proposed findings require human review"],
    ]
    table = Table(summary_rows, colWidths=[1.45 * inch, 5.75 * inch])
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
        Paragraph(escape(exercise["scenario"]), styles["DLBody"]),
        Paragraph("Review status and use", styles["DLHead"]),
        Paragraph(
            "This report separates source observations from interpretation. All findings are proposed until an authorized evaluator approves them. Conflicting and missing timestamps remain unresolved. This working format draws on HSEEP AAR/IP concepts and is not FEMA certification.",
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
    story.append(Paragraph("Exercise timeline", styles["DLHead"]))
    timeline = detail["timeline"]
    if timeline:
        timeline_data = [["TIME", "OBSERVATION", "SOURCE", "CERTAINTY"]]
        for row in timeline:
            when = row["event_time_normalized"] or "Time unknown"
            snippet = row["text"][:165]
            source = f"{row['source_filename']} · {row['source_locator']}"
            timeline_data.append(
                [
                    escape(when[-8:] if "T" in when else when),
                    escape(snippet),
                    escape(source[:58]),
                    escape(row["time_confidence"]),
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
    for finding in detail["findings"]:
        status = finding["status"].upper()
        label = "STRENGTH" if finding["category"] == "strength" else "AREA FOR IMPROVEMENT"
        block = [
            Paragraph(
                f"<b>{escape(label)} · {escape(finding['title'])}</b> <font color='#0c8d8a'>[{escape(status)}]</font>",
                styles["DLBody"],
            ),
            Paragraph(
                f"<b>Objective:</b> {escape(finding['objective_id'] or 'Unmapped; evaluator mapping required')}",
                styles["DLSmall"],
            ),
            Paragraph(
                f"<b>Observed evidence summary:</b> {escape(finding['observation'])}",
                styles["DLBody"],
            ),
            Paragraph(
                f"<b>Interpretation:</b> {escape(finding['interpretation'])}", styles["DLBody"]
            ),
            Paragraph(
                f"<b>Evidence:</b> {escape('; '.join(finding['evidence_labels']))}",
                styles["DLSmall"],
            ),
        ]
        story.append(KeepTogether(block))
    story.append(Paragraph("Improvement plan / corrective-action register", styles["DLHead"]))
    action_rows = [["ACTION / ACCEPTANCE", "OWNER / DUE", "PRIORITY / STATUS"]]
    for action in detail["actions"]:
        text = f"<b>{escape(action['title'])}</b><br/><font size='7'>{escape(action['acceptance_criteria'])}</font>"
        owner = (
            escape(action["owner"] or "OWNER UNASSIGNED")
            + "<br/>"
            + escape(action["due_date"] or "Due date not set")
        )
        state = f"{escape(action['priority'])}<br/>{escape(action['reviewer_decision'])} · {escape(action['status'])}"
        action_rows.append(
            [
                Paragraph(text, styles["DLSmall"]),
                Paragraph(owner, styles["DLSmall"]),
                Paragraph(state, styles["DLSmall"]),
            ]
        )
    if len(action_rows) == 1:
        story.append(Paragraph("No corrective actions are proposed.", styles["DLBody"]))
    else:
        table = Table(action_rows, repeatRows=1, colWidths=[4.2 * inch, 1.62 * inch, 1.38 * inch])
        table.setStyle(
            TableStyle(
                [
                    ("BACKGROUND", (0, 0), (-1, 0), NAVY),
                    ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
                    ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
                    ("FONTSIZE", (0, 0), (-1, 0), 7.5),
                    ("GRID", (0, 0), (-1, -1), 0.3, colors.HexColor("#d6e0e5")),
                    ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, PALE]),
                    ("VALIGN", (0, 0), (-1, -1), "TOP"),
                    ("LEFTPADDING", (0, 0), (-1, -1), 5),
                    ("RIGHTPADDING", (0, 0), (-1, -1), 5),
                    ("TOPPADDING", (0, 0), (-1, -1), 6),
                    ("BOTTOMPADDING", (0, 0), (-1, -1), 6),
                ]
            )
        )
        story.append(table)
    story += [Spacer(1, 12), Paragraph("Source register", styles["DLHead"])]
    for source in detail["sources"]:
        story.append(
            Paragraph(
                f"{escape(source['filename'])} · {escape(source['kind'])} · SHA-256 {escape(source['sha256'])[:16]}…",
                styles["DLSmall"],
            )
        )
    story.append(Spacer(1, 12))
    story.append(
        Paragraph(
            "Prepared by DrillLoop local demo · Human reviewers retain authority over findings, action owners, acceptance, and closure. Do not use synthetic content as real operational guidance.",
            styles["DLSmall"],
        )
    )

    def footer(canvas, _doc):
        canvas.saveState()
        canvas.setStrokeColor(colors.HexColor("#d6e0e5"))
        canvas.line(0.62 * inch, 0.45 * inch, 7.88 * inch, 0.45 * inch)
        canvas.setFont("Helvetica", 7.5)
        canvas.setFillColor(MUTED)
        canvas.drawString(
            0.62 * inch, 0.29 * inch, "DRILLLOOP · Synthetic exercise · Draft for evaluator review"
        )
        canvas.drawRightString(7.88 * inch, 0.29 * inch, f"Page {_doc.page}")
        canvas.restoreState()

    doc.build(story, onFirstPage=footer, onLaterPages=footer)
    return buffer.getvalue()
