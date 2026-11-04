# DrillLoop

**A review workspace for emergency exercise evidence and follow-up tasks.**

After an emergency exercise, teams often have notes, event logs, and transcripts in different files. DrillLoop puts them in one place, links each proposed finding to the exact source record, and tracks improvement tasks until a human reviewer checks the completion evidence.

The proposed first use case is hospital preparedness evaluators reviewing exercise records for an after-action report. The packaged hospital power-outage scenario is fictional. The application has now been exercised with unfamiliar fictional CSV evidence, but it has not been evaluated on permitted real records or with representative hospital teams. Other sectors are possible future markets, not validated customers.

**Example:** The fictional hospital log records a power failure at 09:02 (`EL-01`) and essential power restored at 09:06 (`EL-02`). The exercise target is 60 seconds. DrillLoop can propose that restoration took about four minutes and cite those two records. It cannot tell from those records *why* the delay happened, so the cause remains unknown. An evaluator must approve or reject the proposal.

All included exercise records are invented for demonstration. The generated **After-Action Report and Improvement Plan (AAR/IP)** uses ideas from FEMA’s **Homeland Security Exercise and Evaluation Program (HSEEP)**. It is not FEMA-certified and is not a clinical procedure or operational advice.

New to the project? Read the [Reader Guide](DRILLLOOP_READER_GUIDE.md) for a plain-language example, glossary, audience-specific reading paths, and a safe AI-agent example. The [Demo Guide](DEMO_GUIDE.md) walks through the working app.

## Run the demo

Requirements: Python 3.12, Node.js 22.12+ (or 24+), and npm. Docker Compose can start the app with a PostgreSQL database. For a quick judge demo, use the local setup below; it does not require Docker or a cloud service.

### Local setup

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install --require-hashes -r requirements-dev.lock

cd frontend
npm ci
cd ..
```

Use a fresh temporary SQLite file and apply the reviewed schema migrations before startup; the application refuses to create or alter an unversioned schema automatically. Follow the [demo runbook](docs/audits/DRILLLOOP_DEMO_RUNBOOK.md) to create the private directory, configure a named account, and set `DATABASE_URL`. Then run `alembic upgrade head` followed by:

```bash
PYTHONPATH=backend .venv/bin/uvicorn app.main:app --host 127.0.0.1 --port 8000 --no-access-log
```

In another terminal:

```bash
cd frontend
npm run dev
```

Open <http://127.0.0.1:5173>. The API does not create a default account or seed an exercise on startup. Configure a named local user and a fresh temporary database as described in [the demo runbook](docs/audits/DRILLLOOP_DEMO_RUNBOOK.md); the fictional exercise is available from **Load fictional demo** when demo seeding is enabled. Never reuse an existing database path for a first-time run. The API is at <http://127.0.0.1:8000>, and its OpenAPI page is <http://127.0.0.1:8000/docs>.

Sign-in uses configured named users with explicit roles. There is no shared reviewer key or default password. Local password authentication is a development/demo boundary; an enterprise identity provider, secret-management service, and production session/revocation policy have not been selected.

### Docker Compose

```bash
cp .env.example .env
# Create private secret files and configure .env to point at them.
# Use only a newly created local Compose volume for this fresh-install procedure.
docker compose up --build --wait db
docker compose --profile maintenance run --build --rm migrate
docker compose up --build --wait
```

Open <http://127.0.0.1:8000>. Compose runs the API/UI on PostgreSQL and persists data in the `drillloop-postgres` volume. The Compose file has no default database password or user account. Seed data is disabled by default. Do not change the PostgreSQL volume mount on a populated volume without a verified migration plan, and do not use this local Compose configuration as a production deployment.

The migration command is explicit and can change a versioned existing database. Do not run it against any populated volume until an owner-approved adoption plan, protected backup, and disposable-copy rehearsal are complete. Existing unversioned databases are rejected by app startup and require manual baseline inspection; they are never stamped automatically.

### Tests and quality checks

```bash
.venv/bin/pytest -q
.venv/bin/ruff check backend scripts
cd frontend && npm run build
uv tool run --from pip-audit pip-audit -r requirements-prod.lock
npm audit --prefix frontend --audit-level=high
```

The versioned synthetic analysis evaluation runs with:

```bash
.venv/bin/python scripts/evaluate_analysis.py
```

It uses a new owner-marked temporary SQLite database, prints JSON to stdout, and only writes a result file if `--output` names a new path. The dataset is fictional and developer-authored, not independently reviewed; its results do not predict performance on other exercises. For a bounded loopback readiness load test, start the app against disposable data and run `.venv/bin/python scripts/load_test.py --pid <api-pid>`; the script caps work at 1,000 requests and 20 concurrent workers.

No evaluators were timed. The team has not measured staff time saved, how many drafts evaluators would correct, or the accuracy of automatic speech recognition (**ASR**, software that turns speech into text) on real audio. The current analysis path is deterministic and does not invoke an LLM. See the [Reader Guide](DRILLLOOP_READER_GUIDE.md) and [Evaluation Report](DrillLoop_Evaluation_Report.pdf) for definitions and limits.

## Generate the documents and deck

The generated deliverables are checked into the project root. To regenerate them:

```bash
.venv/bin/python scripts/generate_docs.py
npm --prefix presentation ci
npm --prefix presentation run build
soffice --headless --convert-to pdf --outdir . DrillLoop_Pitch_Deck.pptx
```

The idea PDF is exported from the editable Word document when LibreOffice is available (otherwise the script writes a ReportLab fallback). The PowerPoint is editable and contains presenter notes on every slide. LibreOffice is used here to export the slide PDF.

The Product and Commercial Review is generated independently from new text and native PowerPoint shapes. It does not read or reuse the former 14-slide template, its masters, fonts, or assets. Regenerate the editable PPTX and PDF with:

```bash
npm --prefix presentation ci
.venv/bin/python scripts/generate_business_review.py
```

The script uses the pinned Noto Sans variable font from Google Fonts under the SIL Open Font License 1.1. It downloads and SHA-256 verifies the font and license in a temporary directory for PDF rendering; it does not install the font or copy a standalone font binary into the repository. The generator source is [presentation/generate_business_review.js](presentation/generate_business_review.js). See the [asset rights register](docs/audits/DRILLLOOP_ASSET_RIGHTS_REGISTER.md) for source, digest, embedding, and remaining owner decisions.

## Demo workflow

1. Choose **Night Shift: Extended Power Loss**.
2. Review the timeline and the unresolved 09:10 / 09:11 acknowledgement discrepancy.
3. Open **Findings** and inspect each evidence link. Try the mismatched “two / too” transcript phrase; it is marked 58% confidence and is not needed for the time-discrepancy finding.
4. Approve or reject proposed findings while signed in with an account that has reviewer permission.
5. Update action owner, due date, and acceptance criteria. Approve an action only after its linked finding is approved; record closure evidence before closing it.
6. Export the editable working report as PDF.

The detailed walkthrough, reset choices, and visible error cases are in [DEMO_GUIDE.md](DEMO_GUIDE.md).

## What the app does with evidence

- Imports UTF-8 TXT/MD notes, CSV event logs, JSON event/transcript records, and selectable-text PDFs.
- Keeps the original uploaded file and records where extracted text came from: a CSV row, note line, PDF page, or transcript segment. It also stores a SHA-256 fingerprint (a checksum that helps detect whether the file later changes).
- Shows only times that appear in the evidence. A missing time stays unknown. If two people report different times, both remain visible until a reviewer resolves them.
- Uses a small set of understandable local rules to suggest candidate findings and link them to stated exercise objectives. This sample is small enough to search directly; it does not need a separate vector database or a free-running AI agent.
- Uses deterministic rules configured on each exercise; unconfigured rules or missing evidence remain unknown/needs review. The current application does not call a local or cloud LLM.
- Can optionally turn audio into a draft transcript using faster-whisper. The model must be installed locally; it is not downloaded automatically. The demo does not claim speaker identification or accuracy in languages other than English. The provided transcript is pre-generated, not an audio transcription result.

Uploaded source bytes and extracted text are stored in the configured database. Use fictional or otherwise permitted evidence in the demo. Local named-user passwords and the single-process Compose setup are not a production identity or hosting solution.

## Deliverables

- [Idea document (DOCX)](DrillLoop_Idea_Document.docx) and [PDF](DrillLoop_Idea_Document.pdf)
- [Product pitch deck (PPTX)](DrillLoop_Pitch_Deck.pptx) and [PDF](DrillLoop_Pitch_Deck.pdf) — 13 slides with speaker notes, hospital-first pilot hypothesis, and synthetic demo evidence.
- [Product and commercial review deck (PPTX)](DrillLoop_Business_Review.pptx) and [PDF](DrillLoop_Business_Review.pdf) — independently authored 12-slide review with speaker notes; external distribution remains subject to content-owner approval.
- [Business case](DrillLoop_Business_Case.pdf), [evaluation report](DrillLoop_Evaluation_Report.pdf), and [architecture SVG](DrillLoop_Architecture.svg)
- [Technical design](DrillLoop_Technical_Design.md), [demo guide](DEMO_GUIDE.md), and [plain-language Reader Guide with an AI-agent example](DRILLLOOP_READER_GUIDE.md)
- [Synthetic ground truth](demo/ground_truth.json), [evidence files](demo/evidence/), and [benchmark results](demo/benchmark_results.json)
- [Product screenshots](assets/)

## Research notes

The workflow borrows concepts from FEMA's 2020 HSEEP doctrine: define objectives, capture observations, analyze strengths and areas for improvement, and track corrective actions. California's public hospital power-loss exercise materials provide an adjacent scenario reference. Public product pages show that Veoci already markets AAR production and corrective-action follow-up; DrillLoop's evidence-to-source/reviewer/closure trace is a positioning hypothesis to test, not a validated claim of uniqueness.

References and license/version choices are recorded in [DrillLoop_Technical_Design.md](DrillLoop_Technical_Design.md).
