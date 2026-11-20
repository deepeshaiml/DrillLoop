# Scanned PDF OCR support

Updated: 20 November 2026

## Runtime stack

DrillLoop keeps the existing `pypdf` text extractor and isolated parser worker. For a page with no selectable text, the worker renders that original page with `pypdfium2==5.15.2` and sends an in-memory PNG to Tesseract using English data and page-segmentation mode 6. If PSM 6 puts multiple timestamps on one output line, the worker retries with PSM 3 under the same four-second OCR deadline.

For a page with both native text and embedded images, the worker uses PDFium image-object bounds to identify up to eight merged visible image areas, renders only those crops from the original page, and OCRs the crops. It retains native text and suppresses only same-page lines that match after case/whitespace normalization. Repeated wording on other pages remains a separate observation. Mixed-page OCR is recorded as `native_text_plus_ocr`; OCR-added lines keep page-only citations. The uploaded PDF bytes, filename, SHA-256, and source ID remain the evidence record. No temporary OCR PDF or temporary image files replace the source.

The application environment must provide:

- Python 3.12, `pypdf==6.21.4`, and the hash-locked `pypdfium2==5.15.2` dependency.
- Tesseract 5 with the `eng` trained data. The local verification environment had Tesseract 5.5.3 and English data. The runtime image pins Debian Tesseract `5.5.0-1+b1` and English data package `1:4.1.0-2`.
- `pypdfium2` is distributed under BSD-3-Clause/Apache-2.0 terms with the bundled PDFium and third-party license notices. Tesseract is Apache-2.0; the English trained data is distributed by the Tesseract project. Existing `pypdf` remains BSD-3-Clause. Package versions and wheel hashes are in `requirements-prod.lock` and `requirements-dev.lock`.

OCRmyPDF was not installed in the inspected environment; Ghostscript and qpdf were also absent. Its `skip` mode skips a page when text is present, so it would miss additional image-only wording on a same-page mixed record. Its `redo` mode distinguishes visible and invisible text, masks visible text, and OCRs the remaining page image, which can recover bitmap wording while preserving visible text. It still rewrites the PDF and replaces/removes parts of its text layer, so using it only as an extraction intermediate would add a second PDF pipeline and dependencies. DrillLoop uses bounded PDFium image-region rendering instead, retaining the original evidence file and existing native extraction. OCRmyPDF documents these mode differences in its [advanced processing guide](https://ocrmypdf.readthedocs.io/en/stable/advanced.html).

Phase 3 adds no Python package or lockfile changes. The pinned `pypdfium2==5.15.2` release supports Python 3.6+ and is distributed under BSD-3-Clause/Apache-2.0 terms; bundled PDFium and third-party notices still apply. Tesseract is Apache-2.0. See the [pypdfium2 package metadata](https://pypi.org/project/pypdfium2/5.15.2/) and [Tesseract license](https://github.com/tesseract-ocr/tesseract/blob/main/LICENSE). The verified development runtime was Python 3.12, pypdf 6.21.4, pypdfium2 5.15.2, and Tesseract 5.5.3 with English data. The Docker image pins Tesseract 5.5.0-1+b1 and English data 1:4.1.0-2, but Docker runtime verification was unavailable because the local Docker daemon was stopped.

## Provenance and uncertainty

- Native pages keep their current `pypdf` text and `page N, line M` citation behavior.
- OCR pages store each recognized non-empty line as an observation, with a `page N` locator and `extraction_method: "ocr"`. No line number, bounding box, PDF highlight, or word-confidence value is inferred.
- OCR-derived timestamps are retained as raw source claims and marked `uncertain`. Existing elapsed-time rules exclude uncertain times, so they lead to evaluator review rather than a calculated result. Other configured deterministic rules may still produce a finding, which remains proposed and linked to the OCR page wording.
- Source provenance records per-page extraction method/status, OCR engine and renderer versions, language, resolution, page processing duration, and the unavailable line-position/confidence fields.
- The source viewer shows the page locator and provides the original PDF download. It does not navigate to or highlight a page.

## Resource and upload boundaries

OCR runs only after the configured malware scan succeeds and only inside the existing disposable parser process. Existing limits remain: 15 MiB per file, 250 PDF pages, 2,000,000 extracted characters, one active parser, eight queued jobs, parser wall timeout 15 seconds by default (configurable up to 60), 10 CPU seconds, and 768 MiB parser address-space ceiling. Additional OCR bounds are 20 pages requiring OCR, 200 DPI rendering, 12,000,000 pixels per rendered page or mixed-page crop, 64 embedded image objects inspected and eight merged image regions OCRed per mixed page, one Tesseract thread, and a four-second OCR deadline per page shared by any PSM retry or mixed-page regions. The renderer and image are held in memory; the OCR path creates no per-page temporary files. If the mixed-image region or page cap is reached, native text is retained and the source is marked partial with a page issue. Image-only PDFs exceeding the OCR-page cap fail with a controlled error. The container retains its existing 64 MiB `/tmp` and private quarantine bounds for other upload/scanner work.

If OCR is unavailable, the worker preserves selectable text and flags the affected pages as partial. Image-only files require the OCR runtime and return a controlled 503 if it is unavailable. A page that yields no readable text is flagged for review if other pages can be imported. A document with no readable observations returns a controlled error. Scanner-disabled verification uses only locally generated fictional files, as required. Existing scanner configuration and fail-closed behavior are unchanged.

## Fictional fixtures and local verification

`evals/phase2/ground_truth.json` contains developer-authored labels for selectable, scanned, mixed, rotated/degraded, and ambiguous/missing-information PDFs. The labels are written independently of application output. The fixture generator does not invoke OCR.

The 19 November 2026 fixture run is recorded in [`evals/phase2/results/ocr-quality-2026-11-19.json`](../../evals/phase2/results/ocr-quality-2026-11-19.json). It is a five-file fictional sample, not an accuracy claim for real exercise records.

| Fixture | CER / WER | Observations matched | Correct page attribution | Timestamp labels | OCR time |
| --- | ---: | ---: | ---: | ---: | ---: |
| Selectable text | 0 / 0 | 10/10 | 10/10 | 4/4 | not applicable |
| Image-only scan | 0 / 0 | 10/10 | 10/10 | 4/4; all 4 remain uncertain | 0.424 s |
| Mixed native/scanned pages | 0 / 0 | 10/10 | 10/10 | 4/4; the OCR-derived time remains uncertain | 0.217 s |
| Moderately rotated/degraded | 0 / 0 | 10/10 | 10/10 | 4/4; all 4 remain uncertain | 0.416 s |
| Ambiguous/missing information | 0 / 0 | 5/5 | 5/5 | no timestamp label expected; 3/3 unknowns stayed untimed | 0.225 s |

There were no missed or duplicate observations and no incorrect event/page assignments in these fixtures. Native pages were extracted without OCR; the mixed document used native extraction on page 1 and OCR only on page 2. The scanned two-page file took 0.979 seconds in the isolated worker, including process setup; its OCR subprocess time was 0.424 seconds. Across all isolated parser children in the evaluation run, measured peak RSS was 175,816,704 bytes and aggregate CPU was 4.911 user seconds plus 1.112 system seconds. These figures describe only this local run.

The disposable application workflow preserved the uploaded PDF bytes and SHA-256, created 10 timeline observations, retained OCR timestamps as uncertain, left elapsed-time analysis at `insufficient_information`, and produced the existing deterministic `STATION_B_RESTORED` finding as proposed with reviewer decision `null` and citation `utility_emergency_log_scanned.pdf · page 2`. The existing PDF report export included the finding and page citation. Repeating the same explicit upload creates a second source record; duplicate-file deduplication is not implemented.

Automated browser runs also passed. The OCR-specific walkthrough verified the upload status, source details and page locator, timeline, objective evaluation, proposed finding, citation review, and `OCR-PHASE2-DEMO-AAR-IP.pdf` download. Its screenshots were reviewed locally and are excluded from the PR as reproducible UI artifacts. The existing `frontend/e2e/live-workflow.mjs` regression passed on a separate disposable database, including review, corrective-action closure, PDF export, and responsive-layout checks.

## Phase 3 robustness and mixed-page results

The Phase 3 developer-authored labels were initially written from the intended fictional source content before OCR and were not independently adjudicated. After an initial extraction run, a source-driven audit corrected the “unknown time” category: explicit `15:17` is timed; the no-time row and ambiguous `15:2?` row are unknown. This correction uses the printed source content, not OCR output. The final paired report is [`phase3-final-reviewed-2026-11-20.json`](../../evals/phase3/results/phase3-final-reviewed-2026-11-20.json); PDFs and labels are under `evals/phase3/`. The comparison re-runs the Phase 2 extraction policy and Phase 3 policy against the same five PDFs and audited labels; it is not a production accuracy claim.

| Fixture | CER Phase 2 → 3 | WER Phase 2 → 3 | Observations Phase 2 → 3 | Exact timestamp text Phase 2 → 3 |
| --- | ---: | ---: | ---: | ---: |
| Same-page native text + embedded image | 13.71% → 0% | 14.58% → 0% | 7/8 → 8/8 | 4/5 → 5/5 |
| Two-column, 200-DPI low-resolution, blurred, 1.15° skew | 63.28% → 2.86% | 73.85% → 6.15% | 6/10 → 10/10 | 1/6 → 6/6 |
| Two-page scanned event table | 0.39% → 0.39% | 2.50% → 2.50% | 12/12 → 12/12 | 4/4 → 4/4 |
| Native dispatch memo with conflicting claims | 0% → 0% | 0% → 0% | 5/5 → 5/5 | 2/2 → 2/2 |
| Intentionally unreadable field note | unavailable → unavailable | unavailable → unavailable | unavailable → unavailable | unavailable → unavailable |

Across the four recognition-scored documents, CER fell from 293/1,465 (20.00%) to 13/1,465 (0.89%), and WER from 57/224 (25.45%) to 6/224 (2.68%). Observation precision/recall changed from 30/30 and 30/35 (100%/85.71%) to 35/35 and 35/35 (100%/100%). Exact timestamp text recognition changed from 11/17 (64.71%) to 17/17 (100%); OCR-derived times still carry `uncertain` provenance and are not verified event times. Page-method attribution changed from 5/6 to 6/6. Required citation recall changed from 0/1 to 1/1. Both policies produced zero duplicate observations and zero unsupported observations. The unreadable page returned controlled `EMPTY_PDF` in Phase 3 rather than accepting a page marker as readable evidence.

In the same-page mixed fixture, the worker OCRed one embedded image region, suppressed one exact native/image overlap, retained the repeated event on page 2, and recovered all 8 expected observations with correct pages. The two-column fixture triggered the PSM 3 retry after PSM 6 put multiple timestamps on a line. In the table fixture, both intentionally ambiguous/missing-time lines were preserved without assigning an event time (2/2); repeated `15:17` wording remained cited to its own source page. A separate dispatch memo carries conflicting time claims, but the conflict was not jointly evaluated with the table source, so cross-document conflict handling is not measured here. A separate PDF containing only native versus scanned copies of the identical full document was not available; paired native-vs-scanned CER/WER is unavailable.

Phase 3 isolated-worker wall time was 0.696 s for the same-page fixture, 1.305 s for the two-column scan, 1.308 s for the table scan, 0.482 s for the native memo, and 0.686 s for the unreadable scan. These values include parser startup. The evaluator's Phase 2 policy replay uses an in-process baseline, so its latency values are not directly comparable. Across this Phase 3 run, child CPU totaled 4.606 user + 0.905 system seconds; maximum per-child high-water RSS was 213,057,536 bytes (~203 MiB), not a sum across workers. The earlier Phase 2 run reported 175,816,704 bytes maximum child RSS and 4.911 user + 1.112 system CPU seconds. These are separate runs over different files, not a paired capacity test; the Phase 3 maximum child RSS was higher and still below the existing 768 MiB parser ceiling. The OCR-specific CPU and RSS limits remain unchanged.

The browser demonstration and full existing Playwright regression passed on disposable databases. The demonstration verified upload and OCR status, native and image wording on page 1, exact overlap suppression, page citations in the original source, timeline, objective analysis, a proposed citation-backed finding with reviewer decision still pending, and PDF export. The screenshots were reviewed locally and are excluded from the PR as reproducible UI artifacts. The viewer links to the original PDF and page locator; in-app page navigation and highlighting are not implemented. The same-source duplicate-upload check confirms two explicit uploads create separate source records; duplicate-file deduplication is not implemented.

Re-run the focused comparison with:

```sh
.venv/bin/python scripts/evaluate_ocr.py \
  --labels evals/phase3/ground_truth.json \
  --skip-application-workflow \
  --compare-phase2-baseline \
  --verify-duplicate-upload \
  --output evals/phase3/results/phase3-final-reviewed-2026-11-20.json
```

For the visual demo, start the local disposable API and frontend in separate terminals:

```sh
.venv/bin/python scripts/serve_phase3_ocr_demo.py --port 8000
```

```sh
cd frontend
npm run dev -- --host 127.0.0.1
```

Sign in at `http://127.0.0.1:5173` using `evaluation-admin` / `synthetic-evaluation-only-password`, choose `OCR-PHASE3-DEMO`, and upload `evals/phase3/sources/phase3_same_page_mixed_water_log.pdf`. The server prepares the fictional exercise in a disposable SQLite database and enables scanner-disabled mode only for this local synthetic demo. Do not use this demo server for arbitrary uploads.

The Playwright walkthrough uses the same disposable demo account and running services:

```sh
cd frontend
DRILLLOOP_E2E_BASE_URL=http://127.0.0.1:5173 \
DRILLLOOP_E2E_USERNAME=evaluation-admin \
DRILLLOOP_E2E_PASSWORD=synthetic-evaluation-only-password \
node e2e/phase3-ocr-workflow.mjs
```

```sh
tesseract --version
tesseract --list-langs
.venv/bin/python scripts/evaluate_ocr.py
```

The Phase 2 fixture PDFs and labels are included in the repository. The generator refuses to overwrite a non-empty fixture directory or existing labels; use it only when the fixture outputs are absent.

The evaluator uses an owner-marked disposable SQLite database and deletes it on exit. To save a new result, pass a new, unused path to `--output`; existing result files are refused.

To demonstrate the application workflow locally, start these in separate terminals from the repository root:

```sh
.venv/bin/python scripts/serve_ocr_demo.py --port 8000
```

```sh
cd frontend
npm run dev -- --host 127.0.0.1
```

Open `http://127.0.0.1:5173`, sign in with `evaluation-admin` / `synthetic-evaluation-only-password`, select the prepared `OCR-PHASE2-DEMO` exercise, and upload `evals/phase2/sources/utility_emergency_log_scanned.pdf`. The demo server uses an owner-marked disposable SQLite database and scanner-disabled status for these generated fixtures only. Stop both local processes when finished; no application database or arbitrary upload scanner setting is changed.

The OCR browser walkthrough can be repeated from the `frontend` directory while both local processes are running:

```sh
DRILLLOOP_E2E_BASE_URL=http://127.0.0.1:5173 \
DRILLLOOP_E2E_USERNAME=evaluation-admin \
DRILLLOOP_E2E_PASSWORD=synthetic-evaluation-only-password \
node e2e/ocr-workflow.mjs
```

It writes screenshots under `evals/phase2/results/`. Do not use a production upload scanner bypass for arbitrary files.

## Known limits

- English printed text only; handwriting and multilingual OCR are not claimed. One synthetic printed table was measured, but general table structure recovery is not claimed.
- OCR quality is not calibrated; no OCR confidence score is exposed. A reviewer must compare OCR wording and timestamps with the original page.
- Same-page OCR scans PDF image objects only. Image content encoded as vector paths, hidden, clipped, outside detected object bounds, or omitted by object/region limits can remain unextracted; capped mixed pages are marked partial. Duplicate suppression is exact after case/whitespace normalization and does not merge similar wording.
- A 1.15° skew and low-resolution/blurred two-column scan were measured. Arbitrary page rotation, deskew correction, handwriting recovery, and image enhancement are not claimed. Severe skew/degradation may time out or produce incorrect wording that requires human review.
- Inline timestamp parsing for text files is a separate existing limitation and was not changed in this phase.
- Page locators are available, but in-app page navigation and PDF highlighting are not.
- Synthetic fixture results are not production accuracy or generalization evidence.

## Stack references

- [pypdfium2 5.15.2 package metadata and license](https://pypi.org/project/pypdfium2/5.15.2/)
- [Tesseract OCR license](https://github.com/tesseract-ocr/tesseract/blob/main/LICENSE)
- [Debian Trixie Tesseract package](https://packages.debian.org/trixie/amd64/tesseract-ocr)
- [Debian Trixie English trained data](https://packages.debian.org/trixie/all/tesseract-ocr-eng)
- [OCRmyPDF skip and redo behavior](https://ocrmypdf.readthedocs.io/en/stable/advanced.html)
