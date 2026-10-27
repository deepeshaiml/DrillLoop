# DrillLoop

**A review workspace for emergency exercise evidence and follow-up tasks.**

After an emergency exercise, teams often have notes, event logs, and transcripts in different files. DrillLoop puts them in one place, links each proposed finding to the exact source record, and tracks improvement tasks until a human reviewer checks the completion evidence.

The proposed first use case is hospital preparedness evaluators reviewing exercise records for an after-action report. The current demo uses one fictional hospital power-outage scenario; it has not been tested with a hospital team or an unfamiliar exercise. Other sectors are possible future markets, not validated customers.

**Example:** The fictional hospital log records a power failure at 09:02 (`EL-01`) and essential power restored at 09:06 (`EL-02`). The exercise target is 60 seconds. DrillLoop can propose that restoration took about four minutes and cite those two records. It cannot tell from those records *why* the delay happened, so the cause remains unknown. An evaluator must approve or reject the proposal.

All included exercise records are invented for demonstration. The generated **After-Action Report and Improvement Plan (AAR/IP)** uses ideas from FEMA’s **Homeland Security Exercise and Evaluation Program (HSEEP)**. It is not FEMA-certified and is not a clinical procedure or operational advice.

New to the project? Read the [Reader Guide](DRILLLOOP_READER_GUIDE.md) for a plain-language example, glossary, audience-specific reading paths, and a safe AI-agent example. The [Demo Guide](DEMO_GUIDE.md) walks through the working app.

## Run the demo

Requirements: Python 3.12, Node.js 22.12+ (or 24+), and npm. Docker Compose can start the app with a PostgreSQL database. For a quick judge demo, use the local setup below; it does not require Docker or a cloud service.

### Local setup

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt

cd frontend
npm ci
cd ..

.venv/bin/uvicorn app.main:app --app-dir backend --reload --port 8000
```

In another terminal:

```bash
cd frontend
npm run dev
```

Open <http://localhost:5173>. On first start the API seeds `HOSP-PO-2026-01` into `drillloop.db`; no cloud account or API key is used. The API is at <http://localhost:8000>, and its OpenAPI page is <http://localhost:8000/docs>.

The demo reviewer name and key are prefilled as `Exercise Reviewer` / `demo-reviewer`. Change the key with `REVIEWER_KEY` for a private demo. This is a shared demo password, not a full sign-in system. A real deployment would need named user accounts, different permissions for different jobs, and a record of who made each decision.

### Docker Compose

```bash
cp .env.example .env
docker compose up --build
```

Open <http://localhost:8000>. Compose runs the API/UI on PostgreSQL and persists data in the `drillloop-postgres` volume. Set `REVIEWER_KEY` and `POSTGRES_PASSWORD` in `.env` before sharing a network. The included defaults are for a laptop demo only.

### Tests and quality checks

```bash
.venv/bin/pytest -q
.venv/bin/ruff check backend
cd frontend && npm run build
```

The automated sample check runs with:

```bash
.venv/bin/python scripts/benchmark.py
```

It writes `demo/benchmark_results.json`. On the included synthetic example, the rules matched 8 of 8 labeled event rows, 5 of 5 expected findings, and 9 of 9 expected source-record links. These checks use the same small example that the project was built around; they do not predict performance on a different exercise.

No evaluators were timed. The team has not measured staff time saved, how many drafts evaluators would correct, the accuracy of automatic speech recognition (**ASR**, software that turns speech into text) on real audio, or the quality and speed of an optional local large language model (**LLM**, software that drafts or rephrases text). See the [Reader Guide](DRILLLOOP_READER_GUIDE.md) and [Evaluation Report](DrillLoop_Evaluation_Report.pdf) for definitions and limits.

## Generate the documents and deck

The generated deliverables are checked into the project root. To regenerate them:

```bash
.venv/bin/python scripts/generate_docs.py
npm --prefix presentation ci
npm --prefix presentation run build
soffice --headless --convert-to pdf --outdir . DrillLoop_Pitch_Deck.pptx
```

The idea PDF is exported from the editable Word document when LibreOffice is available (otherwise the script writes a ReportLab fallback). The PowerPoint is editable and contains presenter notes on every slide. LibreOffice is used here to export the slide PDF.

The Business Review deck was generated from a retained 14-slide template that is not included in this public repository because its redistribution terms are not established. To regenerate from that template, provide a local copy. To revise the existing editable deck, use the current PPTX as the input template; the generator reads it before replacing the output:

```bash
npm --prefix presentation ci
export DRILLLOOP_BUSINESS_REVIEW_TEMPLATE="$PWD/DrillLoop_Business_Review.pptx"
.venv/bin/python scripts/generate_business_review.py
soffice --headless --convert-to pdf --outdir . DrillLoop_Business_Review.pptx
```

## Demo workflow

1. Choose **Night Shift: Extended Power Loss**.
2. Review the timeline and the unresolved 09:10 / 09:11 acknowledgement discrepancy.
3. Open **Findings** and inspect each evidence link. Try the mismatched “two / too” transcript phrase; it is marked 58% confidence and is not needed for the time-discrepancy finding.
4. Approve or reject proposed findings with the reviewer key.
5. Update action owner, due date, and acceptance criteria. Approve an action only after its linked finding is approved; record closure evidence before closing it.
6. Export the editable working report as PDF.

The detailed walkthrough, reset choices, and visible error cases are in [DEMO_GUIDE.md](DEMO_GUIDE.md).

## What the app does with evidence

- Imports UTF-8 TXT/MD notes, CSV event logs, JSON event/transcript records, and selectable-text PDFs.
- Keeps the original uploaded file and records where extracted text came from: a CSV row, note line, PDF page, or transcript segment. It also stores a SHA-256 fingerprint (a checksum that helps detect whether the file later changes).
- Shows only times that appear in the evidence. A missing time stays unknown. If two people report different times, both remain visible until a reviewer resolves them.
- Uses a small set of understandable local rules to suggest candidate findings and link them to stated exercise objectives. This sample is small enough to search directly; it does not need a separate vector database or a free-running AI agent.
- Can optionally ask a local Ollama language model to reword a corrective-action draft. The model cannot invent a finding, change its evidence links, or approve it. No cloud AI service is needed.
- Can optionally turn audio into a draft transcript using faster-whisper. The model must be installed locally; it is not downloaded automatically. The demo does not claim speaker identification or accuracy in languages other than English. The provided transcript is pre-generated, not an audio transcription result.

Uploaded source bytes and extracted text are stored in the local database. Use fictional or otherwise permitted evidence in the demo. The included reviewer key is not suitable for production.

## Deliverables

- [Idea document (DOCX)](DrillLoop_Idea_Document.docx) and [PDF](DrillLoop_Idea_Document.pdf)
- [Eureka pitch deck (PPTX)](DrillLoop_Pitch_Deck.pptx) and [PDF](DrillLoop_Pitch_Deck.pdf) — 13 slides with speaker notes, hospital-first pilot hypothesis, and synthetic demo evidence.
- [Business Review deck (PPTX)](DrillLoop_Business_Review.pptx) and [PDF](DrillLoop_Business_Review.pdf) — separate 14-slide internal review; the Eureka pitch deck is the primary product pitch.
- [Business case](DrillLoop_Business_Case.pdf), [evaluation report](DrillLoop_Evaluation_Report.pdf), and [architecture SVG](DrillLoop_Architecture.svg)
- [Technical design](DrillLoop_Technical_Design.md), [demo guide](DEMO_GUIDE.md), and [plain-language Reader Guide with an AI-agent example](DRILLLOOP_READER_GUIDE.md)
- [Synthetic ground truth](demo/ground_truth.json), [evidence files](demo/evidence/), and [benchmark results](demo/benchmark_results.json)
- [Product screenshots](assets/)

## Research notes

The workflow borrows concepts from FEMA's 2020 HSEEP doctrine: define objectives, capture observations, analyze strengths and areas for improvement, and track corrective actions. California's public hospital power-loss exercise materials provide an adjacent scenario reference. Public product pages show that Veoci already markets AAR production and corrective-action follow-up; DrillLoop's evidence-to-source/reviewer/closure trace is a positioning hypothesis to test, not a validated claim of uniqueness.

References and license/version choices are recorded in [DrillLoop_Technical_Design.md](DrillLoop_Technical_Design.md).
