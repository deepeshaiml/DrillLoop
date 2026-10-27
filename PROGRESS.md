# DrillLoop Progress

Updated: 27 October 2026

## Delivery status

- [x] Inspected the empty starter workspace; created `AGENTS.md` and `EXECUTION_PLAN.md`.
- [x] Researched HSEEP workflow, public AAR examples, product positioning, and runtime/model/document library versions and licenses. References and limitations are in the technical and idea documents.
- [x] Defined the exercise/evidence schema, source locators, reviewer gates, and corrective-action lifecycle.
- [x] Created the synthetic hospital outage exercise, eight labeled log observations, five expected findings, and edge cases for missing/contradictory times, ambiguous language, and inaccurate ASR.
- [x] Built the FastAPI/SQLAlchemy API, React/TypeScript UI, SQLite demo persistence, PostgreSQL Compose path, source-preserving uploads, local fixed analysis pipeline, human review, action tracking, and PDF AAR/IP export.
- [x] Added optional staged-model faster-whisper transcription and optional local Ollama action-wording integration. Neither is required for the demo or included in the measured benchmark.
- [x] Added parser, workflow, API, citation, and status-transition tests and generated benchmark metrics.
- [x] Generated and visually checked the Word document, PDFs, editable 13-slide PowerPoint with speaker notes, architecture SVG, product screenshots, README, and demo guide.
- [x] Completed a plain-language review for first-time readers, evaluators, managers, developers, and AI agents. Added a source-cited worked example, glossary, and conceptual JSON review record; refreshed the UI labels and product screenshots.
- [x] Created a separate 14-slide Business Review from the retained template, preserving its layouts, charts, tables, typography, and slide chrome. Replaced placeholder data with sourced MVP, benchmark, scenario, target-market, decision, and roadmap content; added speaker notes and exported a PDF.
- [x] Made Business Review regeneration accept a local template path without bundling an asset whose redistribution terms are unknown; made README regeneration commands root-relative and excluded local databases, caches, and installed dependencies from Git.

## Verification log

- `ruff format backend && ruff check backend`: passed.
- `pytest -q`: **11 passed**, 1 Starlette/httpx deprecation warning.
- `npm run build` in `frontend`: passed with TypeScript and Vite production build.
- `npm run build` in `presentation`: generated the 13-slide PPTX.
- `npm run build` in `frontend`: TypeScript and Vite production build passed after the plain-language UI update; refreshed overview, findings, and action screenshots from the running demo.
- `npm audit --omit=dev` in `presentation`: 0 vulnerabilities; `image-size` is pinned to fixed 2.0.4.
- `docker compose config`: valid Compose configuration.
- API smoke check: `/api/exercises` returns the seeded fictional hospital exercise.
- Document generator passed after refreshing the screenshots; idea DOCX/PDF and business/evaluation PDFs were regenerated.
- PDF structure: idea PDF 8 pages (exported from DOCX), business case 2 pages, evaluation report 3 pages, pitch deck 13 pages.
- PPTX inspection: 13 slides and 13 speaker-notes pages, each containing narration. Pitch PDF was exported from the refreshed PPTX with LibreOffice.
- Business Review inspection: 14 editable slides and 14 meaningful speaker-notes pages; PDF export has 14 pages. Rendered the slide PDF and checked the full montage plus dense benchmark and financial slides for clipping.
- `scripts/generate_business_review.py`: generated the Business Review by cloning the retained PowerPoint template. A connected Google Slides import was unavailable because the upload returned HTTP 403; the reference remains unchanged and the local PPTX/PDF are complete.
- Visual QA: rendered the pitch PDF and document PDFs to page images; checked the deck montage, product screenshots, and Word export for layout and clipping.
- Readability review was editorial; the project has not yet run comprehension sessions with representative nontechnical users or AI agents.

## Recorded synthetic benchmark

- Observation extraction: 8/8; precision 1.00, recall 1.00, F1 1.00.
- Finding detection: 5/5; precision 1.00, recall 1.00, F1 1.00.
- Expected event-row citations: 9/9; unsupported closed-fixture rate 0/5; uncited drafts 0.
- Timeline: 8/8 explicit CSV timestamps; one contradictory time flagged; one untimed note left unplaced.
- Corrective-action checklist: 31/32 fields; 3/4 owners assigned because one is intentionally missing.
- Deterministic rule request latency: p50 4.61 ms / p95 9.13 ms across 12 local test-client requests; process RSS 78.2 MB on the test machine, without ASR or LLM models.
- Manual evaluator comparison, correction workload, time saved, ASR WER, and local LLM quality/latency: not measured.

All perfect match values above describe one closed synthetic fixture and do not estimate performance in other exercises or organizations. The test warning, model limitations, security boundary, and pilot validation plan are documented in the reports.
