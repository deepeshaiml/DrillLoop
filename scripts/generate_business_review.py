"""Build a DrillLoop business review by editing a copy of the retained template."""

from __future__ import annotations

import json
import os
import posixpath
import re
import shutil
import subprocess
import tempfile
import zipfile
from pathlib import Path
from xml.etree import ElementTree as ET

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_TEMPLATE = (
    Path.home()
    / ".codex/plugins/cache/openai-curated-remote/openai-templates/0.1.1/skills"
    / "artifact-template-business-review/assets/reference.pptx"
)
TEMPLATE = Path(os.environ["DRILLLOOP_BUSINESS_REVIEW_TEMPLATE"]).expanduser() if os.environ.get("DRILLLOOP_BUSINESS_REVIEW_TEMPLATE") else DEFAULT_TEMPLATE
OUTPUT = ROOT / "DrillLoop_Business_Review.pptx"
PPTXGEN = ROOT / "presentation/node_modules/pptxgenjs"

P = "http://schemas.openxmlformats.org/presentationml/2006/main"
A = "http://schemas.openxmlformats.org/drawingml/2006/main"
C = "http://schemas.openxmlformats.org/drawingml/2006/chart"
R = "http://schemas.openxmlformats.org/officeDocument/2006/relationships"
REL = "http://schemas.openxmlformats.org/package/2006/relationships"
CT = "http://schemas.openxmlformats.org/package/2006/content-types"
S = "http://schemas.openxmlformats.org/spreadsheetml/2006/main"
NS = {"p": P, "a": A, "c": C, "r": R, "rel": REL, "ct": CT, "s": S}

TEXT: dict[int, dict[str, list[str]]] = {
    1: {
        "4": ["DrillLoop Q4 Business Review"],
        "5": [
            "Review of MVP delivery, synthetic demo results, illustrative economics, and next proof points. Customer demand, evaluator time savings, and real-world accuracy remain unvalidated."
        ],
        "6": ["Q4 2026 · Status as of 27 October"],
        "10": ["DrillLoop · Product review"],
    },
    2: {"3": ["MVP, evidence, economics, and decisions"], "5": ["Agenda"]},
    3: {
        "5": ["MVP Status"],
        "10": ["MVP recap, evidence, and decisions"],
        "11": ["Executive Summary"],
        "3": ["DEMO READY"],
        "534": [
            "DrillLoop turns exercise notes and event logs into source-linked finding drafts for evaluator review. The working demo covers exercise setup, evidence upload, timeline, human approval, corrective actions, and report export. Optional speech and writing models were not used in the reported benchmark."
        ],
        "7": ["What the benchmark shows"],
        "6": [
            "In one closed synthetic fixture, 8/8 log rows, 5/5 expected finding codes, and 9/9 expected evidence IDs matched. The citation check confirms that IDs were linked; it does not prove that evidence supports a claim or generalizes to new exercises."
        ],
        "17": ["Sponsor decision requested"],
        "16": [
            "Authorize discovery for a 90-day pilot with 2–3 hospital or municipal exercise teams, subject to partner interest and privacy approval. Measure source lookup, citation support, reviewer edits, action ownership, and verified closure."
        ],
        "14": ["Bottom line"],
        "18": [
            "No customer demand, willingness to pay, evaluator workload reduction, or real-world model accuracy has been measured. The next decision is whether to recruit pilot partners—not whether to scale a proven business."
        ],
    },
    4: {
        "533": ["Current business and delivery status"],
        "13": ["Working demo; commercial assumptions remain untested."],
        "12": [
            "The local demo is functional. It proposes findings with source links and leaves review decisions to authorized people."
        ],
        "14": ["Working MVP"],
        "10": [
            "Setup, uploads, linked timeline, evaluator review, action tracking, and PDF report export work in the demo."
        ],
        "17": ["Synthetic benchmark"],
        "16": [
            "One fictional case: 8/8 event rows, 5/5 findings, and 9/9 expected source IDs matched."
        ],
        "19": ["Buyer hypothesis"],
        "18": [
            "Hospitals and municipal teams are candidate pilots; demand and willingness to pay are untested."
        ],
        "21": ["Key risk"],
        "20": [
            "Real data needs approval. Citation quality, reviewer edits, and action closure need pilot validation."
        ],
    },
    5: {
        "533": ["Priorities for the next proof point"],
        "5": [
            "A 90-day pilot should answer three practical questions:"
        ],
        "3": [
            "Can evaluators find and verify source evidence faster?",
            "Do cited records support each draft finding, and can teams assign and verify improvement tasks? Use synthetic or specifically approved records. Compare the process with current manual review; do not assume savings before measuring them.",
        ],
        "28": ["Recruit pilot teams"],
        "27": ["Seek 2–3 willing hospital or municipal exercise teams and an evaluator contact."],
        "6": ["Measure review workload"],
        "4": ["Time evidence lookup and report drafting; count reviewer edits and citation corrections."],
        "9": ["Verify action closure"],
        "8": ["Check owners, due dates, completion tests, and reviewer-confirmed closure evidence."],
    },
    6: {
        "4": ["Value hypotheses to test"],
        "18": ["No savings or willingness to pay have been measured."],
        "17": [
            "The pilot should test source traceability, reviewer confidence, and action follow-through in existing exercise workflows.",
            "Existing platforms already offer after-action reports and follow-up tasks. DrillLoop’s positioning hypothesis is the connected trail from claim to source, reviewer decision, and verified closure—not report generation alone.",
        ],
        "6": [
            "Evidence trace",
            "Open the source row, note line, or transcript segment behind a proposed claim.",
        ],
        "12": [
            "Human review",
            "Keep each draft pending until an authorized evaluator approves or rejects it.",
        ],
        "13": [
            "Verified follow-through",
            "Track the owner and due date; close only after a reviewer checks completion proof.",
        ],
    },
    7: {
        "533": ["What is delivered—and what remains unproven"],
        "3": ["Delivered in the MVP"],
        "534": [
            "The app sets up exercises and accepts evaluator notes, event logs, and readable PDFs. It places recorded events on a timeline, flags conflicting times, and attaches each draft finding to its source.",
            "Reviewers can accept or reject drafts, assign owners and due dates, specify how completion will be checked, record closure proof, and export a report. A simple local database supports the demo; a deployment-ready database option is included.",
            "Optional speech-to-text and text-drafting models can run locally. Neither was used in the reported benchmark.",
        ],
        "2": [
            "Still unproven",
            "No customer interviews, paid pilots, manual timing baseline, reviewer correction study, real-audio accuracy, or local-model quality results are available.",
            "The perfect fixture scores reflect labels built for one fictional scenario. They do not establish general performance. Enterprise login, role-based access, and buyer demand also need validation.",
        ],
    },
    8: {
        "533": ["Target markets are hypotheses, not customers"],
        "3": [
            "Potential segments include hospitals, municipal emergency teams, airports, civil defense and disaster agencies, training providers, defense-support teams, and critical infrastructure operators. No customer list, sales pipeline, market-size estimate, or willingness-to-pay evidence is available. Validate use cases and purchasing paths before forecasting adoption.",
        ],
    },
    9: {
        "533": ["Synthetic benchmark: what actually matched"],
        "8": ["All perfect matches come from one closed fictional exercise fixture."],
        "7": [
            "The test checks whether expected rows, finding codes, and evidence links are present. A linked record ID does not prove that the source supports the claim.",
            "One timing disagreement was flagged and one untimed note stayed unplaced. No human evaluators, real audio, or unseen exercise records were tested.",
        ],
    },
    10: {
        "533": ["Synthetic fixture counts"],
        "18": ["Event rows"],
        "17": ["8 of 8 expected log rows were found."],
        "13": ["Finding codes"],
        "12": ["All 5 expected finding codes were proposed."],
        "15": ["Action owners"],
        "14": ["3 of 4 have owners; one is intentionally blank."],
    },
    11: {
        "533": ["Annual USD cases ($000)"],
        "3": ["$488k"],
        "7": ["Base-case revenue under listed assumptions."],
        "9": ["Loss"],
        "10": ["$157k shortfall after costs; not net profit."],
        "19": [
            "Base case: 15 annual plans, 40 exercises, one private deployment, eight templates, and 30 support days. Revenue / listed costs: conservative $177k / $385k; base $488k / $645k; high scale $2.05m / $1.87m. Planning assumptions, not a forecast; excludes tax and cash timing."
        ],
    },
    12: {
        "11": ["Next 12 months: validate before scaling"],
        "9": ["0–3 months"],
        "16": [
            "Run a measured pilot",
            "Work with 2–3 willing hospital or municipal teams. Measure source lookup, reviewer edits, citation support, action ownership, and verified closure.",
        ],
        "13": ["3–6 months"],
        "17": [
            "Harden what the pilot needs",
            "If the evidence supports it, assess organization login, configurable templates, private hosting, and integrations.",
        ],
        "14": ["6–12 months"],
        "18": [
            "Decide whether to add AI",
            "Evaluate optional speech or writing models only if measured quality, privacy controls, and reviewer workload justify them.",
        ],
    },
    13: {
        "533": ["Illustrative 90-day pilot workplan"],
        "10": ["Confirm willing teams and approve data use"],
        "9": ["Recruit evaluators; document today's workflow"],
        "8": ["Run matched evidence-review sessions"],
        "5": ["Score citations and reviewer corrections"],
        "7": ["Check action owners and closure evidence"],
        "6": ["Decision gate: continue only after approvals and evidence review"],
    },
    14: {
        "4": ["Decision requested"],
        "5": [
            "Authorize discovery for a 90-day, measurement-led pilot.",
            "Recruit 2–3 hospital or municipal teams if they are willing; use synthetic or specifically approved records after privacy review.",
            "Return with reviewer workload, citation quality, and closure-verification results before any decision to scale.",
        ],
    },
}

TABLES: dict[int, dict[str, list[list[str]]]] = {
    2: {
        "7": [
            ["01", "MVP status", "Build"],
            ["02", "Synthetic results", "Evidence"],
            ["03", "Customer segments", "Demand"],
            ["04", "Pricing assumptions", "Illustrative"],
            ["05", "Pilot priorities", "Next 90 days"],
            ["06", "Decision request", "Sponsor"],
        ]
    },
    9: {
        "2": [
            ["Metric", "Result", "What it shows", "Boundary"],
            ["Log rows", "8 / 8", "Expected rows found", "One fixture"],
            ["Findings", "5 / 5", "Expected codes found", "One fixture"],
            ["Citations", "9 / 9", "Expected IDs linked", "ID only"],
            ["Extra codes", "0 / 5", "No extra labels", "Closed set"],
            ["Uncited drafts", "0 / 5", "Each draft linked", "ID presence"],
            ["Timing", "1 + 1", "Conflict flagged; note unplaced", "One fixture"],
            ["Action fields", "31 / 32", "One owner blank", "Synthetic data"],
            ["Rule time", "4.61 / 9.13 ms", "Median / 95th percentile", "12 local calls"],
            ["Memory", "78.2 MB", "App and test tools", "No model"],
        ]
    },
    13: {
        "4": [
            ["Weeks 1–2", "Weeks 3–4", "Weeks 5–6", "Weeks 7–9", "Weeks 10–12"]
        ]
    },
}

CHARTS = {
    "ppt/charts/chart1.xml": {
        "title": "Synthetic fixture: expected vs matched counts",
        "categories": ["Event rows", "Findings", "Evidence IDs", "Action owners"],
        "series": [("Expected", [8, 5, 9, 4]), ("Observed", [8, 5, 9, 3])],
        "hide_second_labels": True,
    },
    "ppt/charts/chart2.xml": {
        "title": "Illustrative annual revenue and costs (USD thousands)",
        "categories": ["Conservative", "Base", "High scale"],
        "series": [("Revenue", [177, 488, 2050]), ("Listed costs", [385, 645, 1870])],
        "hide_second_labels": True,
    },
}

NOTES = [
    "Introduce this as an internal business review of a working hackathon MVP, not an operating company with proven revenue. The fictional hospital outage is demonstration data. The product promise is to keep draft findings connected to exact source records and human review.",
    "Use the agenda to move from what is built, to what the synthetic test measured, to what remains a market hypothesis. The figures later in the deck are either closed-fixture technical results or illustrative financial assumptions. The final section asks for a measured pilot discovery period.",
    "Summarize the MVP and the benchmark carefully: 8 of 8 log rows, 5 of 5 expected finding labels, and 9 of 9 expected evidence IDs matched in one synthetic fixture. An ID link is not a human judgment that the source supports the claim. The requested decision is to recruit pilot partners, conditional on their interest and privacy approval.",
    "The local demo includes exercise setup, evidence uploads, timeline, proposed findings, reviewer decisions, action tracking, and PDF export. The clean fixture results show that this workflow runs on its designed sample. They do not establish performance on new exercises. Hospitals and municipal teams are candidate users only; there is no measured buyer demand.",
    "Frame these as proposed pilot priorities. The pilot should measure evidence lookup time, evaluator corrections, citation support, and whether actions receive owners and verifiable closure proof. Use synthetic or explicitly approved records. Do not report time savings as cash savings until both the time effect and labor-cost basis are measured.",
    "After-action reports and corrective-action follow-up already exist in emergency-management platforms. DrillLoop should not claim those features are unique. The positioning hypothesis is a connected source-to-claim-to-review-to-closure trail. Pilot participants should decide whether that trace helps and whether it fits their current tools.",
    "Describe what is in the MVP and what is still missing. Optional faster-whisper speech transcription and local Ollama wording were not used in the benchmark. The sample fixture was deliberately built for the rules, so perfect scores do not predict performance elsewhere. No human workload or real-audio accuracy study was run.",
    "The listed organizations are customer segments to investigate, not clients, opportunities, or a sales pipeline. No market-size or adoption numbers are included because none are validated in the available sources. Discovery should identify who uses the workflow, who buys it, what existing platforms cover, and what data controls are required.",
    "Explain each benchmark result with its boundary. Event rows, finding labels, and evidence IDs are checked against one closed fictional fixture. Citation IDs being present does not prove semantic support. The conflict and untimed note remain visible. The 31-of-32 action field result includes one intentionally blank owner. The median is the middle request time; the 95th percentile is the time by which 95% of 12 local requests finished. Latency and memory exclude optional model inference.",
    "The chart compares expected with found or assigned counts in the single synthetic fixture. Categories have different denominators, so compare within a category rather than across categories. Action owners are 3 of 4 because one is intentionally missing. This is a pipeline check, not a field accuracy score.",
    "All prices and financial scenarios are illustrative USD assumptions from the business case, not market quotes or a forecast. The base case assumes 15 annual plans, 40 individual exercise workspaces, one private deployment, eight templates, and 30 support days. It produces $488,000 of modeled revenue against $645,000 of listed costs, or negative $157,000 after those costs. This excludes tax, financing, and cash timing and is not net profit.",
    "The roadmap is conditional. Start with a 90-day pilot if partners agree and privacy review permits the evidence used. Consider enterprise login, templates, integrations, or more AI only when pilot findings show what is needed and the added cost or risk is justified.",
    "This Gantt is an illustrative sequence, not a committed project schedule. Partner availability, evidence permissions, and local privacy requirements may change the timing. The decision gate is whether the pilot data supports another trial; it is not an automatic scale decision.",
    "Close with the requested next step: authorize discovery for a 90-day, measurement-led pilot and recruit two or three willing hospital or municipal exercise teams. Use synthetic or explicitly approved records only after review. Return with evidence on reviewer workload, citation quality, and verified action closure before considering scale.",
]


def xml_with_prefixes(data: bytes) -> ET.Element:
    text = data.decode("utf-8")
    for prefix, uri in re.findall(r'xmlns:([\w.-]+)="([^"]+)"', text):
        ET.register_namespace(prefix, uri)
    default = re.search(r'xmlns="([^"]+)"', text)
    if default:
        ET.register_namespace("", default.group(1))
    return ET.fromstring(data)


def xml_bytes(root: ET.Element) -> bytes:
    return ET.tostring(root, encoding="UTF-8", xml_declaration=True)


def text_nodes(paragraph: ET.Element) -> list[ET.Element]:
    return paragraph.findall(".//a:t", NS)


def set_paragraph(paragraph: ET.Element, text: str) -> None:
    nodes = text_nodes(paragraph)
    if not nodes:
        raise ValueError("Template paragraph has no editable text run")
    nodes[0].text = text
    for node in nodes[1:]:
        node.text = ""


def replace_shape(root: ET.Element, shape_id: str, paragraphs: list[str]) -> None:
    matches = []
    for shape in root.findall(".//p:sp", NS):
        nv = shape.find("p:nvSpPr/p:cNvPr", NS)
        if nv is not None and nv.get("id") == shape_id:
            matches.append(shape)
    if len(matches) != 1:
        raise ValueError(f"Expected one shape id {shape_id}; found {len(matches)}")
    tx = matches[0].find("p:txBody", NS)
    available = [p for p in tx.findall("a:p", NS) if any(t.text for t in text_nodes(p))]
    if len(available) != len(paragraphs):
        raise ValueError(
            f"Shape {shape_id}: expected {len(available)} populated paragraphs, got {len(paragraphs)}"
        )
    for paragraph, value in zip(available, paragraphs):
        set_paragraph(paragraph, value)


def replace_table(root: ET.Element, frame_id: str, rows: list[list[str]]) -> None:
    frames = []
    for frame in root.findall(".//p:graphicFrame", NS):
        nv = frame.find("p:nvGraphicFramePr/p:cNvPr", NS)
        if nv is not None and nv.get("id") == frame_id:
            frames.append(frame)
    if len(frames) != 1:
        raise ValueError(f"Expected one graphicFrame id {frame_id}; found {len(frames)}")
    table = frames[0].find("a:graphic/a:graphicData/a:tbl", NS)
    table_rows = table.findall("a:tr", NS)
    if len(table_rows) != len(rows):
        raise ValueError(f"Table {frame_id}: row count {len(table_rows)} != {len(rows)}")
    for table_row, values in zip(table_rows, rows):
        cells = table_row.findall("a:tc", NS)
        if len(cells) != len(values):
            raise ValueError(f"Table {frame_id}: column count mismatch")
        for cell, value in zip(cells, values):
            paragraphs = cell.findall("a:txBody/a:p", NS)
            populated = [p for p in paragraphs if any(t.text for t in text_nodes(p))]
            if not populated:
                raise ValueError("Table cell has no text run")
            set_paragraph(populated[0], value)
            for p in populated[1:]:
                set_paragraph(p, "")


def update_chart(root: ET.Element, spec: dict) -> None:
    chart = root.find(".//c:chart", NS)
    title = chart.find("c:title", NS)
    if title is not None:
        chart.remove(title)
    auto_title = chart.find("c:autoTitleDeleted", NS)
    if auto_title is None:
        auto_title = ET.Element(f"{{{C}}}autoTitleDeleted", {"val": "1"})
        chart.insert(0, auto_title)
    else:
        auto_title.set("val", "1")

    series_nodes = root.findall(".//c:ser", NS)
    if len(series_nodes) != len(spec["series"]):
        raise ValueError("Template chart series count changed")
    count = len(spec["categories"])
    for index, (ser, (name, values)) in enumerate(zip(series_nodes, spec["series"])):
        if len(values) != count:
            raise ValueError("Chart categories and data lengths differ")
        cols = ["B", "C"]
        for f in ser.findall(".//c:f", NS):
            formula = f.text or ""
            if "$A$2:$A$5" in formula:
                f.text = formula.replace("$A$2:$A$5", f"$A$2:$A${count + 1}")
            elif "$B$2:$B$5" in formula:
                f.text = formula.replace("$B$2:$B$5", f"${cols[index]}$2:${cols[index]}${count + 1}")
            elif "$C$2:$C$5" in formula:
                f.text = formula.replace("$C$2:$C$5", f"${cols[index]}$2:${cols[index]}${count + 1}")
            elif "$B$1" in formula or "$C$1" in formula:
                f.text = re.sub(r"\$[BC]\$1", f"${cols[index]}$1", formula)

        # Remove line-series value labels so they cannot collide with nearby bar labels.
        if index == 1 and spec.get("hide_second_labels", False):
            labels = ser.find("c:dLbls", NS)
            if labels is not None:
                ser.remove(labels)

        name_values = ser.findall("c:tx//c:v", NS)
        if not name_values:
            raise ValueError("Chart series name cache missing")
        name_values[0].text = name
        name_cache = ser.find("c:tx//c:strCache", NS)
        if name_cache is not None:
            name_cache.find("c:ptCount", NS).set("val", "1")
            for pt in name_cache.findall("c:pt", NS):
                name_cache.remove(pt)
            pt = ET.SubElement(name_cache, f"{{{C}}}pt", {"idx": "0"})
            ET.SubElement(pt, f"{{{C}}}v").text = name
        category_cache = ser.find("c:cat//c:strCache", NS)
        if category_cache is not None:
            category_cache.find("c:ptCount", NS).set("val", str(count))
            for pt in category_cache.findall("c:pt", NS):
                category_cache.remove(pt)
            for i, label in enumerate(spec["categories"]):
                pt = ET.SubElement(category_cache, f"{{{C}}}pt", {"idx": str(i)})
                ET.SubElement(pt, f"{{{C}}}v").text = label
        for cache in ser.findall(".//c:numCache", NS):
            count_node = cache.find("c:ptCount", NS)
            count_node.set("val", str(count))
            for pt in cache.findall("c:pt", NS):
                cache.remove(pt)
            for i, number in enumerate(values):
                pt = ET.Element(f"{{{C}}}pt", {"idx": str(i)})
                v = ET.SubElement(pt, f"{{{C}}}v")
                v.text = str(number)
                cache.append(pt)


def update_embedded_workbook(data: bytes, categories: list[str], series: list[tuple[str, list[int]]]) -> bytes:
    import io

    src = zipfile.ZipFile(io.BytesIO(data))
    strings = [" ", series[0][0], series[1][0], *categories]
    string_index = {text: idx for idx, text in enumerate(strings)}

    sheet = xml_with_prefixes(src.read("xl/worksheets/sheet1.xml"))
    sheet.find("s:dimension", NS).set("ref", f"A1:C{len(categories) + 1}")
    sheet_data = sheet.find("s:sheetData", NS)
    rows = sheet_data.findall("s:row", NS)
    for row in rows:
        rnum = int(row.get("r"))
        for cell in list(row.findall("s:c", NS)):
            if cell.get("r", "").startswith("D") or rnum > len(categories) + 1:
                row.remove(cell)
        if rnum > len(categories) + 1:
            sheet_data.remove(row)
    for rnum in range(1, len(categories) + 2):
        row = next((r for r in sheet_data.findall("s:row", NS) if int(r.get("r")) == rnum), None)
        if row is None:
            row = ET.SubElement(sheet_data, f"{{{S}}}row", {"r": str(rnum)})
        values: list[tuple[str, str, str]]
        if rnum == 1:
            values = [("A", " ", "s"), ("B", series[0][0], "s"), ("C", series[1][0], "s")]
        else:
            idx = rnum - 2
            values = [
                ("A", categories[idx], "s"),
                ("B", str(series[0][1][idx]), "n"),
                ("C", str(series[1][1][idx]), "n"),
            ]
        for col, val, kind in values:
            ref = f"{col}{rnum}"
            cell = next((c for c in row.findall("s:c", NS) if c.get("r") == ref), None)
            if cell is None:
                cell = ET.SubElement(row, f"{{{S}}}c", {"r": ref})
            if kind == "s":
                cell.set("t", "s")
                idx = string_index[val]
            else:
                cell.attrib.pop("t", None)
                idx = None
            v = cell.find("s:v", NS)
            if v is None:
                v = ET.SubElement(cell, f"{{{S}}}v")
            v.text = str(idx) if idx is not None else val
        # Keep cell order valid after updating the row.
        row[:] = sorted(row, key=lambda c: (c.tag.endswith("}c"), c.get("r", "")))

    shared = ET.Element(f"{{{S}}}sst", {"count": str(len(strings)), "uniqueCount": str(len(strings))})
    for value in strings:
        si = ET.SubElement(shared, f"{{{S}}}si")
        t = ET.SubElement(si, f"{{{S}}}t")
        if value[:1].isspace() or value[-1:].isspace():
            t.set("{http://www.w3.org/XML/1998/namespace}space", "preserve")
        t.text = value

    replacements = {
        "xl/worksheets/sheet1.xml": xml_bytes(sheet),
        "xl/sharedStrings.xml": xml_bytes(shared),
    }
    out = io.BytesIO()
    with zipfile.ZipFile(out, "w", zipfile.ZIP_DEFLATED) as z:
        for entry in src.infolist():
            z.writestr(entry, replacements.get(entry.filename, src.read(entry.filename)))
    src.close()
    return out.getvalue()


def notes_script() -> str:
    return """const fs=require('fs');\nconst pptxgen=require(process.argv[2]);\nconst notes=JSON.parse(fs.readFileSync(process.argv[3],'utf8'));\nconst pptx=new pptxgen(); pptx.layout='LAYOUT_WIDE';\nfor(const note of notes){const s=pptx.addSlide(); s.addNotes(note);}\npptx.writeFile({fileName:process.argv[4]});\n"""


def inject_notes(template_parts: dict[str, bytes], helper_path: Path) -> dict[str, bytes]:
    helper = zipfile.ZipFile(helper_path)
    names = helper.namelist()
    parts = dict(template_parts)
    for path in ["ppt/notesMasters/notesMaster1.xml", "ppt/notesMasters/_rels/notesMaster1.xml.rels"]:
        if path in names:
            parts[path] = helper.read(path)
    for index in range(1, len(NOTES) + 1):
        for path in [
            f"ppt/notesSlides/notesSlide{index}.xml",
            f"ppt/notesSlides/_rels/notesSlide{index}.xml.rels",
        ]:
            if path not in names:
                raise ValueError(f"PptxGenJS speaker note part missing: {path}")
            parts[path] = helper.read(path)

        rel_path = f"ppt/slides/_rels/slide{index}.xml.rels"
        rel_root = xml_with_prefixes(parts[rel_path])
        ids = [int(x.get("Id")[3:]) for x in rel_root if x.get("Id", "").startswith("rId") and x.get("Id")[3:].isdigit()]
        rid = f"rId{max(ids, default=0) + 1}"
        ET.SubElement(
            rel_root,
            f"{{{REL}}}Relationship",
            {
                "Id": rid,
                "Type": "http://schemas.openxmlformats.org/officeDocument/2006/relationships/notesSlide",
                "Target": f"../notesSlides/notesSlide{index}.xml",
            },
        )
        parts[rel_path] = xml_bytes(rel_root)

    presentation_rels = "ppt/_rels/presentation.xml.rels"
    rel_root = xml_with_prefixes(parts[presentation_rels])
    ids = [int(x.get("Id")[3:]) for x in rel_root if x.get("Id", "").startswith("rId") and x.get("Id")[3:].isdigit()]
    ET.SubElement(
        rel_root,
        f"{{{REL}}}Relationship",
        {
            "Id": f"rId{max(ids, default=0) + 1}",
            "Type": "http://schemas.openxmlformats.org/officeDocument/2006/relationships/notesMaster",
            "Target": "notesMasters/notesMaster1.xml",
        },
    )
    parts[presentation_rels] = xml_bytes(rel_root)

    ct_root = xml_with_prefixes(parts["[Content_Types].xml"])
    existing = {x.get("PartName") for x in ct_root.findall("ct:Override", NS)}
    overrides = [
        ("/ppt/notesMasters/notesMaster1.xml", "application/vnd.openxmlformats-officedocument.presentationml.notesMaster+xml")
    ]
    overrides.extend(
        (
            f"/ppt/notesSlides/notesSlide{index}.xml",
            "application/vnd.openxmlformats-officedocument.presentationml.notesSlide+xml",
        )
        for index in range(1, len(NOTES) + 1)
    )
    for part, content_type in overrides:
        if part not in existing:
            ET.SubElement(ct_root, f"{{{CT}}}Override", {"PartName": part, "ContentType": content_type})
    parts["[Content_Types].xml"] = xml_bytes(ct_root)
    helper.close()
    return parts


def main() -> None:
    if not TEMPLATE.exists():
        raise FileNotFoundError(
            f"Business Review template not found at {TEMPLATE}. Set "
            "DRILLLOOP_BUSINESS_REVIEW_TEMPLATE to a local template path."
        )
    parts: dict[str, bytes] = {}
    with zipfile.ZipFile(TEMPLATE) as source:
        for path in source.namelist():
            parts[path] = source.read(path)

    for slide_number, replacements in TEXT.items():
        path = f"ppt/slides/slide{slide_number}.xml"
        root = xml_with_prefixes(parts[path])
        for shape_id, paragraphs in replacements.items():
            replace_shape(root, shape_id, paragraphs)
        if slide_number in TABLES:
            for frame_id, rows in TABLES[slide_number].items():
                replace_table(root, frame_id, rows)
        parts[path] = xml_bytes(root)

    for path, spec in CHARTS.items():
        chart_root = xml_with_prefixes(parts[path])
        update_chart(chart_root, spec)
        parts[path] = xml_bytes(chart_root)

    # Keep the charts editable in PowerPoint by updating their embedded workbooks as well.
    for path, spec in CHARTS.items():
        rel_path = path.replace("ppt/charts/", "ppt/charts/_rels/") + ".rels"
        rel_root = xml_with_prefixes(parts[rel_path])
        relationship = next(
            x for x in rel_root if x.get("Type", "").endswith("/package")
        )
        workbook_path = posixpath.normpath(
            posixpath.join("ppt/charts", relationship.get("Target"))
        )
        parts[workbook_path] = update_embedded_workbook(
            parts[workbook_path], spec["categories"], spec["series"]
        )

    # Update document metadata without changing the reference file.
    if "docProps/core.xml" in parts:
        core = xml_with_prefixes(parts["docProps/core.xml"])
        dc = "http://purl.org/dc/elements/1.1/"
        title = core.find(f"{{{dc}}}title")
        if title is not None:
            title.text = "DrillLoop Business Review · Q4 2026"
        subject = core.find(f"{{{dc}}}subject")
        if subject is not None:
            subject.text = "MVP status, synthetic benchmark, commercial assumptions, and pilot decisions"
        parts["docProps/core.xml"] = xml_bytes(core)

    with tempfile.TemporaryDirectory(prefix="drillloop_business_review_") as td:
        temp = Path(td)
        helper_js = temp / "notes.js"
        notes_json = temp / "notes.json"
        helper_pptx = temp / "notes.pptx"
        helper_js.write_text(notes_script(), encoding="utf-8")
        notes_json.write_text(json.dumps(NOTES), encoding="utf-8")
        subprocess.run(
            ["node", str(helper_js), str(PPTXGEN), str(notes_json), str(helper_pptx)],
            check=True,
            cwd=ROOT,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
        )
        parts = inject_notes(parts, helper_pptx)

    with zipfile.ZipFile(OUTPUT, "w", zipfile.ZIP_DEFLATED) as target:
        for path, data in parts.items():
            target.writestr(path, data)
    print(f"Generated {OUTPUT.name} from the retained 14-slide Business Review template with notes.")


if __name__ == "__main__":
    main()
