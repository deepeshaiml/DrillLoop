# DrillLoop Technical Design

**Version:** hackathon MVP · **Research date:** 26 October 2026 · **Runtime baseline:** Python 3.12.16 / Node 24

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
| ASR / LLM | Speech-to-text software / software that drafts or rewrites text. Optional AI tools remain subordinate to evidence and human review. |

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
- `backend/app/pipeline.py`: deterministic observation matching, finding candidates, objective links, exact evidence observation IDs, and corrective-action drafts. Optional local Ollama can rephrase improvement-action and acceptance text only; it cannot originate a finding or evidence citation.
- `backend/app/main.py`: exercise CRUD, ingestion, local ASR route, human review, action state transitions, original-source download, audit log, and PDF response.
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
2. **Candidate detection:** compact rules inspect the text for the labeled exercise signals: primary power loss and four-minute restoration, delayed acknowledgement, contradictory response duration, completed cold-chain procedure, and missing owner.
3. **Objective mapping:** each candidate maps to a stated objective ID. A missing objective blocks analysis.
4. **Evidence retrieval:** rules return specific observation IDs; the API resolves each ID to the original source and locator. No candidate is stored without at least one evidence link.
5. **Uncertainty checks:** missing timestamps, explicitly contradictory timing notes, and ASR confidence remain visible to evaluators.
6. **Corrective-action drafting:** improvement candidates create a proposed action with supporting evidence, priority, due date, acceptance criteria, and owner field. The synthetic missing-owner case intentionally remains unassigned.
7. **Review:** an authorized human can edit a proposed finding through the API and approve/reject it. Action approval requires an approved linked finding, an owner, and a due date. Closure requires approval and reviewer-entered closure evidence.
8. **Report:** the generated AAR/IP includes timeline, findings, sources, objectives, actions, review state, and explicit synthetic/draft caveats.

### Optional local language model

The default mode is deterministic and has no LLM dependency. Set `OLLAMA_MODEL` and `OLLAMA_BASE_URL` to invoke the local Ollama `/api/generate` endpoint for action/acceptance wording. The app accepts only known candidate codes and bounded strings. When the local service is unavailable or returns invalid data, the deterministic wording remains. Model output does not alter event observations, objective links, finding codes, evidence IDs, or review state. Only loopback/private in-container Ollama hostnames are permitted by the app.

Qwen3-4B is the optional suggested local draft model because the Qwen project publishes Qwen3 dense checkpoints under Apache 2.0. We did not download or run that model in this benchmark, so no resource, quality, or latency claim is made. Operators must verify the exact model revision/tag, hardware fit, license, and local runtime conditions before use. For private deployments, stage model weights on an approved host and disable internet egress after provisioning.

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
| TypeScript | 5.9.3 | Apache 2.0 | Conservative compiler choice for the hackathon; Vite 8 build succeeded. |
| Node | 24 in Docker; tested locally on 26.9.0 | MIT | Node 24 meets Vite 8's supported engine range. |
| Vite / React plugin | 8.3.5 / 6.1.2 | MIT | Plugin 6 is required for Vite 8 compatibility. |
| pypdf | 6.21.2 | BSD-3-Clause | Selectable-text PDF parser. Chosen over PyMuPDF's AGPL/commercial dual license to keep the PDF path permissive for commercial deployment. |
| faster-whisper | 1.2.1 optional | MIT | CTranslate2-based offline ASR; not installed in the default dependency set. |
| Whisper weights | MIT | MIT | OpenAI states code and model weights are MIT-licensed; separately verify the selected checkpoint card. |
| Ollama + Qwen3-4B | optional local service/model | Qwen3 Apache 2.0 | Local wording aid only; not included or benchmarked. Ollama's runtime and selected model tag should be verified at deployment. |
| python-docx | 1.2.0 | MIT | Editable idea document and pitch speaker notes generation support. |
| ReportLab | 5.1.0 | BSD-style | PDF exports and accompanying PDF reports. |
| PptxGenJS | 4.0.1 | MIT | Editable PowerPoint shapes/text and slide speaker notes; patched `image-size` 2.0.4 override keeps the presentation dependency audit clean. |
| pytest / Ruff | 9.1.1 / 0.17.2 | MIT / MIT | Tests and lint. |

Sentence Transformers, a vector index, Transformers, and LangGraph are not required in the small offline baseline. Exact strings/IDs are better suited to the packaged synthetic fixture, and no retrieval model adds demonstrable value at this size. A later retrieval evaluation should compare source-level citation precision before adding embeddings. The AAR/IP export and business/evaluation briefs use ReportLab; the idea-document PDF is exported from its editable DOCX when LibreOffice is available, with a ReportLab fallback. Pitch PDF rendering uses LibreOffice during packaging, not a production dependency.

## 7. Interfaces and errors

- `GET /api/exercises`, `POST /api/exercises`, `GET /api/exercises/{id}`
- `POST /api/exercises/{id}/evidence`, `/transcripts`, and optional `/audio`
- `POST /api/exercises/{id}/analyze`
- `PATCH /api/findings/{id}` and `POST /api/findings/{id}/review`
- `PUT /api/actions/{id}`, `POST /api/actions/{id}/review`, `POST /api/actions/{id}/close`
- `GET /api/sources/{id}/download`, `GET /api/exercises/{id}/report.pdf`

Validation distinguishes malformed/unsupported files, missing PDF text, missing objectives, absent local ASR package/model, ASR failure, reviewer-key failure, incomplete action approval, unapproved linked findings, and missing closure evidence. Errors return explicit code/message payloads for the UI.

## 8. Security and deployment boundaries

- Local-first by default; no cloud model, telematics, or third-party fonts are required. Source uploads remain in the configured database.
- The reviewer key is a shared demo secret passed in a header; it does not implement user identity, least privilege, tenant isolation, session expiry, or enterprise SSO.
- The MVP does not encrypt database values or uploaded bytes, run malware scans, redact personal information, implement retention controls, or conduct a security assessment. The packaged demo uses fictional records and has not been validated for protected patient or operational data.
- The default workflow makes no cloud-model call. Optional faster-whisper inference uses a locally staged model; optional Ollama is configured as a local/private service for action wording. Deployment-level data-flow and security review has not been performed.
- Production would need SSO/RBAC, encrypted transport/storage and managed backups, tenant isolation, secrets management, access logging, retention/deletion, malware and PDF resource controls, dependency scanning, threat modeling, and a clinical/emergency-management review process.
- Report approval and closure are authorization-gated, but development credentials are intentionally visible in the demo guide. Replace them and the default Compose PostgreSQL password before exposing any environment.

## 9. Verification and limits

Recorded verification: Python 3.12.13, FastAPI 0.162.0, Pydantic 2.14.1, SQLAlchemy 2.0.48, React 19.3.1, TypeScript 5.9.3, Vite 8.3.5, local SQLite. `pytest` exercises parsers, source-byte downloads, evidence citations, status gates, incomplete objectives, and PDF export. `ruff check backend` and the TypeScript/Vite production build are run separately. Docker/PostgreSQL and optional ASR/Ollama are configuration paths; their inference path is not part of the recorded benchmark.

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
- pypdf, [PyPI 6.21.2 license metadata](https://pypi.org/project/pypdf/6.21.2/).
- SYSTRAN, [faster-whisper repository](https://github.com/SYSTRAN/faster-whisper); Systran, [faster-whisper-small.en model card](https://huggingface.co/Systran/faster-whisper-small.en); OpenAI, [Whisper license statement](https://github.com/openai/whisper/blob/main/README.md).
- Qwen, [Qwen3 model sizes, Apache 2.0 licenses, and local use](https://qwenlm.github.io/blog/qwen3/); Ollama, [local JSON/structured output API](https://github.com/ollama/ollama/blob/main/docs/api.md).
- PptxGenJS, [speaker notes API](https://gitbrent.github.io/PptxGenJS/docs/speaker-notes.html) and [MIT license](https://gitbrent.github.io/PptxGenJS/license/).
