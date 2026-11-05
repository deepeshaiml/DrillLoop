# DrillLoop Progress

Updated: 4 November 2026

## Delivery status

- [x] Inspected the empty starter workspace; created `AGENTS.md` and `EXECUTION_PLAN.md`.
- [x] Researched HSEEP workflow, public AAR examples, product positioning, and runtime/model/document library versions and licenses. References and limitations are in the technical and idea documents.
- [x] Defined the exercise/evidence schema, source locators, reviewer gates, and corrective-action lifecycle.
- [x] Created the synthetic hospital outage exercise, eight labeled log observations, five expected findings, and edge cases for missing/contradictory times, ambiguous language, and inaccurate ASR.
- [x] Built the FastAPI/SQLAlchemy API, React/TypeScript UI, SQLite demo persistence, PostgreSQL Compose path, source-preserving uploads, local fixed analysis pipeline, human review, action tracking, and PDF AAR/IP export.
- [x] Added optional staged-model faster-whisper transcription. The earlier optional Ollama action-wording integration was removed from the active analysis path during remediation; current analysis is deterministic and does not invoke an LLM.
- [x] Added parser, workflow, API, citation, and status-transition tests and generated benchmark metrics.
- [x] Generated and visually checked the Word document, PDFs, editable 13-slide PowerPoint with speaker notes, architecture SVG, product screenshots, README, and demo guide.
- [x] Completed a plain-language review for first-time readers, evaluators, managers, developers, and AI agents. Added a source-cited worked example, glossary, and conceptual JSON review record; refreshed the UI labels and product screenshots.
- [x] Created a separate 14-slide Business Review from the retained template, preserving its layouts, charts, tables, typography, and slide chrome. Replaced placeholder data with sourced MVP, benchmark, scenario, target-market, decision, and roadmap content; added speaker notes and exported a PDF.
- [x] Made Business Review regeneration accept a local template path without bundling an asset whose redistribution terms are unknown; made README regeneration commands root-relative and excluded local databases, caches, and installed dependencies from Git.

## Phase 6 — release candidate review (4 November 2026)

- [x] Reviewed the complete accumulated worktree, classified every changed/untracked path, prepared the inclusion/exclusion manifest, and documented the proposed one-PR review unit. Eight superseded audit snapshots and the obsolete migrations `.gitkeep` are excluded from the PR; no file was deleted.
- [x] Reviewed app, migration, deployment, dependency, and CI configuration. Corrected `.env.*` ignore coverage, switched development setup paths to the hashed lock, pinned three GitHub-maintained Actions to tag-verified commit SHAs, corrected the pypdf design version, aligned the TLS Nginx upstream with the Compose `app` service, and made staging/production reject both demo-seed flags. The scanner-enabled rehearsal now uses the checked-in upstream directly.
- [x] Final `env -u DATABASE_URL .venv/bin/pytest -q`: **86 passed, 1 skipped**, with one Starlette/httpx deprecation warning. `.venv/bin/python scripts/rehearse_clamav_integration.py`: **1 passed** against the pinned actual ClamAV image; owned container and signature volume cleanup passed.
- [x] Ruff check/format passed (40 files); frontend TypeScript/Vite production build passed; npm audit reported 0 vulnerabilities; pip-audit reported no known vulnerabilities. A hash-required dry-run through `requirements.txt` passed.
- [x] Fresh SQLite Alembic `upgrade head` and `check` passed in a unique marked temp directory. Four captured PostgreSQL 18.6 + HTTPS/Nginx + ClamAV rehearsals passed the browser/security/recovery workflows and completed **80/80** synthetic load workflows each. In order, safe parser-capacity 503 retries were 1/0/1/0 and edge 429 retries were 180/181/173/185; every retained result had zero unexpected 5xx. The latest run had no browser errors and restored 84/84 exercise rows to a new DB. One intervening invocation's output was truncated and is unverified. Previous-image rollback was not run.
- [x] Release-execution revalidation: backend **86 passed, 1 skipped**; separate ClamAV integration **1 passed**; Ruff/format, frontend TypeScript/build, npm audit (0 vulnerabilities), pip-audit (no known vulnerabilities), hash-required install dry run, Compose config, Actionlint, and fresh SQLite migrations passed. Candidate Gitleaks scanned all 90 changed paths with zero findings. Existing SQLite fingerprints were unchanged. Two company-specific references in the included doc generator are flagged for content-owner review before public publication.
- [x] Compose configuration, Actionlint, local security configuration checks, and `git diff --check` passed. Candidate-only Gitleaks 8.30.1 scanned all 90 modified/untracked paths with zero findings; ignored local databases and caches were excluded.
- [x] Read-only GitHub API checks confirmed public `deepeshaiml/DrillLoop`, default branch `main`, zero hosted workflows, no `main` branch protection/rulesets, read-only default workflow token, first-time fork workflow approval, secret scanning and push protection enabled, non-provider pattern scanning disabled, and Dependabot security updates disabled.
- [x] Local DB fingerprints matched the pre-review values; test databases and rehearsal volumes were isolated. No commit, branch, push, PR, release, repository setting change, or deployment occurred. Approved staging and production remain NOT READY.

See [DRILLLOOP_PHASE6_RELEASE_REVIEW.md](docs/audits/DRILLLOOP_PHASE6_RELEASE_REVIEW.md), [DRILLLOOP_RELEASE_FILE_MANIFEST.md](docs/audits/DRILLLOOP_RELEASE_FILE_MANIFEST.md), [DRILLLOOP_GITHUB_PR_PREPARATION.md](docs/audits/DRILLLOOP_GITHUB_PR_PREPARATION.md), and [DRILLLOOP_STAGING_HANDOFF.md](docs/audits/DRILLLOOP_STAGING_HANDOFF.md) for release scope, owner decisions, and handoff steps.

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

## Product review alignment (27 Oct 2026; program references generalized for publication)

- [x] Updated the submission draft and public-facing descriptions to use the public-safety sector as the proposed first use case: hospital-preparedness evaluators reviewing a tabletop exercise. Program-specific labels are generalized in this publication copy.
- [x] Made the report preparer, candidate approver, and unknown budget owner explicit; kept interview results, partner interest, procurement path, time savings, and price unclaimed.
- [x] Added a proposed discovery and paired-review plan, including current-practice comparison, evaluator-labeled unfamiliar exercise, partner-defined success thresholds, and security/data-handling questions.
- [x] Refreshed the idea document, technical design, business case, evaluation report, and README. Regenerated the idea DOCX/PDF, business case PDF, and evaluation report PDF.
- [x] Updated the dedicated product pitch and the separate 14-slide Product and Commercial Review to match the hospital-first discovery plan; removed the implied fixed 90-day/multi-segment pilot commitment and unsupported numerical price/cost scenarios. Commercial models remain qualitative hypotheses to validate.
- [x] Exported the refreshed pitch and Business Review PDFs; checked PDF page counts and the PowerPoint slide/note counts. Visually reviewed the idea cover and worked example, key pitch pages, and changed Business Review slides.
- [x] Kept app behavior and synthetic benchmark results unchanged. This update does not add customer validation, a new exercise benchmark, a security assessment, or application code changes; application tests were not rerun.

## Recorded synthetic benchmark

- Observation extraction: 8/8; precision 1.00, recall 1.00, F1 1.00.
- Finding detection: 5/5; precision 1.00, recall 1.00, F1 1.00.
- Expected event-row citations: 9/9; unsupported closed-fixture rate 0/5; uncited drafts 0.
- Timeline: 8/8 explicit CSV timestamps; one contradictory time flagged; one untimed note left unplaced.
- Corrective-action checklist: 31/32 fields; 3/4 owners assigned because one is intentionally missing.
- Deterministic rule request latency: p50 4.61 ms / p95 9.13 ms across 12 local test-client requests; process RSS 78.2 MB on the test machine, without ASR or LLM models.
- Manual evaluator comparison, correction workload, time saved, ASR WER, and local LLM quality/latency: not measured.

All perfect match values above describe one closed synthetic fixture and do not estimate performance in other exercises or organizations. The test warning, model limitations, security boundary, and pilot validation plan are documented in the reports.

## Independent readiness audit (3 November 2026)

The original audit's detailed snapshots are historical and excluded from the Phase 6 pull request as superseded. Current release status and evidence are in [DRILLLOOP_PHASE6_RELEASE_REVIEW.md](docs/audits/DRILLLOOP_PHASE6_RELEASE_REVIEW.md) and [DRILLLOOP_GO_LIVE_GATE.md](docs/audits/DRILLLOOP_GO_LIVE_GATE.md).

- `.venv/bin/pytest -q`: 11 passed, 1 Starlette/httpx deprecation warning. Audit-side data-handling incident: backend/tests/conftest.py drops all tables in the pre-existing fixed `.pytest-drillloop.db` before/after the run. Its prior contents were reset and are not recoverable from this audit. The normal `drillloop.db` was not used. Isolate the fixture before future runs.
- `.venv/bin/ruff check backend`: passed.
- `npm run build` in frontend: TypeScript and Vite build passed on Node 26.9.0/npm 11.19.1.
- `docker compose config --quiet`: passed syntax/interpolation validation only.
- `npm audit --audit-level=high` in frontend: 0 vulnerabilities.
- `uv tool run --from pip-audit pip-audit -r requirements.txt -r requirements-asr.txt`: reported 9 findings across pypdf 6.21.2 and python-multipart 0.0.30; pypdf advisories include high severity findings and patched releases through 6.21.4.
- Fixture benchmark ran from a temporary copy: 8/8 observations, 5/5 findings, 9/9 event-row citations, 8/8 timestamps, one conflict and one missing time retained; p50 2.98 ms / p95 3.63 ms. This remains a single synthetic fixture result.
- Playwright browser run against temporary SQLite completed finding approval, corrective-action approval/closure, and PDF download. A separate browser upload through the UI imported the fixture CSV and displayed eight observations/five drafts.
- An unfamiliar fictional exercise with a five-minute objective and evidence at 14:00/14:04 produced a false 60-second failure, hard-coded 09:02/09:06 wording, an unsupported owner, and an unsupported due date.
- Invalid CSV time `99:99` returned HTTP 500.
- Default isolated Compose startup built the app image but PostgreSQL 18.6 failed health checks because the volume path is incompatible. A temporary Compose copy using `/var/lib/postgresql` started and retained a test record across app-container restart. No application source/config was changed; both temporary Compose projects were stopped and their disposable volumes removed.
- Optional Ollama and faster-whisper were not configured. Real integrations, load tests, backup/restore, production deployment, and representative-user testing were not run.
- This audit changed no application code. Only requested Markdown audit reports and this verification log were added/updated.

## Remediation and end-to-end verification (3 November 2026)

The independent audit section above is a historical record, including its database-fixture incident and pre-remediation results. The current review and remaining decisions are in [DRILLLOOP_PHASE6_RELEASE_REVIEW.md](docs/audits/DRILLLOOP_PHASE6_RELEASE_REVIEW.md), [DRILLLOOP_GO_LIVE_GATE.md](docs/audits/DRILLLOOP_GO_LIVE_GATE.md), and [DRILLLOOP_OWNER_DECISIONS.md](docs/audits/DRILLLOOP_OWNER_DECISIONS.md).

- [x] Made pytest storage isolated before running the suite: `backend/tests/conftest.py` rejects an inherited `DATABASE_URL`, creates a 0700 owner-marked temporary directory and a unique SQLite file per test, and never drops or removes an existing database. `backend/app/db.py` rejects unsafe test URLs and application database names. Added database safety regression tests.
- [x] Updated pypdf to 6.21.4 and python-multipart to 0.0.31; `pip-audit` and production `npm audit` reported zero known vulnerabilities at verification time.
- [x] Added upload type/size/shape checks and controlled parser errors. Invalid CSV timestamp `99:99` now returns structured HTTP 400 `INVALID_TIMESTAMP`; extraction limits cover files, batches, rows/segments, PDF pages, and extracted text.
- [x] Corrected the PostgreSQL 18 data mount and added database-backed readiness checks. An isolated temporary Compose project started, authenticated, uploaded and analyzed evidence, and retained data across an app-container restart.
- [x] Replaced fixture-specific generic analysis with deterministic objective-configured rules for elapsed time, reported duration, event presence, and required fields. Tests cover thresholds, boundary conditions, missing/conflicting/out-of-order records, source citations, unknown owner/due dates, and exercise isolation.
- [x] Added exercise creation, selection/resume, objective editing before analysis, evidence association, exercise-scoped review/action/report flows, and stale-objective protection after analysis starts.
- [x] Replaced the shared reviewer key with named configured local identities, server-side roles, signed sessions, CSRF checks, organization/exercise grants, and server-derived reviewer attribution. An enterprise identity provider remains unselected.
- [x] Added a Playwright browser regression covering the fictional seed and unfamiliar fictional evidence through upload, analysis, citations, human review, action closure, PDF export, refresh, and exercise switching.
- [x] Updated the demo runbook, production checklist, current backlog, and technical design. Production and actual external-integration readiness remain blocked; no external service or real/confidential exercise evidence was used.

### Remediation verification actually run

- `.venv/bin/pytest -q`: **44 passed**, one Starlette/httpx deprecation warning. The fixture used a unique per-test SQLite file under an owner-marked temporary directory.
- `.venv/bin/ruff check backend`: passed.
- `npm run build` in `frontend`: TypeScript and Vite production build passed.
- `uv tool run --from pip-audit pip-audit -r requirements.txt -r requirements-asr.txt`: no known vulnerabilities found.
- `npm audit --omit=dev` in `frontend`: 0 vulnerabilities.
- From `frontend/`, `DRILLLOOP_E2E_USERNAME='demo-admin' DRILLLOOP_E2E_PASSWORD='browser-test-password-2026' node e2e/live-workflow.mjs`: passed against fresh temporary SQLite; browser page errors were empty. The run covered fictional seeded and newly authored synthetic evidence.
- Isolated PostgreSQL 18 Compose verification: `docker compose up --build --wait --detach` against a uniquely named temporary project and temporary database mount; app readiness, named-user login, exercise creation, evidence upload, analysis, review/action/report flow, app restart, and persisted reads passed. The isolated project was stopped without `-v`.
- SHA-256 fingerprints after remediation test runs: `.pytest-drillloop.db` `47b85ccc2a44283b0c4ba2c992a92e3d8890226efa774ce2fd517a3c1216cd50`; `drillloop.db` `d08aed1139319a01009c468bae5c651cec27ba318b31a5d76870f93cbc719417`.

The passing browser scenario uses fictional evidence and does not constitute independent domain validation. External connectors, optional ASR model execution, accessibility review, load tests, production identity, migrations, backup/restore, deployment, and rollback remain unverified or blocked; see the implementation progress report and production checklist.


## Phase 3 production engineering (3 November 2026)

- [x] Added Alembic revisions and startup schema gates; no automatic DDL or stamping. Fresh SQLite/PostgreSQL initialization and a populated disposable upgrade preserve tested records.
- [x] Added SQLite/PostgreSQL backup and restore tooling. An isolated PostgreSQL 18 archive was restored into a new database; row snapshots, audit/review/action/grant records, source byte hashes, and migration head matched.
- [x] Added bounded request/file ingestion, isolated parser worker limits/timeouts, cleanup, safe errors, and a required fail-closed scanner boundary. No scanner is bundled; production uploads remain unavailable until one is operated.
- [x] Added local exercise-access UI and audit events; authentication remains a controlled-demo mechanism pending identity-provider and lifecycle decisions.
- [x] Added structured logs, request IDs, health/readiness, protected metrics, and upload/analysis/request measurements. Platform alerting and dashboard integration remain operational tasks.
- [x] Added least-privilege CI workflow, hash-locked Python dependencies, pinned container images, and hardened Compose foundation. CI YAML and local-equivalent checks pass; a hosted workflow run has not occurred.
- [x] Added fictional versioned analysis evaluation and bounded load tools. Synthetic evaluation had 5/5 expected findings and 8/9 labeled canonical citations; results are not independent accuracy evidence. The 500-request loopback readiness test passed at concurrency 20; it is not an application capacity claim.
- [x] Completed isolated browser workflow, PostgreSQL migration/restart/recovery, SQLite recovery tests, and application health checks.

### Phase 3 verification actually run

- .venv/bin/ruff check backend scripts — passed.
- env -u DATABASE_URL .venv/bin/pytest -q — 67 passed; one Starlette/httpx deprecation warning.
- npm --prefix frontend run build — passed.
- npm --prefix frontend audit --audit-level=high — 0 known vulnerabilities.
- uv tool run --from pip-audit pip-audit -r requirements-prod.lock — no known vulnerabilities found.
- docker compose config --quiet with explicit disposable test values — passed; Nginx local ingress configuration test passed.
- scripts/rehearse_postgres.py — isolated PostgreSQL 18 migration, browser workflow, restart persistence, backup, restore-to-new-target, record/hash checks, and cleanup passed.
- scripts/rehearse_load_test.py — 500 HTTP 200 readiness requests, 0 failures, 1,802.79 requests/second, p50 10.27 ms, p95 13.01 ms, max 35.43 ms, sampled API RSS 123.7 MiB initial / 125.2 MiB peak.
- scripts/evaluate_analysis.py and repeat with --baseline-result — evaluation and zero metric-count regression comparison completed on the same fictional dataset.
- .pytest-drillloop.db and drillloop.db fingerprints remained at previously recorded SHA-256 values.

Production remains NOT READY. Staging infrastructure/TLS/secrets, approved malware scanning, identity choice, classification and retention policy, recovery objectives, independent permitted evidence evaluation, integration scope, capacity/availability requirements, hosted CI, monitoring/response owners, and security/accessibility reviews remain. See [DRILLLOOP_PHASE6_RELEASE_REVIEW.md](docs/audits/DRILLLOOP_PHASE6_RELEASE_REVIEW.md), [DRILLLOOP_GO_LIVE_GATE.md](docs/audits/DRILLLOOP_GO_LIVE_GATE.md), and [DRILLLOOP_STAGING_HANDOFF.md](docs/audits/DRILLLOOP_STAGING_HANDOFF.md).

## Phase 5 — scanner integration, bounded concurrency and release candidate (4 November 2026)

Phase 5 was performed on the already dirty Phase 3/4 worktree. Existing local databases, ignored files, Docker data and application data were preserved. No commit, push, PR, hosted CI run, approved staging deployment or production deployment occurred.

- Added an optional Docker Compose `scanner` profile using the digest-pinned official ClamAV Debian 1.5.4 image. The scanner has no host port binding, a persistent signature volume, controlled FreshClam updates, 2 CPU/5 GiB limits, and a dedicated outbound network. Required-mode app readiness checks `PING`, signature timestamp freshness, a clean scan and EICAR detection. The local 72-hour signature-age threshold and four daily update checks are proposed values, not approved organizational policy.
- Replaced immediate single-slot rejection with FIFO bounded parser admission: one isolated worker, eight waiters, a 30-second default queue wait and retryable 503 when full or timed out. Added cancellation/child cleanup, upload-batch atomicity, scanner provenance/audit data, and active/waiting/peak/rejection/queue/processing/scan metrics. The frontend displays the retry guidance from the API.
- Updated ingress throttling to return structured 429 with `Retry-After: 2` while retaining the configured request-rate limit and security headers. The bounded load driver retries only those pre-forwarding 429s and parser-capacity 503s that cannot have persisted records.
- `.venv/bin/python scripts/rehearse_staging.py`: **PASS** on a unique PostgreSQL 18.6 + HTTPS/Nginx + ClamAV local project. Browser login/create/objectives/upload/scan/extract/analyze/citations/review/action/PDF/refresh/resume, access grant/revoke, cross-user denial, migration checks, health, scanner timeout/outage/restart, app/database restart and backup/restore to a new DB all passed. Restored exercise count was 84/84; no scanner port was published.
- Actual ClamAV synthetic cases: clean CSV/PDF accepted; EICAR rejected with no imported source; invalid timestamp rejected; scanner timeout/unavailable failed closed; accepted/rejected decisions were audited; quarantine was empty afterward. Local scanner image and policy are not organizationally approved.
- Bounded Postgres+ClamAV load: 20 independent fictional workflows each at concurrency 1, 2, 5 and 10; **80/80 completed**. No unexpected HTTP 5xx, parser capacity 503s, duplicate source/finding/action records or scan rejections. One parser worker peaked at eight waiters, average queue wait 0.173 seconds, zero admission rejections. Nginx returned 175 bounded 429s and all were retried. Measured throughput was 0.758–0.792 workflows/s; local container resource peaks and descriptive p50/p95 values are in `docs/audits/DRILLLOOP_PHASE5_RELEASE_CANDIDATE.md`. The ingress rate limit shaped the result; these are not production capacity targets.
- `.venv/bin/python scripts/rehearse_clamav_integration.py`: actual-scanner API integration test **1 passed** in a separate disposable ClamAV container bound only to loopback; the owned scanner container/signature volume were removed.
- `env -u DATABASE_URL .venv/bin/pytest -q`: **85 passed, 1 skipped**, one existing Starlette/httpx deprecation warning. `.venv/bin/ruff check backend scripts` and format check passed (40 files); `npm --prefix frontend run build` passed; npm and Python dependency audits found zero known vulnerabilities; Compose config, Actionlint, Ruby YAML parse, Gitleaks 8.30.1 and `git diff --check` passed.
- Re-ran the primary synthetic analysis evaluation against the Phase 4 result: zero finding/observation/citation count deltas; 5/5 findings, 21/21 observations and 9/9 canonical citations. The OBJ-02 rows 4/5 citation and five-minute pass/two-minute failure regressions remain fixed. Seven alternate citations remain unlabeled and require evaluator review; no independent real-evidence validation is claimed.
- Final candidate status was 85 non-ignored modified/untracked paths on `main`, including pre-existing Phase 3/4 changes; ignored `drillloop.db` and `.pytest-drillloop.db` remain untouched. The local CI workflow passes static actionlint but is unpublished. Hosted CI, branch protections, staging, production and external integration remain blocked.

The current verdicts, measured results, exact release publication sequence and remaining owner decisions are in [DRILLLOOP_PHASE5_RELEASE_CANDIDATE.md](docs/audits/DRILLLOOP_PHASE5_RELEASE_CANDIDATE.md). Local production-like behavior is ready for owner review; organizational approvals and external verification are still required before release.

## Phase 4 — evidence gaps, local rehearsal, and release gates (4 November 2026)

Phase 3 notes above remain a historical record. Phase 4 work was performed on the existing dirty worktree; no prior changes were reset, no repository database was opened, and no commit was pushed. All rehearsals used newly generated isolated SQLite files or uniquely named disposable PostgreSQL Compose projects/volumes with ownership-checked cleanup.

### Implementation completed

- Fixed the missed OBJ-02 source reference by adding the source wording “outage acknowledgement was requested” to the communication start terms. Added an API regression requiring the proposal to cite control-log rows 4 and 5 and retain the conflicting evaluator note.
- Fixed transcript timing semantics: recording segment offsets are kept in `source_locator` and are not converted into `event_time`; a transcript can supply an explicit segment `event_time`. Added regression coverage for offset-only and explicit event-time inputs. Evaluation dataset revision 2 corrects labels that had mistaken speech position for event time; this change is based on input meaning, not to make code match labels.
- Expanded the evaluator to load each dataset's own exercise/objectives/sources, calculate metrics only when labels support them, suppress citation precision and unsupported-citation rate for incomplete inventories, and report unmatched/duplicate references, false-positive/false-negative and duplicate findings, incorrect objective mappings, timestamps/durations, unknowns/conflicts, and per-objective/per-exercise results.
- Added a separate developer-authored fictional process hold-out under `evals/held-out/`; it was run once and not used for tuning. It is not independently adjudicated or real-world evidence.
- Hardened scanner configuration and upload processing: bounded scanner timeout, optional private quarantine directory, malware/error/timeout/unavailable rejection, rejection audit, no source/timeline persistence on failure, and cleanup. Adapter unit tests use fake executables. A separate actual ClamAV 1.5.4 engine rehearsal passed clean CSV and EICAR paths through a temporary wrapper in an isolated no-network container; no scanner is installed in the DrillLoop app image or approved for deployment, so required mode remains fail closed when unavailable.
- Made staging-mode configuration enforce PostgreSQL, file-injected DB/session/user secrets, named accounts, Secure cookies, trusted hosts, required scan mode, and disabled demo seed. Changed TLS reference Nginx ports to unprivileged 8080/8443 and documented external mapping.
- Added keyboard dialog focus handling and browser checks for login, labels/errors, focus trap, Escape, and focus return. Updated the E2E test to assert focus returns to the trigger that opened the create dialog.
- Added DB pool gauges and `scripts/rehearse_workflow_load.py` for bounded API workflows. Fixed duplicate error accounting in the load report.
- Created Phase 4 evidence-quality, staging, security, owner-decision, and final-gate reports; updated the current backlog, go-live gate, deployment/recovery runbook, and Reader Guide.

### Verification actually run

- `.venv/bin/pytest -q`: **79 passed**, one Starlette/httpx deprecation warning; tests used newly created isolated SQLite databases.
- `.venv/bin/ruff check backend scripts` and `.venv/bin/ruff format --check backend scripts`: passed.
- `npm --prefix frontend run build`: TypeScript and Vite production build passed.
- `uv tool run --from pip-audit pip-audit -r requirements-dev.lock`: no known vulnerabilities. `npm --prefix frontend audit --audit-level=high`: zero vulnerabilities.
- Primary synthetic evaluation, revision 2: 5/5 finding precision/recall/F1 1.00; 21/21 observation precision/recall/F1 1.00; 9/9 canonical citations (recall 1.00); 7 alternative references require evaluator review, so citation precision and unsupported rate are null; 17/17 explicit timestamps and 4/4 expected unknown event times matched; five objective duration/assessment results, four unknowns and one conflict matched; zero finding duplicates, false-positive/false-negative findings, timestamp/duration errors, or objective interpretation errors. All findings remained proposed and reviewer decisions null.
- Held-out fictional process fixture: 2/2 findings, 4/4 observations and 3/3 exhaustive citations; 1.00 precision/recall/F1 where labels are exhaustive; no errors. This developer-authored one-exercise hold-out is not independent quality evidence.
- `.venv/bin/python scripts/rehearse_postgres.py`: **PASS** for fresh PostgreSQL 18 migration, populated disposable upgrade, readiness, named login, fictional browser upload/extraction/analyze/citation/review/action/PDF/refresh/resume, grant/revoke, cross-user detail/report denial, PostgreSQL restart, archive restore to new DB, row snapshots and source hashes. This local demo sets scan mode disabled and does not validate a clean scanner verdict.
- `.venv/bin/python scripts/rehearse_staging.py`: migration, build, test-certificate HTTPS, secure cookie, file secrets, trusted host, metrics authorization, cross-user isolation, required scanner outage/audit/no-source, restarts, and backup/restore to a new DB **PASS**. Previous-image rollback **NOT RUN** because no prior compatible image was supplied. No approved external staging exists.
- Local ClamAV adapter rehearsal: official `clamav/clamav-debian:stable` image digest `sha256:c21aa18cc0a358678255a3dfb343a4555b58f71b97d7b869df8fdf7ea0a5b4b1`; actual engine/database `1.5.4/28172` (2 November 2026); network disabled, no ports, 5 GiB cap, read-only synthetic quarantine mount. Clean CSV imported as `scan_status=clean`; EICAR was rejected with 422 `MALWARE_REJECTED`; source/timeline remained at one clean item, rejection was audited, analysis continued without the EICAR, and quarantine was empty after both runs. Temporary container/quarantine/database were removed; image remains cached. This is not an organizational scanner approval or deployment integration; licensing and signature-update operations need owner review.
- `.venv/bin/python scripts/rehearse_workflow_load.py --workflows-per-level 5 --max-concurrency 2`: disposable local SQLite; concurrency 1 completed 5/5 workflows (5.564 workflows/s, 61.207 requests/s); concurrency 2 completed 2/5 (7.354 completed workflows/s, 125.014 requests/s attempted) with three safe 503 `PARSER_CAPACITY_EXHAUSTED` upload rejections. 89 requests: 69×200, 17×201, 3×503. Upload p50 84.05 ms (n=10), login/session p50 22.62 ms and p95 48.08 ms (n=20); sampled peak API process-tree 197.44 MiB and 83.1 CPU percent (9 samples). No p99 supported. This exposes the one-parser-slot bottleneck; it is not capacity evidence for PostgreSQL or an approved scanner.
- Authenticated read-only GitHub inspection found no remote workflows (`gh workflow list` empty; `ci.yml` not found), no branch protection (`main` API returned “Branch not protected”), and no effective `main` rules (`[]`). Local `.github/workflows/ci.yml` includes lint/format, tests, audits, migrations, browser, secret scan and hardened image smoke, but is untracked and was not hosted. No push or settings were changed.

### Remaining release blockers

- No organization-approved scanner service is configured in the DrillLoop app image or staging. The local actual-engine rehearsal verifies the adapter contract only; required staging/production mode rejects uploads while its scanner is unavailable.
- No approved or externally deployed staging/production host, TLS/DNS, secret service, monitoring, incident owner, identity provider/MFA, evidence policy, retention/deletion, backup encryption, RPO/RTO, concurrency, or latency/availability targets.
- Three of five attempted workflows at concurrency 2 were safely rejected by the single parser slot. Capacity remains insufficiently evidenced pending owner targets and an approved scanner/PostgreSQL workload.
- The remote GitHub repository has no hosted workflow or branch rules. A reviewed/published commit and authorized repository settings changes are required before hosted CI can be verified.
- Independent permitted-record evaluation, independent security/threat-model/penetration review, accessibility assessment, approved staging scanner integration, and previous-image rollback rehearsal remain outstanding.

See [DRILLLOOP_PHASE6_RELEASE_REVIEW.md](docs/audits/DRILLLOOP_PHASE6_RELEASE_REVIEW.md) and [DRILLLOOP_GO_LIVE_GATE.md](docs/audits/DRILLLOOP_GO_LIVE_GATE.md) for current per-scope verdicts. Local Compose success is not a staging or production deployment.

## Phase 11 — rights-safe Business Review replacement (4 November 2026)

- Replaced the template-dependent Business Review generator with a new PptxGenJS source that creates 12 independently authored slides from text and native shapes. The source does not read the previous deck or reuse its theme, masters, template, fonts, screenshots, or other media. Regenerated the editable PPTX and PDF.
- The PDF generator downloads Noto Sans and its SIL OFL 1.1 license from a pinned Google Fonts revision into a temporary directory, verifies both SHA-256 digests, and confirms Fontconfig resolves that exact font file. No standalone font file was added to the repository. The PPTX has no embedded font data; the PDF contains only Noto Sans subsets.
- Added [DRILLLOOP_ASSET_RIGHTS_REGISTER.md](docs/audits/DRILLLOOP_ASSET_RIGHTS_REGISTER.md) with asset provenance, license evidence, artifact review, historical disclosure analysis, license-model options, and content/security-owner approval checklists. Updated README regeneration instructions.
- Did not regenerate the Idea Document, Business Case, or Pitch Deck. Their screenshot ownership, existing PDF font provenance, and/or authorship still require content-owner confirmation. The corrected current Pitch Deck has no local-path image descriptions; the historical public-baseline copy still contains three such descriptions and remains in prior Git history. Security-owner disposition is pending.

### Verification actually run

- `node --check presentation/generate_business_review.js` and `.venv/bin/python -m py_compile scripts/generate_business_review.py`: passed.
- `.venv/bin/python scripts/generate_business_review.py`: generated both outputs; pinned font and license digest checks and exact-font resolution passed; LibreOffice exported the PDF.
- PPTX ZIP/OOXML check: valid package, 12 slides and 12 substantive speaker-note parts; no embedded font binaries, image payloads, comments, external relationships, or personal author values. New deck text has no OpenAI Sans, organization branding, or developer paths.
- PDF check: valid 12-page file; Noto Sans regular/bold subsets embedded; no annotations or detected absolute paths. All pages rendered to PNG and visually reviewed; no apparent clipping or layout overflow.
- Gitleaks 8.30.1 scanned the affected source/docs and PPTX/PDF artifacts with zero findings. `git diff --check` passed.
- No application integration/performance tests were rerun. No application database was accessed or modified. No files were staged; no commit, push, PR, deployment, or history change occurred.

### Remaining publication decisions

- Content owner: confirm ownership and publication authority for the new deck, project-name use, Idea Document attribution, Business Case authorship, product screenshots/UI artwork, Pitch Deck content, exact font provenance in existing PDFs, and the cited-source summaries. If provenance cannot be established, authorize replacement or re-export in a separate follow-up change.
- Security owner: decide whether to accept the historical local-directory path exposure or request a separately scoped history-remediation proposal. No severity is assigned here, and no history was rewritten.
- Project owner: choose public rights-reserved, open-source, or private/organization-controlled distribution; if open source, select code and documentation licenses separately. No project license was added.
- Existing release commit `3bc0c71d7038dc31806b03bcc7fbbf8e62900aad` remains unchanged. The rights register, generator, README/PROGRESS updates, and replacement PPTX/PDF are local follow-up changes and are not staged. Public publication remains on hold.

## Phase 12 — owner-directed publication readiness (4 November 2026)

- Re-exported `DrillLoop_Idea_Document.pdf`, `DrillLoop_Pitch_Deck.pdf`, and `DrillLoop_Architecture.pdf` from their tracked DOCX, PPTX, and SVG sources using the pinned Noto Sans and Noto Sans Symbols fonts. Font and OFL SHA-256 values are checked by `scripts/reexport_publication_pdfs.py`; LibreOffice 26.8.1.1 is required. No standalone font files were added.
- The re-export changes only temporary copies of the Office/SVG sources. Source text nodes and metadata are preserved. The Idea PDF maps legacy Symbol bullets and arrows to equivalent Noto Symbols and scales point sizes to 95% in the temporary copy to retain its existing eight-page pagination. The editable DOCX, Pitch Deck PPTX, and source SVG are unchanged.
- All three PDFs passed page-count, page-size, font embedding, metadata, active-content, annotation, attachment, and path checks. Rendered pages were compared visually with the previous outputs; no blank-page, clipping, or overflow regression was observed.
- Updated [DRILLLOOP_ASSET_RIGHTS_REGISTER.md](docs/audits/DRILLLOOP_ASSET_RIGHTS_REGISTER.md) with the verified PDF-font provenance, Playwright screenshot origin, and the specific remaining UI typography/branding and assignment decisions. Added [DRILLLOOP_PUBLICATION_OWNER_DECISIONS.md](docs/audits/DRILLLOOP_PUBLICATION_OWNER_DECISIONS.md); it records evidence and leaves every owner choice unselected.
- Repository evidence shows screenshots are local DrillLoop UI captures with synthetic data and Lucide icons. It does not prove ownership of the UI/wordmark or employment-assigned work. CSS requests Avenir Next first, but the capture does not record which system font the browser resolved; owner may attest to the rendering rights or authorize a pinned Noto Sans re-capture. Earlier Pitch Deck paths are absent from the current candidate but remain in prior public Git history; the security-owner disposition remains pending.

### Verification performed

- `.venv/bin/python -m py_compile scripts/reexport_publication_pdfs.py`, `.venv/bin/ruff check scripts/reexport_publication_pdfs.py`, and `.venv/bin/ruff format --check scripts/reexport_publication_pdfs.py` passed.
- `.venv/bin/python scripts/reexport_publication_pdfs.py` regenerated only the three listed PDFs. Page counts are 8 (Idea), 13 (Pitch), and 1 (Architecture); all embedded font resources are verified Noto Sans family subsets. PDF metadata authorship for Idea and Pitch is preserved.
- `pypdf` inventory of the six tracked root PDFs confirmed the other reviewed outputs: Business Review uses Noto Sans subsets; Business Case and Evaluation Report use standard PDF Base-14 Helvetica references without embedded font programs.
- Gitleaks 8.30.1 scanned the re-export generator, updated rights/owner/progress documents, and extracted text from the three re-exported PDFs: no leaks found. `git diff --check` and a trailing-whitespace/newline check of the new untracked source and owner record passed.
- No application tests or integration/performance suites were run. No application code, editable source documents, screenshots, or databases were modified. No files were staged or committed; no push, PR, deployment, or history change occurred.
- At the time of this Phase 12 review, owner decisions remained unrecorded; see the dated owner attestation below for the subsequent update. Public publication remained on hold.

### Project-owner attestation update (4 November 2026)

- The project owner states they independently developed DrillLoop and maintain its original source code, documentation, screenshots, branding, and project materials. This owner attestation is recorded in [DRILLLOOP_PUBLICATION_OWNER_DECISIONS.md](docs/audits/DRILLLOOP_PUBLICATION_OWNER_DECISIONS.md) and reflected in the [asset rights register](docs/audits/DRILLLOOP_ASSET_RIGHTS_REGISTER.md); it is not an independent legal finding.
- The attestation does not grant rights to third-party assets or source material and does not override applicable contractual obligations. No generic organizational approval is requested for the owner-attested original materials; any specific contractual exception or third-party issue remains separate.
- Still undecided: project distribution model/license and public-push authorization; factual accuracy of existing authorship metadata; the actual font rendered in screenshots and applicable terms; treatment of cited third-party summaries; and acceptance or separate proposal for the historical Pitch Deck path disclosure. No historical disclosure was accepted, no project license was selected, and no public release was authorized by the ownership attestation.

## CI follow-up — ClamAV signature freshness (5 November 2026)

- The failed hosted run reports `SCANNER_SIGNATURES_STALE` on the first clean upload. The pinned ClamAV `1.5.4` linux/amd64 image's preloaded database reports `ClamAV 1.5.4/28172/Mon Nov  2 06:24:10 2026`, about 73 hours, 2 minutes old at the failure. The Actions teardown log shows FreshClam updated `daily.cld` to version `28174` at 07:26:23 UTC, about two seconds after the test failed at 07:26:21 UTC. This confirms an update/readiness race; the captured update logs show no network or rate-limit error. The old run did not record ClamD's post-update `VERSION`, so whether ClamD loaded version `28174` before teardown is unknown.
- CI now explicitly leaves the official FreshClam daemon enabled at one scheduled check per day and waits up to 10 minutes for `PING` plus a fresh timestamp returned by ClamD's own `VERSION`. On failure, the helper reports the loaded version/age and filtered FreshClam diagnostics with URLs and IP addresses redacted. Freshness remains 72 hours and application scanning remains fail closed.
- Added a regression test that verifies the 72-hour freshness policy continues to reject stale ClamAV signatures. No upload processing behavior changed.

### Verification actually run

- `.venv/bin/ruff check backend scripts` and `.venv/bin/ruff format --check backend scripts`: passed.
- `env -u DATABASE_URL .venv/bin/pytest -q`: 87 passed, 1 skipped, one existing Starlette/httpx deprecation warning. The skipped case is the actual-scanner integration, which needs a fresh ClamAV database.
- `actionlint .github/workflows/ci.yml` and Ruby YAML syntax parsing: passed.
- Isolated pinned linux/amd64 image check confirmed the preloaded database timestamp above. An isolated stale-signature gate check received `PONG`, read that timestamp from ClamD, and failed readiness at age 73.39 hours with the diagnostic emitted. The local image's FreshClam startup attempt could not update because this machine's container network rejected the TLS certificate (FreshClam error 60); the actual CSV/PDF/EICAR integration could not complete locally, and this local network result does not establish the hosted runner's update status.
- Hosted verification after the authorized push: pending at the time of this entry. No application database or existing app data was accessed; scanner checks used disposable containers without a persistent volume.
