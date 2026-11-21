# DrillLoop Eureka V2 demo guide

**EUR-26-014 · Public Safety Intelligence · TRL 4, self-assessed.** Hospital preparedness teams use DrillLoop to connect exercise records to a timeline, draft findings, human decisions, and corrective actions. The live demonstration uses one fictional hospital exercise, **Night Shift: Extended Power Loss**. The public-document evaluation is the final speaking point.

## Launch and sign in

From the real-evidence worktree, install once and build the frontend. The rehearsal used Python 3.12.13, Node 26.9.0, Playwright 1.64.1 with Chromium, and Tesseract 5.5.3 with English data. Hosted CI uses Node 24. Ollama and LibreOffice are optional for the fictional demo. Tesseract supports the scan step. LibreOffice is used for the separate public Office source conversion.

```sh
python3.12 -m venv .venv
.venv/bin/python -m pip install --require-hashes -r requirements-dev.lock
npm --prefix frontend ci
npm --prefix frontend run build
npm --prefix frontend exec -- playwright install chromium
tesseract --list-langs
.venv/bin/python scripts/serve_eureka_demo.py --controlled
```

Open **http://127.0.0.1:8765**. Uvicorn serves the API and production React build. The launcher prints the private run folder and credentials file after readiness. Sign in as `eureka-operator`. Open a separate browser profile or private window for `eureka-reviewer` so the two sessions use different cookies. Use the named account passwords from the printed, owner-readable `credentials.json`. New passwords are generated each run. Open the credentials off screen.

`--controlled` enables a scripted provider for the fictional pharmacy note. Introduce it as a **scripted test response** before clicking Generate. For optional real inference, run a separate `OLLAMA_HOST=127.0.0.1:11479 OLLAMA_NO_CLOUD=1 ollama serve` instance with a compatible installed model. Start the demo with `--model qwen3.6:35b-a3b-coding-nvfp4` in place of `--controlled`. The demo runs with AI disabled when both flags are omitted.

Use **Ctrl+C** for shutdown. A new launch allocates a fresh owned SQLite file. The previous run stays available. To recover it with AI disabled, use `.venv/bin/python scripts/serve_eureka_demo.py --resume <printed-run-name>`. If 8765 is occupied, use `--port 0` and open the printed URL.

## 9½-minute run of show

| Time | Screen and action | Say and verify | If the step fails |
| --- | --- | --- | --- |
| 0:00–0:50 | Exercises → **Load fictional demo** → overview | Exercise records arrive as logs, notes, and PDFs. Reviewers need a traceable account of what happened and what follow-up was decided. Verify the fictional banner. | Capture 01 |
| 0:50–1:35 | **Objectives** → OBJ-01. Use **Manage access** to grant the named reviewer. | Essential circuits have a 60-second exercise target. A named reviewer will act in a separate session. | Capture 02 |
| 1:35–2:35 | **Evidence** → select `fictional_pharmacy_scan.pdf` and `fictional_pharmacy_handoff.txt` from the run folder → **Upload 2 files**. Open the PDF source card. | The scan is fictional. Inspect OCR wording, page 1 and uncertain time. The text handoff is a separate source. | Capture 03 and a preloaded CSV source |
| 2:35–3:25 | **Timeline** → open the 09:02 and 09:06 log sources, then **Conflicting or unresolved times** | The log clocks give four minutes for restoration. An acknowledgement disagreement stays unresolved. | Capture 04 |
| 3:25–4:15 | **Findings** → essential power proposal | The rule compares four minutes with 60 seconds. Check the source citations and leave cause unknown. | Capture 05 |
| 4:15–5:25 | **Findings → AI assistance → Generate AI suggestions** → inspect OBJ-03 quotation → **Save for review** | The scripted provider cites the signed pharmacy form. Saving creates a candidate. | Capture 06 or open the saved candidate in a resumed run |
| 5:25–6:40 | Reviewer profile → **Findings → Open candidate for OBJ-03 → Accept for consideration → Confirm decision → Create proposed finding** | Read line 1. Title “Fictional pharmacy temperature check is documented.” Copy the source wording into **Evidence-based observation**. Say in **Interpretation** that the form documents the check and the event time remains unknown. Choose **Strength**, confirm the wording, and submit. | Captures 07 and 08 |
| 6:40–7:20 | **Open finding → Approve finding**. Open the separate essential-power finding and approve it after inspecting its citations. | The pharmacy proposal receives its first official review decision. The power finding has its own decision and action. | Capture 09 |
| 7:20–8:15 | Operator → **Corrective actions** → essential-power action → **Edit action details → Save action → Approve action** | Assign Fictional Facilities Operations, due 15 Jan 2027, and a retest criterion of 60 seconds. **Record closure evidence** with “Fictional retest DEMO-PO-01 recorded essential circuits restored in 54 seconds.” Confirm as the reviewer-capable operator. | Captures 10 and 11 |
| 8:15–8:55 | **Reports → Download report & improvement plan (PDF)**. Point to the review history. | The draft brings current decisions, source references, and closure evidence together. | Verified local PDF or capture 12 |
| 8:55–9:30 | Evaluation summary and pilot ask | Five prepared PDFs were processed. All 20 labeled passages landed on expected pages. Four clock labels stayed classified as planned. Ask for two or three reviewers and one permitted dataset. | Evaluation table and speaking notes |

The two pharmacy files are generated fixtures for the existing fictional exercise. In the public browser run, select **Planning document or template** for the LA County sources and **Published evaluation** for the Northwest report. These classifications retain wording and locators while excluding reference records from performance rules and AI performance suggestions. Existing imports require reviewer judgment about source purpose.

## Rehearsal and backup

```sh
.venv/bin/python scripts/serve_eureka_demo.py --verify fictional
.venv/bin/python scripts/serve_eureka_demo.py --port 0 --verify public --model qwen3.6:35b-a3b-coding-nvfp4
```

Both commands create fresh databases. Optional `--axe-script /absolute/path/to/axe.min.js` runs focused accessibility checks. Browser captures, Playwright recordings, and PDFs go in `.eureka-private/artifacts/<printed-run-name>/`. Open the numbered captures in order and narrate the matching table rows. Captures 07–09 show the authority boundary. Capture 13 shows the candidate history after the AI-disabled restart.

| Failure | Fallback |
| --- | --- |
| Ollama offline or interpretation incorrect | Continue with deterministic findings. Open the previously saved controlled candidate in a resumed fictional run. Leave weak model suggestions unapproved. |
| OCR unavailable or poor | Open the original fictional scan and preverified OCR screenshot. Move to the selectable CSV for the timing finding. |
| Public URL or network unavailable | Run offline from the built app using local artifacts and the registered evaluation results. |
| Browser crash or API restart | Reopen the URL. If the API stopped, resume the printed run with AI disabled and sign in again. |
| PDF download fails | Use Reports → **Retry download**, then open the rehearsed PDF if necessary. |

**Architecture.** React and TypeScript render the evaluator workflow. FastAPI validates uploads and decision requests. The isolated parser uses pypdf for native text and pypdfium2 plus Tesseract for OCR. SQLAlchemy and Alembic persist source bytes, locators, scoped access, candidates, reviewer history, findings and actions in SQLite or PostgreSQL. Optional Ollama assistance runs on loopback. ReportLab builds the draft PDF from current records.

[Evaluation results](../../evals/real-evidence/EVALUATION_REPORT.md) · [Readiness](EUREKA_FINAL_READINESS.md) · [Pitch](EUREKA_PITCH_SCRIPT.md)
