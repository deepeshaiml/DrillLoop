# DrillLoop Technical Design

**Version:** working prototype · **Research date:** 26 October 2026 · **Runtime baseline:** Python 3.12.16 / Node 24

**Implementation update (3 November 2026):** The initial design notes below include historical plans and audit findings. The running analysis is now deterministic and objective-configured; it does not call Ollama. Named local-user sessions, role checks, exercise access grants, safe upload validation, an isolated pytest database fixture, the PostgreSQL 18 volume correction, and database readiness checks have been implemented. See `docs/audits/DRILLLOOP_PHASE6_RELEASE_REVIEW.md` and `docs/audits/DRILLLOOP_GO_LIVE_GATE.md` for current verification and remaining production gates.

**Phase 5 update (4 November 2026):** The optional Compose `scanner` profile now runs the digest-pinned official ClamAV Debian 1.5.4 service, separate from the app image. The local PostgreSQL 18.6 + HTTPS/Nginx browser rehearsal passed with actual scan-before-analysis enabled. Readiness checks ClamD capability and a proposed 72-hour signature freshness limit; that threshold and the four daily FreshClam checks are not approved policy. Parser admission is one isolated worker plus a bounded FIFO queue of eight waiters. The local 1/2/5/10 workflow matrix completed 80/80 independent synthetic workflows. These results establish local integration, not organizational scanner approval, approved staging, or production capacity. See `docs/audits/DRILLLOOP_PHASE5_RELEASE_CANDIDATE.md`.

## Quick overview (for nontechnical readers)

DrillLoop is a shared notebook for an emergency exercise. It saves the exercise plan, the evidence people upload, the system’s draft interpretation, the evaluator’s decision, and proof that a follow-up task was completed. It is designed to help people review evidence; it does not make emergency decisions.

**Worked example:** The control-room log says power failed at 09:02 (`EL-01`) and essential circuits were restored at 09:06 (`EL-02`). The written exercise target is 60 seconds. The records support a proposed finding that restoration took about four minutes and missed that target. The cause is not in those records, so it stays unknown. A reviewer decides whether the proposed finding is fair.

| Word used here | Plain-language meaning |
|---|---|
| Observation | What a file directly says. |
| Finding | An evaluator’s conclusion compared with an exercise target. It starts as a proposal. |
| Corrective action | A task to improve performance next time. It needs an owner and a test for completion. |
| Source locator | Where the supporting words are: file and row, line, page, or transcript segment. |
| AAR/IP | After-Action Report and Improvement Plan: what happened, what needs improvement, and who will follow up. |
| HSEEP | FEMA’s Homeland Security Exercise and Evaluation Program. DrillLoop uses some of its exercise-evaluation concepts; it is not certified by FEMA. |
| API | A defined way for the website and server to exchange information. |
| ASR / LLM | Speech-to-text software / software that drafts or rewrites text. Optional ASR has an unverified local route; an LLM adapter is not implemented. |

Readers who want a longer walkthrough and a conceptual example for AI agents can use [DrillLoop Reader Guide](DRILLLOOP_READER_GUIDE.md).

The next sections explain the safety rules and data flow first, then give implementation details for developers. Readers can skip the package-version table and API route list if they only need to understand how the product works.

## 1. Product and safety boundary

DrillLoop supports the exercise-to-improvement cycle: define objectives and expected milestones, collect evidence, reconstruct a traceable timeline, prepare candidate findings, review findings, assign corrective actions, and export an after-action/improvement-plan draft. The application uses synthetic records only in the packaged demo.

The application does not autonomously publish findings, infer events without source observations, resolve conflicting times, assign an owner as if confirmed, or close an action without reviewer-submitted closure evidence. Finding states are `proposed`, `approved`, and `rejected`; action state and reviewer decision are separate fields. The report labels itself as a draft until the relevant review is completed. The template borrows HSEEP concepts and is not an official HSEEP form or certification.

## 2. Architecture

See [DrillLoop_Architecture.svg](DrillLoop_Architecture.svg). The running system has a React/TypeScript client, FastAPI application, and SQLAlchemy persistence. SQLite is the no-setup local default; Compose runs PostgreSQL. Original files, extracted content, SHA-256 fingerprints, observations, findings, actions, and reviewer audit events are persisted. No vector database is used for this small corpus.

```text
Evidence files → type-specific parser → immutable source + exact observations
      → normalized/uncertain timeline → deterministic candidate rules
      → objective mapping + exact evidence IDs → proposed findings/actions
      → authorized reviewer decisions → PDF AAR/IP export
```

Candidate creation is a fixed workflow rather than an open-ended tool-using agent. For this safety-sensitive review path it gives repeatable behavior, auditable rules, and simpler testing. LangGraph would add little to this compact flow; it can be reconsidered if future deployments need durable multi-stage queues or long-running human checkpoints.

### Main services

- `backend/app/evidence.py`: TXT/MD, CSV, JSON event/transcript, and selectable-text PDF parsing. pypdf is used for PDF extraction; scanned image OCR is not implemented.
- `backend/app/pipeline.py`: deterministic, configured objective rules for elapsed time, reported duration, event presence, and required fields; missing/contradictory evidence is retained as unknown or conflict. It emits source-cited proposed findings with null owner and due date.
- `backend/app/main.py`: named-user sessions, role and organization-scoped exercise grants, exercise setup/objective edits before analysis, ingestion, optional local ASR route, human review, action transitions, source download, audit log, readiness check, and PDF response.
- `backend/app/reporting.py`: generated report that keeps observation, interpretation, evidence, reviewer status, and action fields distinct.
- `frontend/`: React/TypeScript interface with overview, evidence, timeline, finding review, corrective-action register, source download, and exercise creation.

## 3. Data model and evidence schema

| Entity | Core fields | Purpose |
|---|---|---|
| Exercise | ID, scenario, date, duration, objectives, criteria, evaluator roles, participants, expected milestones | Planning baseline and performance targets |
| Source | Filename, media type, original bytes, extracted text, SHA-256, parser metadata | Original evidence, integrity reference, and extraction provenance |
| Observation | Source ID, exact text, locator, raw/normalized time, timing confidence, type, extraction method, recognition confidence | Source-level event or transcript segment; unresolved time remains nullable |
| Finding | Code, category, objective ID, observation, interpretation, evidence observation IDs, confidence, reviewer status/note | Proposed or human-reviewed synthesis |
| Corrective action | Finding ID, evidence IDs, owner, priority, due date, acceptance criteria, status, reviewer decision, closure evidence | Improvement tracking and verified closure |
| Audit event | Actor, action, object ID, timestamp, decision details | Reviewer history for edits, approval, rejection, and closure |

CSV row locators include row number and source event ID. Text notes retain line numbers. PDF locations retain page and line. Transcript imports retain segment index and relative offset; if the recording start time is absent the event remains relative/unplaced. Uploaded source bytes are downloadable from the evidence viewer.

### Time and conflict rules

- ISO timestamps normalize to ISO 8601; `HH:MM[:SS]` combines with the exercise date and carries minute-level confidence.
- Missing or unparseable times remain `unknown` and do not receive a synthetic timestamp.
- An evaluator note explicitly describing 09:10 versus 09:11 is surfaced as an unresolved conflict. DrillLoop does not select a winner.
- A transcript segment with low pre-generated recognition confidence is marked uncertain. Relative ASR offsets have no absolute event time unless a recording start time is provided.

## 4. Evaluation workflow

1. **Extract:** parsers create one observation per CSV row, non-empty note line, PDF line, or transcript segment.
2. **Candidate detection:** each exercise objective must have an explicit supported rule and configured evidence phrases. No generic fixture threshold or event phrase is applied to another exercise.
3. **Objective mapping:** a candidate maps to the rule-bearing objective ID. Missing objectives block analysis; objectives without a supported rule remain needs-review.
4. **Evidence retrieval:** rules return specific observation IDs; the API resolves each ID to the original source and locator. No candidate is stored without at least one evidence link.
5. **Uncertainty checks:** missing timestamps, explicitly contradictory timing notes, and ASR confidence remain visible to evaluators.
6. **Corrective-action drafting:** improvement candidates create a proposed, generic evaluator-review action. Owner and due date stay null until a human supplies them.
7. **Review:** an authorized human can edit a proposed finding through the API and approve/reject it. Action approval requires an approved linked finding, an owner, and a due date. Closure requires approval and reviewer-entered closure evidence.
8. **Report:** the generated AAR/IP includes timeline, findings, sources, objectives, actions, review state, and explicit synthetic/draft caveats.

### LLM status

The current application does not invoke an LLM or other external analysis service. The deterministic rules are the only analysis path. Any future model adapter needs an agreed contract, validation tests, license/version record, timeout and cost controls, and a review boundary before it can be described as implemented.

## 5. Offline ASR path

An optional `/api/exercises/{id}/audio` route writes an uploaded recording to a temporary file and invokes `faster-whisper` using CPU int8 and VAD. A locally supplied CTranslate2 model directory is mandatory; the route does not fetch a checkpoint. The result stores model/package version, detected language, segment offsets, transcript text, and uncertainty notice. The MVP does not provide word-level confidence or diarization and has not been tested for multilingual accuracy. The app warns users to review transcription against audio.

Suggested English-only evaluation starting point: `Systran/faster-whisper-small.en` (MIT model card, approximately 486 MB weight file at the time reviewed). The English-only model is inappropriate for claims about other languages. Larger models and GPU inference trade additional storage/compute for possible accuracy; this demo measured none of those trade-offs. The pre-generated transcript in `demo/evidence/transcript.json` includes a synthetic 0.58-confidence “two” → “too” substitution so the review state can be demonstrated without audio inference.

## 6. Technology and license selection

Versions below were checked on 26 October 2026; Python backend and frontend build were exercised on the local runtime. Pin upgrades and rerun compatibility/security checks before deployment.

| Component | Selected version | License / use | Decision |
|---|---:|---|---|
| Python | 3.12.16 runtime target | PSF | Kept the mature 3.12 line for broad ASR/parser wheel compatibility while Python 3.14.9/3.15 are newer. Local verification ran on 3.12.13. |
| FastAPI | 0.162.0 | MIT | API, validation integration, OpenAPI, multipart upload. |
| Pydantic | 2.14.1 | MIT | Request/transition schema validation. |
| SQLAlchemy | 2.0.48 | MIT | SQLite/PostgreSQL portability without a custom data layer. |
| PostgreSQL | 18.6 | PostgreSQL License | Docker Compose persistence; SQLite remains simplest for local setup. |
| React / React DOM | 19.3.1 | MIT | Stable component UI. |
| TypeScript | 5.9.3 | Apache 2.0 | Conservative compiler choice for the prototype; Vite 8 build succeeded. |
| Node | 24 in Docker; tested locally on 26.9.0 | MIT | Node 24 meets Vite 8's supported engine range. |
| Vite / React plugin | 8.3.5 / 6.1.2 | MIT | Plugin 6 is required for Vite 8 compatibility. |
| pypdf | 6.21.4 | BSD-3-Clause | Selectable-text PDF parser. Chosen over PyMuPDF's AGPL/commercial dual license to keep the PDF path permissive for commercial deployment. |
| ClamAV service | 1.5.4; official Debian image digest `sha256:c21aa18cc0a358678255a3dfb343a4555b58f71b97d7b869df8fdf7ea0a5b4b1` | GPLv2; see [ClamAV project documentation](https://docs.clamav.net/) and [Docker deployment documentation](https://docs.clamav.net/manual/Installing/Docker.html). | Optional Compose service, separate from the app image; locally tested with persistent signatures and actual ClamD scans. Security/legal approval, signature provenance/freshness policy, update egress and quarantine operations remain owner decisions before organizational use. |
| faster-whisper | 1.2.1 optional | MIT | CTranslate2-based offline ASR; not installed in the default dependency set. |
| Whisper weights | MIT | MIT | OpenAI states code and model weights are MIT-licensed; separately verify the selected checkpoint card. |
| Ollama + Qwen3-4B | research option only; not called by the application | Qwen3 Apache 2.0 | No current feature or integration. Any later implementation requires adapter and evaluation work. |
| python-docx | 1.2.0 | MIT | Editable idea document and pitch speaker notes generation support. |
| ReportLab | 5.1.0 | BSD-style | PDF exports and accompanying PDF reports. |
| PptxGenJS | 4.0.1 | MIT | Editable PowerPoint shapes/text and slide speaker notes; patched `image-size` 2.0.4 override keeps the presentation dependency audit clean. |
| pytest / Ruff | 9.1.1 / 0.17.2 | MIT / MIT | Tests and lint. |

Sentence Transformers, a vector index, Transformers, and LangGraph are not required in the small offline baseline. Exact strings/IDs are better suited to the packaged synthetic fixture, and no retrieval model adds demonstrable value at this size. A later retrieval evaluation should compare source-level citation precision before adding embeddings. The AAR/IP export and business/evaluation briefs use ReportLab; the idea-document PDF is exported from its editable DOCX when LibreOffice is available, with a ReportLab fallback. Pitch PDF rendering uses LibreOffice during packaging, not a production dependency.

## 7. Interfaces and errors

- `POST /api/auth/login`, `GET /api/auth/session`, `POST /api/auth/logout`
- `GET /api/exercises`, `POST /api/exercises`, `GET /api/exercises/{id}`, `PUT /api/exercises/{id}/objectives`
- `GET/POST /api/exercises/{id}/access`, `DELETE /api/exercises/{id}/access/{user_id}`
- `POST /api/exercises/{id}/evidence`, `/transcripts`, and optional `/audio`
- `POST /api/exercises/{id}/analyze`
- `PATCH /api/findings/{id}` and `POST /api/findings/{id}/review`
- `PUT /api/actions/{id}`, `POST /api/actions/{id}/review`, `POST /api/actions/{id}/close`
- `GET /api/sources/{id}/download`, `GET /api/exercises/{id}/report.pdf`

Every data route requires a named session and applicable role/exercise grant; unsafe cookie-authenticated requests require a CSRF token. Validation distinguishes malformed/unsupported files and timestamps, missing PDF text, missing objectives, absent local ASR package/model, ASR failure, missing authentication/configuration, forbidden role/grant, CSRF failure, locked objectives, incomplete action approval, unapproved linked findings, and missing closure evidence. Errors return explicit code/message payloads for the UI.

## 8. Security and deployment boundaries

- Local-first by default; no cloud model, telematics, or third-party fonts are required. Source uploads remain in the configured database.
- Local named users are configured by `DRILLLOOP_USERS_JSON` with scrypt password hashes, roles, organization IDs, and a signed eight-hour session. The organization must still select an enterprise identity provider and production session/revocation policy. The demo login rate limiter is in-process and is not a production edge control.
- The application does not encrypt database values or uploaded bytes and does not redact personal information or enforce retention policy. The packaged demo uses fictional records and has not been validated for protected patient or operational data.
- Required scan mode rejects unavailable, failed, timed-out, stale-signature, or malicious verdicts before source creation. The optional Compose scanner is private to the app/scanner network, has no host port, persists signatures, and runs controlled FreshClam updates. Readiness verifies PING/VERSION, signature age, clean scan capability, and EICAR detection; container health alone is not treated as scanner readiness. The local 72-hour freshness limit and four daily checks are proposed values. The scanner is locally integrated but not organization-approved; image/license, signature/update policy, quarantine operations, and release policy remain open.
- Analysis uses no cloud or local LLM. Optional faster-whisper inference uses a locally staged model; diarization and multilingual accuracy are not claimed. Upload size/count/row bounds, parser timeout and worker isolation are implemented. Parser admission defaults to one active worker and eight bounded FIFO waiters, with a configurable wait timeout; quarantine is private, per-job, and cleaned on success, rejection, timeout, cancellation, and parser failure.
- Production still needs enterprise SSO/identity provisioning, organization-owned TLS/DNS and managed secrets, encrypted backups and restore, retention/deletion, operational logs/monitoring/alerts, a compatible prior-image rollback rehearsal, threat modeling, owner-approved load targets, independent evaluation, and an approved emergency-management evaluation.
- Compose requires a PostgreSQL password and named-user configuration; there are no shipped default credentials. The configured local password flow remains a demo boundary.

## 9. Verification and limits

Phase 5 recorded 85 backend tests passed and one optional scanner test skipped in the host suite; that test separately passed against actual ClamAV. Phase 6's final backend suite passed 86 tests with one optional scanner skip, and the actual-scanner integration test separately passed. Ruff, frontend production build, dependency audits, Actionlint, candidate-only secret scan, Compose config, migration checks, and `git diff --check` passed locally. Two disposable PostgreSQL 18.6 + HTTPS/Nginx + ClamAV replays each completed 80/80 synthetic workflows across concurrency 1/2/5/10. The first had one safely retried parser-capacity 503; the final replay against the checked-in Nginx upstream had none. Both had zero unexpected 5xx. These are local synthetic checks. No approved staging, hosted CI execution, real integration, independent real-evidence validation, independent accessibility/security assessment, or production-capacity target was verified. See `docs/audits/DRILLLOOP_PHASE5_RELEASE_CANDIDATE.md` and `docs/audits/DRILLLOOP_PHASE6_RELEASE_REVIEW.md` for commands and limitations.

The fixture benchmark measures observation precision/recall, finding precision/recall, supported-citation rate, exact event-log citations, timeline timestamp matches, corrective-action field completion, rule latency, and process RSS. It intentionally does not report manual report time, reviewer correction time, ASR WER, local LLM quality, or dollar savings. Read [DrillLoop_Evaluation_Report.pdf](DrillLoop_Evaluation_Report.pdf) and `demo/benchmark_results.json` for actual results and limitations.

The proposed first validation segment is hospital preparedness teams reviewing tabletop exercises. A next evaluation would interview two or three prospective users, establish a current-process baseline, and compare both workflows on the same permitted records. Evaluator-labeled evidence from an unfamiliar exercise would measure missed and incorrect findings, citation support, and timeline agreement. One relevant alternative would be selected with the pilot partner for a same-workflow comparison. Success thresholds, partner access, and schedule are not yet established; the partner would set the thresholds before measurement.

## 10. References

- FEMA, [Homeland Security Exercise and Evaluation Program Doctrine, January 2020](https://www.fema.gov/sites/default/files/2020-04/Homeland-Security-Exercise-and-Evaluation-Program-Doctrine-2020-Revision-2-2-25.pdf).
- FEMA Preparedness Toolkit, [Evaluation and AAR/IP workflow](https://preptoolkit.fema.gov/web/training/evaluation).
- California Department of Public Health, [Medical & Health Exercise: Power Loss scenario](https://www.cdph.ca.gov/Programs/EPO/Pages/swmhe_scenarios_power_loss.aspx).
- Mid-South Emergency Planning Coalition, [2023 Full Scale Exercise AAR/IP example](https://midsouthepc.org/wp-content/uploads/2024/03/Mid-South-HCC-2023-Non-Hospital-FSE-AAR.pdf) (public example, facility-specific details; reference for format only).
- Veoci, [After-action reporting and corrective-action product page](https://veoci.com/emergency-management/after-action-reporting/).
- D4H, [Emergency response team readiness software](https://www.d4h.com/team-readiness-software).
- Python.org, [Python release versions](https://www.python.org/doc/versions/).
- FastAPI, [release notes](https://fastapi.tiangolo.com/release-notes/) and [PyPI FastAPI 0.162.0](https://pypi.org/project/fastapi/0.162.0/).
- Pydantic, [validation changelog](https://pydantic.dev/docs/validation/latest/get-started/changelog/); React, [version history](https://react.dev/versions); PostgreSQL, [versioning policy](https://www.postgresql.org/support/versioning/).
- pypdf, [PyPI 6.21.4 license metadata](https://pypi.org/project/pypdf/6.21.4/).
- SYSTRAN, [faster-whisper repository](https://github.com/SYSTRAN/faster-whisper); Systran, [faster-whisper-small.en model card](https://huggingface.co/Systran/faster-whisper-small.en); OpenAI, [Whisper license statement](https://github.com/openai/whisper/blob/main/README.md).
- Qwen, [Qwen3 model sizes, Apache 2.0 licenses, and local use](https://qwenlm.github.io/blog/qwen3/); Ollama, [local JSON/structured output API](https://github.com/ollama/ollama/blob/main/docs/api.md).
- PptxGenJS, [speaker notes API](https://gitbrent.github.io/PptxGenJS/docs/speaker-notes.html) and [MIT license](https://gitbrent.github.io/PptxGenJS/license/).
