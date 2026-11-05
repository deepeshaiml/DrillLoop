# DrillLoop Phase 6 — Release File Manifest

**Snapshot:** 4 November 2026
**Worktree:** `release/drillloop-phase6-rc1` at `78f2d594a88e5512672720f311aa8e1dceb344f1`.
**Inventory:** 99 changed paths: 34 modified tracked files, one renamed document, and 64 untracked paths. No standalone deletions.
**Proposed release set:** 90 `INCLUDE`; 9 `EXCLUDE` (eight superseded audit snapshots and the empty migration placeholder). The nine exclusions remain unstaged and untouched.

`INCLUDE` means suitable for the proposed PR after the listed reviewers inspect the path. It is not a claim of organizational approval. `EXCLUDE` means leave the current local file untouched and out of this first PR. The `Status` column reports Git status at this review; the manifest includes its own new `??` path.

## 1. Application source

| Status | Path | Purpose / release | Security implication and reviewer | Unresolved concern |
|---|---|---|---|---|
| ?? | `backend/app/auth.py` | Named-user authentication, scrypt hashes, signed sessions, CSRF and roles; **INCLUDE**. | Security-sensitive identity/session code; Application Security and Identity reviewer. | Enterprise IdP/MFA, account lifecycle and shared revocation remain open. |
| M | `backend/app/evidence.py` | Source parsing, validation, locators and provenance; **INCLUDE**. | File parsing boundary; Application Security and QA reviewer. | Independent permitted-evidence coverage remains limited. |
| ?? | `backend/app/limits.py` | Upload and parser bounds; **INCLUDE**. | Resource-exhaustion control; Application Security/SRE reviewer. | Values need owner-approved staging workload. |
| M | `backend/app/main.py` | API, authorization, review gates, audit and lifecycle; **INCLUDE**. | Broad route/tenant boundary; Application Security reviewer. | Independent route/role review still needed. |
| ?? | `backend/app/observability.py` | Structured metrics and observability; **INCLUDE**. | Check labels/logs for evidence or identity leakage; SRE/Security reviewer. | Platform retention and alert thresholds are unselected. |
| M | `backend/app/pipeline.py` | Deterministic source-linked objective analysis; **INCLUDE**. | Finding provenance and reviewer state; Product and independent evaluator review. | Alternate citations remain incompletely labeled; no real-world accuracy claim. |
| ?? | `backend/app/runtime_config.py` | Fail-closed environment validation; **INCLUDE**. | Enforces production/staging safety invariants; Security/Operations reviewer. | Organization values and identity/scanner policy remain unapproved. |
| M | `backend/app/schemas.py` | Request/response validation and explicit evidence fields; **INCLUDE**. | Contract controls; Application and QA reviewer. | Conceptual examples are not API schemas. |
| ?? | `backend/app/upload_processing.py` | Isolated parser, bounded queue, scanner protocol and quarantine; **INCLUDE**. | Upload/malware boundary; Application Security and Security Operations reviewer. | ClamAV license, trust boundary, freshness/update and quarantine policy require approval. |
| M | `frontend/src/App.tsx` | Login, source-linked review, action and report workflows; **INCLUDE**. | UI authorization and human decision display; Frontend, Product and Accessibility reviewer. | Formal accessibility and SSO journey are not independently verified. |
| M | `frontend/src/styles.css` | Workflow styling and responsive states; **INCLUDE**. | Presentation only; Frontend/Accessibility reviewer. | Formal responsive/screen-reader assessment remains open. |

## 2. Database models and migrations

| Status | Path | Purpose / release | Security implication and reviewer | Unresolved concern |
|---|---|---|---|---|
| M | `backend/app/db.py` | SQLAlchemy engine/session and migration-state checks; **INCLUDE**. | Database connection and startup safety; DBA/Application reviewer. | Existing populated DB adoption requires a separate clone rehearsal. |
| ?? | `backend/app/database_config.py` | File-based DB secret resolution; **INCLUDE**. | Secret-file validation; Security/DBA reviewer. | Target secret manager and rotation are unselected. |
| M | `backend/app/models.py` | Exercise/evidence/review/action and audit tables; **INCLUDE**. | Data access boundaries and stored evidence; DBA/Data owner reviewer. | Retention, deletion, classification and encryption policy remain open. |
| ?? | `alembic.ini` | Alembic configuration; **INCLUDE**. | Migration target configuration; DBA reviewer. | Review target URL handling before environment-specific use. |
| ?? | `migrations/env.py` | Online/offline Alembic environment; **INCLUDE**. | Explicit migrations; DBA/Security reviewer. | Never point at an existing DB without approved backup and clone procedure. |
| ?? | `migrations/script.py.mako` | Migration template; **INCLUDE**. | Generated migration baseline; DBA reviewer. | New migrations require review and forward recovery plan. |
| ?? | `migrations/versions/8bb36fe0ea4c_initial_schema.py` | Initial versioned schema; **INCLUDE**. | Creates tables on an explicit migration target; DBA reviewer. | Existing unversioned database adoption is not automatic. |
| ?? | `migrations/versions/a53481bc2d73_record_upload_scan_state.py` | Adds upload scan provenance; **INCLUDE**. | Scan state affects whether evidence is usable; DBA/Security reviewer. | Downgrade is intentionally unsupported; recovery is restore/forward-fix. |
| ?? | `migrations/versions/.gitkeep` | Empty-directory placeholder; **EXCLUDE** because the directory contains real migrations. | No runtime/security effect. | Redundant; leave the local file in place and do not stage. |

## 3. Tests and evaluations

All listed fixtures and test identities are synthetic. Test-only values must never be reused as deployment credentials.

| Status | Path | Purpose / release | Security implication and reviewer | Unresolved concern |
|---|---|---|---|---|
| M | `backend/tests/conftest.py` | Creates unique owner-marked temporary DBs and refuses inherited `DATABASE_URL`; **INCLUDE**. | Protects existing databases; QA/DBA reviewer. | Preserve its collection-time refusal guard. |
| ?? | `backend/tests/test_auth.py` | Authn, CSRF, session and role regressions; **INCLUDE**. | Identity security; Application Security reviewer. | No IdP/MFA integration test without an owner-selected IdP. |
| ?? | `backend/tests/test_clamav_integration.py` | Optional real scanner contract test; **INCLUDE**. | Uses actual scanner only when explicitly configured; Security Operations reviewer. | CI scanner is disposable, not organization-approved. |
| ?? | `backend/tests/test_db_safety.py` | Test DB isolation and refusal checks; **INCLUDE**. | Protects existing application data; DBA/QA reviewer. | Keep isolated target checks intact. |
| M | `backend/tests/test_evidence.py` | Parser, source locator and extraction regressions; **INCLUDE**. | Untrusted file handling; QA/Application Security reviewer. | Synthetic cases do not replace permitted-evidence testing. |
| ?? | `backend/tests/test_health.py` | Readiness/liveness behavior; **INCLUDE**. | Avoids reporting ready without core services; SRE reviewer. | Platform probes and alert routing remain unselected. |
| ?? | `backend/tests/test_migrations.py` | Migration and populated-disposable upgrade safety; **INCLUDE**. | Prevents destructive schema assumptions; DBA reviewer. | Existing customer DB adoption is still manual and gated. |
| ?? | `backend/tests/test_pipeline.py` | Deterministic analysis/citation regressions; **INCLUDE**. | Human review and evidence support; QA/independent evaluator reviewer. | Seven alternate references are not fully adjudicated. |
| ?? | `backend/tests/test_recovery.py` | Non-destructive recovery tests; **INCLUDE**. | Restore target safety; DBA/QA reviewer. | RPO/RTO, backup encryption and ownership remain open. |
| ?? | `backend/tests/test_runtime_config.py` | Required production/staging configuration validation; **INCLUDE**. | Fail-closed config; Security/Operations reviewer. | Organization-specific values need decisions. |
| ?? | `backend/tests/test_upload_processing.py` | Scanner failures, parser admission and cleanup; **INCLUDE**. | Malware and resource-exhaustion boundary; Application Security reviewer. | Actual approved scanner policy requires external validation. |
| M | `backend/tests/test_workflow.py` | End-to-end API workflow and human gates; **INCLUDE**. | State transitions and reviewer attribution; QA/Product reviewer. | Independent role matrix review remains open. |
| ?? | `frontend/e2e/live-workflow.mjs` | Browser workflow, review, action and accessibility smoke checks; **INCLUDE**. | Uses synthetic test identities and data; QA/Accessibility reviewer. | Not a formal accessibility conformance test. |
| ?? | `evals/datasets/synthetic-hospital-v1.json` | Versioned fictional evaluation labels; **INCLUDE**. | Ground truth explicitly labeled fictional; independent evaluator review. | Citation label inventory is incomplete. |
| ?? | `evals/held-out/README.md` | Documents fictional process hold-out limits; **INCLUDE**. | Prevents overclaiming hold-out independence; Evaluation reviewer. | Dataset is developer-authored, not independently adjudicated. |
| ?? | `evals/held-out/sources/library_evacuation.csv` | Synthetic held-out source evidence; **INCLUDE**. | Fictional exercise material; Evaluation reviewer. | Preserve hold-out status and labels. |
| ?? | `evals/held-out/synthetic-library-v1.json` | Synthetic held-out exercise/labels; **INCLUDE**. | Explicit fictional data; Evaluation reviewer. | Not a real-world accuracy benchmark. |
| ?? | `evals/schemas/drillloop-evaluation-v1.schema.json` | Evaluation file schema; **INCLUDE**. | Schema validation; QA/Evaluation reviewer. | Conceptual response examples are not API schemas. |
| M | `scripts/benchmark.py` | Legacy synthetic fixture benchmark; **INCLUDE**. | Creates no production evidence; QA reviewer. | Metrics are fixture-specific only. |
| ?? | `scripts/__init__.py` | Supports importing evaluation/rehearsal helpers; **INCLUDE**. | No runtime secret handling; Engineering reviewer. | None identified. |
| ?? | `scripts/evaluate_analysis.py` | Versioned synthetic evaluation runner; **INCLUDE**. | Writes only to a new explicitly requested output; Evaluation reviewer. | Independent labels and acceptance thresholds remain open. |
| ?? | `scripts/isolated_runtime.py` | Creates marked temporary SQLite runtime; **INCLUDE**. | Cleanup checks owner marker/token; QA/DBA reviewer. | Preserve ownership checks. |
| ?? | `scripts/load_test.py` | Capped loopback readiness load; **INCLUDE**. | Bounded work and temporary data; SRE reviewer. | Local results are not capacity targets. |
| ?? | `scripts/rehearse_clamav_integration.py` | Disposable real ClamAV API integration; **INCLUDE**. | Loopback-only binding and label-checked cleanup; Security Operations reviewer. | Scanner image/policy not approved for organizational use. |
| ?? | `scripts/rehearse_load_test.py` | Bounded API load rehearsal; **INCLUDE**. | Uses isolated resources; SRE reviewer. | Confirm against owner workload before capacity acceptance. |
| ?? | `scripts/rehearse_phase5_load.py` | Synthetic PostgreSQL/scanner concurrency workflows; **INCLUDE**. | Caps and retries only safe responses; SRE/QA reviewer. | A safe parser 503 occurred in one Phase 6 run; see replay record. |
| ?? | `scripts/rehearse_postgres.py` | Disposable PostgreSQL workflow/recovery rehearsal; **INCLUDE**. | Uses unique project and owner-checked cleanup; DBA/QA reviewer. | Scan-disabled path is not malware-scan verification. |
| ?? | `scripts/rehearse_staging.py` | Full local TLS/PostgreSQL/ClamAV/browser/load rehearsal; **INCLUDE**. | Unique resources, synthetic secrets/data, ownership-checked cleanup; SRE/Security reviewer. | Previous-image rollback is not implemented in this rehearsal. |
| ?? | `scripts/rehearse_workflow_load.py` | Earlier SQLite concurrency sample; **INCLUDE** as diagnostic history. | Synthetic test values only; QA reviewer. | Small sample had three safe 503s at concurrency two; not comparable to PostgreSQL matrix. |

## 4. Deployment and security configuration

| Status | Path | Purpose / release | Security implication and reviewer | Unresolved concern |
|---|---|---|---|---|
| M | `.env.example` | Local Compose template; **INCLUDE**. | Contains names/placeholders only; Security reviewer. Local HTTP and scanning-disabled values must not be used for staging. | Scanner threshold and update count are proposed local values. |
| M | `.gitignore` | Excludes local data, credentials, caches and `.env.*`; **INCLUDE**. | `.env.example` is explicitly retained; Security reviewer. | Owner must keep real evidence/backups out of status. |
| ?? | `.dockerignore` | Excludes secrets/local files from build context; **INCLUDE**. | Excludes `.env.*`, DBs, keys, logs and caches; Container Security reviewer. | Review if new credential/file types are introduced. |
| M | `Dockerfile` | Multi-stage frontend/app image, pinned bases, non-root runtime, hashed production install; **INCLUDE**. | Supply-chain/container hardening; DevSecOps reviewer. | Rebuild against current approved base-image process and scan images in hosted pipeline. |
| M | `docker-compose.yml` | PostgreSQL, app, scanner, Nginx and explicit migration job; **INCLUDE**. | Network, secrets, resource limits and service profiles; Platform/Security reviewer. | Compose is a reference; no approved platform/secret manager exists. |
| ?? | `deploy/nginx/drillloop.conf` | TLS ingress reference; **INCLUDE**. | HSTS, body/rate limits, forwarded headers; Network/Security reviewer. | Certificate, host, TLS policy and ingress mapping are placeholders. Upstream now matches Compose `app`. |
| ?? | `deploy/nginx/drillloop.local.conf` | Loopback local ingress; **INCLUDE**. | HTTP-only; binds locally in the Compose reference; Security reviewer. | Not suitable for organizational exposure. |
| ?? | `scripts/db_recovery.py` | Backup verify and restore only to new DB targets; **INCLUDE**. | Refuses overwrite and protects passwords; DBA/Security reviewer. | Encryption, schedule, restore role, RPO/RTO need decisions. |

## 5. CI configuration

| Status | Path | Purpose / release | Security implication and reviewer | Unresolved concern |
|---|---|---|---|---|
| ?? | `.github/workflows/ci.yml` | Fork-safe PR/push quality workflow; **INCLUDE**. | `pull_request`, read-only token, SHA-pinned actions, disposable test resources; DevSecOps reviewer. | Unpublished and unrun on GitHub; status context and hosted behavior remain unverified. |
| M | `Makefile` | Developer setup/build/test entry points; **INCLUDE**. | Install path now uses hashed dev lock; Engineering/DevSecOps reviewer. | Make commands assume required local tools. |
| M | `pyproject.toml` | Pytest/Ruff configuration; **INCLUDE**. | Quality policy; Python/QA reviewer. | Keep CI arguments aligned with these settings. |

## 6. Dependency manifests and locks

| Status | Path | Purpose / release | Security implication and reviewer | Unresolved concern |
|---|---|---|---|---|
| M | `requirements.txt` | Compatibility entry point to the hashed development lock; **INCLUDE**. | `--require-hashes` dry-run passed; Dependency reviewer. | Keep this wrapper consistent if lock names change. |
| ?? | `requirements-dev.in` | Development dependency inputs; **INCLUDE**. | Human-readable inputs; Dependency reviewer. | Regenerate lock on deliberate dependency changes. |
| ?? | `requirements-dev.lock` | Full hashed test/dev dependency closure; **INCLUDE**. | pip-audit found no known vulnerabilities; Dependency reviewer. | No automated full transitive license allowlist/SBOM gate. |
| ?? | `requirements-prod.in` | Production dependency inputs; **INCLUDE**. | Excludes developer tooling; Dependency reviewer. | Update technical design with approved changes. |
| ?? | `requirements-prod.lock` | Full hashed runtime dependency closure used in image; **INCLUDE**. | Pinned hashes and audited known vulnerability status; Dependency/Container reviewer. | Continue advisory and license review. |

## 7. Documentation

| Status | Path | Purpose / release | Security implication and reviewer | Unresolved concern |
|---|---|---|---|---|
| M | `DEMO_GUIDE.md` | Fictional local demo setup; **INCLUDE**. | Uses temporary storage and fictional labels; Product/QA reviewer. | No real-evidence claim. |
| M | `DRILLLOOP_READER_GUIDE.md` | Plain-language evidence/reviewer guide; **INCLUDE**. | Describes source provenance and human decision state; Product/Evaluation reviewer. | Keep conceptual examples distinct from API schema. |
| M | `DrillLoop_Technical_Design.md` | Architecture, dependencies, licenses and limits; **INCLUDE**. | Records ClamAV GPLv2 and model/library assumptions; Architecture/Legal reviewer. | License record is not a full transitive SBOM. |
| M | `PROGRESS.md` | Implementation and actual Phase 6 verification record; **INCLUDE**. | Reports executed results and limits; Delivery owner reviewer. | Reconcile if later checks change. |
| M | `README.md` | Product scope, install and evaluation limits; **INCLUDE**. | Explicit fictional/unvalidated scope; Product reviewer. | Do not add unsupported accuracy/productivity claims. |
| ?? | `docs/audits/DRILLLOOP_DEMO_RUNBOOK.md` | Reproducible fictional demo and scanner workflow; **INCLUDE**. | Isolation and synthetic data; QA reviewer. | No production approval implied. |
| ?? | `docs/audits/DRILLLOOP_EVIDENCE_QUALITY_REPORT.md` | Open citation-label and evaluation issues; **INCLUDE**. | Preserves unknowns/conflicts; Independent evaluator reviewer. | Alternate citations remain unadjudicated. |
| ?? | `docs/audits/DRILLLOOP_FINAL_RELEASE_GATES.md` | Older gate summary; **EXCLUDE** as superseded by the Phase 6 review and updated go-live gate. | Contains previous release status; Release manager. | Retaining it in the PR would duplicate current gates. |
| ?? | `docs/audits/DRILLLOOP_GITHUB_PR_PREPARATION.md` | Branch, PR, CI and protection steps; **INCLUDE**. | Publication boundary remains explicit; Repository owner/DevSecOps reviewer. | No PR or branch created. |
| ?? | `docs/audits/DRILLLOOP_GO_LIVE_GATE.md` | Updated deployment gate with current local results; **INCLUDE**. | Separates local verification from organizational approvals; SRE/Security reviewer. | Approved staging remains blocked. |
| ?? | `docs/audits/DRILLLOOP_IMPLEMENTATION_PROGRESS.md` | Older Phase 2 implementation snapshot; **EXCLUDE** as stale and superseded. | Contains historical readiness states; Release manager. | Can mislead against current implementation. |
| ?? | `docs/audits/DRILLLOOP_OWNER_DECISIONS.md` | Detailed 17-decision register; **INCLUDE**. | Names owner roles only; Product/Operations reviewer. | No owner decision is made here. |
| ?? | `docs/audits/DRILLLOOP_PENDING_WORK.md` | Older work snapshot; **EXCLUDE** as stale. | Superseded scanner/CI status; Release manager. | Misstates current implementation if published unchanged. |
| ?? | `docs/audits/DRILLLOOP_PHASE5_RELEASE_CANDIDATE.md` | Detailed prior verification plus Phase 6 replay addendum; **INCLUDE**. | Keeps historical/current measurements distinct; QA/SRE reviewer. | Local test data only; rollback not run. |
| ?? | `docs/audits/DRILLLOOP_PHASE6_RELEASE_REVIEW.md` | Final scope/security/verification verdict; **INCLUDE**. | Records findings without secrets; Principal reviewer/Release manager. | Candidate-only scan result must remain current. |
| ?? | `docs/audits/DRILLLOOP_PRODUCTION_CHECKLIST.md` | Older production checklist; **EXCLUDE** as duplicate of the updated gate/handoff. | Previous review state; Release manager. | Keep current checklist as source of truth. |
| ?? | `docs/audits/DRILLLOOP_PRODUCTION_IMPLEMENTATION.md` | Older implementation narrative; **EXCLUDE** as historical and superseded. | Contains old deployment/security status; Release manager. | Would duplicate design and current handoff. |
| ?? | `docs/audits/DRILLLOOP_READINESS_AUDIT.md` | Early MVP audit; **EXCLUDE** as superseded and stale. | Historical gaps no longer describe current code; Release manager. | Could mislead readers. |
| ?? | `docs/audits/DRILLLOOP_SECURITY_RELEASE_REVIEW.md` | Older security snapshot; **EXCLUDE** because this Phase 6 review supersedes it. | Historical remote/config status; Security reviewer. | Keep current remote findings in Phase 6 report. |
| ?? | `docs/audits/DRILLLOOP_STAGING_HANDOFF.md` | Infrastructure, operation and 17 owner decisions; **INCLUDE**. | No providers/policies are invented; Platform/Security/Operations reviewer. | Deployment awaits organizational decisions. |
| ?? | `docs/audits/DRILLLOOP_STAGING_READINESS.md` | Older staging snapshot; **EXCLUDE** as superseded by Phase 5/6 records. | Previous measurements/config; Release manager. | Could contradict current rerun values. |
| ?? | `docs/operations/DEPLOYMENT_AND_RECOVERY.md` | Secret, migration, startup and recovery procedure; **INCLUDE**. | Explicit existing DB protection; DBA/Operations reviewer. | Refresh references if deployment target is selected. |
| M | `scripts/generate_business_review.py` | Editable business review generator; **INCLUDE** as maintained document tooling. | May consume local source assets; Documentation owner reviewer. | Do not include locally supplied proprietary templates/assets. |
| M | `presentation/generate_deck.js` | Product pitch generator with neutral branding and generic image descriptions; **INCLUDE**. | Generates a public-facing presentation; Documentation owner reviewer. | Regenerate only from reviewed source and confirm no local paths enter metadata. |
| M | `scripts/generate_docs.py` | Root-relative document/screenshot generator; **INCLUDE** as maintained document tooling. | Can write generated PDFs/slides; Documentation owner reviewer. | Seven related tracked output artifacts are now included for review. |
| ?? | `docs/audits/DRILLLOOP_RELEASE_FILE_MANIFEST.md` | This path-by-path scope and exclusion record; **INCLUDE**. | Lists only path names and roles, no secret values; Release manager reviewer. | Update count/status if the candidate changes. |
| R | `Product_Concept_Submission_Draft.md` | Neutralized publication copy of the product concept submission; **INCLUDE**. | Historical program labels and personal contact details are omitted; content owner reviewer. | The original path remains in public Git history; this rename does not rewrite history. |

## 8. Generated or temporary files

The release candidate includes these seven tracked publication artifacts, each regenerated or updated from the reviewed source and inspected for visible text, notes, metadata, and structure:

| Status | Path | Purpose / release | Security implication and reviewer | Unresolved concern |
|---|---|---|---|---|
| M | `DrillLoop_Idea_Document.docx` | Editable idea document with neutral labels and approved role/fit wording; **INCLUDE**. | Creator/author fields preserved; content owner reviewer. | Confirm personal attribution is approved for publication. |
| M | `DrillLoop_Idea_Document.pdf` | Idea document publication copy; **INCLUDE**. | Text and PDF properties inspected; content owner reviewer. | Confirm personal author attribution is approved for publication. |
| M | `DrillLoop_Business_Case.pdf` | Commercial hypotheses and neutral public-safety fit wording; **INCLUDE**. | Text and metadata inspected; Product reviewer. | Customer demand and partnerships remain unvalidated hypotheses. |
| M | `DrillLoop_Pitch_Deck.pptx` | Editable 13-slide product pitch with speaker notes; **INCLUDE**. | Neutral labels and generic image descriptions; Documentation/Security reviewer. | Prior public baseline contained local paths; history review remains separate. |
| M | `DrillLoop_Pitch_Deck.pdf` | 13-slide pitch publication copy; **INCLUDE**. | Text, page count, and PDF properties inspected; Documentation reviewer. | Public distribution still needs content-owner approval. |
| M | `DrillLoop_Business_Review.pptx` | Editable 14-slide product and commercial review with speaker notes; **INCLUDE**. | Neutral decision label and notes; content owner reviewer. | External distribution requires explicit content-owner approval. |
| M | `DrillLoop_Business_Review.pdf` | 14-slide review PDF; **INCLUDE**. | Text, page count, and PDF properties inspected; Documentation reviewer. | External distribution requires explicit content-owner approval. |

The frontend build created ignored `frontend/dist/`; it is excluded from Git and was not removed. Temporary migration databases, TLS test keys, ClamAV containers/signature volumes, and PostgreSQL Compose volumes used by the rehearsals were created under unique owner-marked names and cleaned by their harnesses. Do not stage generated build output or temporary test data.

## 9. Database and backup artifacts

No database, dump, backup, or local upload path appears in the changed/untracked candidate. The pre-existing ignored `drillloop.db` and `.pytest-drillloop.db` remain present and must **never** be committed. Their size and SHA-256 fingerprints matched the pre-review snapshot after tests. Keep `*.db`, `*.sqlite*`, `*.dump`, `*.backup`, `backups/`, and `uploads/` excluded. Do not copy a local DB into the release to seed demo data.

## 10. Potential secrets or confidential data

No candidate path is classified as containing an actual credential, private certificate, real exercise record, customer record, or confidential backup. `.env.example` contains template values; test passwords/tokens are synthetic and fixed only for disposable tests. Gitleaks 8.30.1 scanned a private snapshot of the exact 117-file Git index, the staged diff with `gitleaks git --staged`, and extracted text/metadata from nine Office/PDF artifacts in directory mode; all three scans returned zero findings. Reports were redacted and no secret values were printed. This does not certify ignored local data. The Office/PDF extraction covers package text and properties but does not OCR raster images.

Never commit `.env`, `.env.*` except the explicitly reviewed `.env.example`, `secrets/`, private keys/certificates (`*.key`, `*.pem`), databases, backups/dumps, uploads, logs, `.venv/`, `node_modules/`, caches, or `frontend/dist/`. Git and Docker ignore rules cover these local artifacts.

## Release decision summary

- **Proposed included paths:** 90.
- **Excluded but preserved paths:** 9 (`.gitkeep` plus eight superseded audit documents).
- **Changed paths reviewed:** 99.
- **Staging or production approval:** none; see [DRILLLOOP_STAGING_HANDOFF.md](DRILLLOOP_STAGING_HANDOFF.md).
- **GitHub publication:** not performed; see [DRILLLOOP_GITHUB_PR_PREPARATION.md](DRILLLOOP_GITHUB_PR_PREPARATION.md).
