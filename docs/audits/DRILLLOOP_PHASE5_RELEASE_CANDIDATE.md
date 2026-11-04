# DrillLoop Phase 5 — Release Candidate Assessment

**Updated:** 4 November 2026
**Scope:** ClamAV deployment integration, bounded upload admission, local PostgreSQL/scanner browser rehearsal, and release preparation. All test evidence is synthetic and local.

## Result

The two locally actionable blockers are fixed for the tested workload. The optional Compose scanner service is operational with required-mode fail-closed uploads. Parser admission now waits in a bounded FIFO queue and returns a retryable capacity response only after the queue or wait limit is reached. A production-like local browser workflow and an 80-workflow PostgreSQL+ClamAV load matrix passed.

This is a locally reviewable release candidate, not an approved staging deployment or production approval. The ClamAV service, image, license, signature age and update schedule still need organization approval. No commit, push, pull request, hosted CI run or external deployment occurred.

## Implementation

### Scanner deployment and upload path

- Added the optional `scanner` Compose profile with the official ClamAV Debian image pinned to version 1.5.4 and digest `sha256:c21aa18cc0a358678255a3dfb343a4555b58f71b97d7b869df8fdf7ea0a5b4b1`. ClamAV licensing is GPLv2 and needs legal/security review before organizational use. See the [official container documentation](https://docs.clamav.net/manual/Installing/Docker.html).
- Scanner TCP port 3310 has no host binding. ClamAV shares a private container network with DrillLoop, has a separate outbound bridge for signature updates, persists `/var/lib/clamav` in its own volume, disables `clamav-milter`, and is capped at 2 CPU and 5 GiB. `FRESHCLAM_CHECKS=4` configures four update checks per day.
- The app streams files through ClamD `INSTREAM`, checks `PING` and `VERSION`, parses the signature database timestamp, and requires signatures to be no older than the configured threshold. Readiness also performs a clean synthetic scan and EICAR detection check. The ClamD protocol has no authentication or transport encryption, so the reference keeps it inside the trusted private network; see the [ClamD protocol documentation](https://docs.clamav.net/manual/Usage/ClamdProtocol.html).
- The configured 72-hour signature-age limit is a **proposed local value**, not an approved security policy. Stale or unverifiable signature data makes readiness fail and required-mode uploads fail closed. The app image does not contain ClamAV; the service is a separate optional deployment component.
- Scan and upload decisions log the result, scanner version, signature timestamp, duration, source ID or rejection code. Private per-job quarantine files are removed after success, rejection, timeout, cancellation or parser failure; the staging quarantine was empty after the checks.
- Upload batches are persisted only after every file passes scan and extraction. A retry after a capacity 503 cannot create a partial batch or duplicate evidence. Existing file type, size, count and extraction limits remain in force.

### Concurrent upload reliability

**Root cause:** the previous implementation used one non-blocking parser permit. A request arriving while the single worker was occupied immediately received `503 PARSER_CAPACITY_EXHAUSTED`, even when the parser would become available shortly. That caused three of five concurrent-two workflows to fail in the prior SQLite/scanning-disabled sample.

**Fix:** one isolated parser worker remains the active limit; up to eight waiting jobs are admitted FIFO, with a default 30-second bounded wait. A full queue or expired wait returns HTTP 503, `Retry-After: 2`, and a user-facing “no files were imported; wait and retry” message. Parser work remains capped by child-process CPU/memory/time limits. Cancellation terminates the child and cleans its quarantine directory. Metrics expose active workers, waiting and peak queue depth, rejections, queue wait, processing time, and scan duration/outcome.

Repeated analysis and uploads were checked for duplicate findings, actions and source records. The load script retries only safe edge 429 responses that include `Retry-After`, and upload capacity 503s only where no records were persisted. There were no parser-admission rejections in the Phase 5 matrix.

## Production-like local rehearsal

Command: `.venv/bin/python scripts/rehearse_staging.py`
Disposable project: `drillloop-staging-64c9d87abd`; image ID: `sha256:92743d3f59557be3bef208aefcc915abc813ecb8cff10c8b58b0d6b7edb45397`.

The harness created a fresh PostgreSQL 18.6 volume, pinned ClamAV service and signature volume, file-injected test identities/secrets, random loopback HTTPS ports, and a short-lived self-signed certificate. It explicitly applied and checked Alembic migrations. The completed browser path verified secure login, exercise/objective creation, clean-scanned evidence extraction, objective analysis and citations, human finding review, corrective-action approval/closure, PDF export, refresh/resume, exercise switching, access grant/revoke and same-organization cross-user denial. There were no browser errors. This checks the local flow; it does not establish independent evaluation accuracy.

| Scanner/workflow check | Result |
|---|---|
| App readiness | PASS: `PING`, parseable/current `VERSION`, clean scan and EICAR scan verified. Signature database age 50.1 hours at rehearsal time; configured maximum 72 hours. |
| Clean CSV and selectable-text PDF | PASS: each accepted with `scan_status=clean`. |
| EICAR fixture | PASS: rejected with 422 `MALWARE_REJECTED`; no source or extracted observation was created. |
| Invalid timestamp file | PASS: rejected with 400 `INVALID_TIMESTAMP` after clean scan; no source was created. |
| Scanner timeout and outage | PASS: timeout and stopped-service upload returned safe 503 responses, created no source/timeline data, and produced audit/metrics records. |
| Scanner recovery/restart | PASS: scanner restart after timeout and outage recovered live readiness while reusing its signature volume. |
| Audit and quarantine | PASS: accepted and rejected events included scan provenance; quarantine was empty after processing. |
| Scanner network/resource config | PASS: no host port binding; signature volume persisted during the rehearsal; 5 GiB cap applied. |
| PostgreSQL/app restart | PASS: readiness and persisted records recovered. |
| Backup/restore | PASS: a 93,713-byte PostgreSQL archive restored to a new disposable DB; 84/84 exercise rows matched. |
| Previous-image rollback | NOT RUN: no prior compatible image was supplied. |

The successful uploads used the actual local ClamAV engine `1.5.4/28172`, database timestamp `2026-11-02 06:24:10 UTC`. This is a working local scanner deployment, not an organization-approved production scanner.

## PostgreSQL + ClamAV load results

Command, invoked by the staging harness: `scripts/rehearse_phase5_load.py --workflows-per-level 20 --max-concurrency 10`. Each synthetic workflow used its own exercise and performed login, create, upload/scan/extract, analysis twice, finding review, action update/review/closure and PDF export. Each completed workflow had exactly one clean source, finding and action with a citation. The 20 attempts at each level provide descriptive p95s for operations with 20 or more samples; p99 is not reported.

| Concurrent workflows | Completed | Workflow throughput | Elapsed per level |
|---:|---:|---:|---:|
| 1 | 20/20 | 0.792 workflows/s | 25.238 s |
| 2 | 20/20 | 0.758 workflows/s | 26.395 s |
| 5 | 20/20 | 0.774 workflows/s | 25.833 s |
| 10 | 20/20 | 0.758 workflows/s | 26.374 s |

Descriptive per-operation p50/p95 latency in milliseconds (each cell is `p50 / p95`; login has 40 samples, analysis has 60, and the other operations have 20):

| Operation | C1 | C2 | C5 | C10 |
|---|---:|---:|---:|---:|
| Login/session | 34 / 75 | 37 / 150 | 79 / 2,009 | 116 / 2,076 |
| Exercise create | 8 / 2,022 | 9 / 21 | 38 / 2,027 | 159 / 2,021 |
| Upload, scan, extract | 275 / 327 | 358 / 524 | 480 / 2,761 | 1,978 / 3,987 |
| Analysis | 9 / 17 | 10 / 2,015 | 14 / 2,025 | 11 / 2,025 |
| Finding review | 9 / 16 | 9 / 11 | 16 / 2,028 | 9 / 2,016 |
| Action update | 8 / 12 | 9 / 21 | 16 / 2,015 | 10 / 2,018 |
| Action review | 9 / 2,017 | 10 / 2,012 | 14 / 2,028 | 1,019 / 2,025 |
| Action close | 8 / 15 | 9 / 2,021 | 13 / 2,016 | 9 / 2,019 |
| PDF export | 14 / 23 | 15 / 2,024 | 19 / 2,019 | 14 / 4,045 |

The 2-second ingress `Retry-After` contributes to the high tail values. The configured Nginx 10-request/second rate limit returned 175 structured 429 responses; all 175 were retried within the bounded policy. There were zero unexpected HTTP 5xx, zero parser-capacity 503s, zero other upload rejections and no incomplete workflows. The queue reached its bound of eight waiters, with 82 queue observations averaging 0.173 seconds and zero admission rejections. Scanner operation metrics recorded 82 clean scans averaging 11.8 ms.

Sampled container peaks at 0.5-second intervals: app CPU 98.4% and memory 116.1 MiB; ClamAV CPU 1.2% and memory 992.6 MiB; PostgreSQL CPU 4.2% and memory 54.2 MiB; ingress CPU 4.0% and memory 21.3 MiB. These are measurements from one developer machine. The matrix confirms safe completion under the tested request rate; it does not establish production capacity or owner-approved latency targets.

The Phase 5 brief cites a prior **30% failed-workflow** observation at concurrency two. The retained reproducible Phase 4 run record (`scripts/rehearse_workflow_load.py --workflows-per-level 5 --max-concurrency 2`) instead reports 2/5 completed workflows and three upload 503s, which is 3/5 failures in that five-workflow sample. The source records therefore have a denominator mismatch; the reported 30% and the detailed 2/5 run are not treated as the same measurement. Phase 5 completed 20/20 at concurrency two with zero parser 503s, plus 20/20 at concurrency 1, 5 and 10. Throughput is not directly comparable: the earlier repeat used SQLite, five workflows and scanning disabled; this matrix used PostgreSQL, HTTPS, real scanning, 20 workflows per level and ingress throttling.

## Regression and release checks

| Check | Actual result |
|---|---|
| `env -u DATABASE_URL .venv/bin/pytest -q` | **85 passed, 1 skipped**, one existing Starlette/httpx deprecation warning. The skipped optional integration test was run separately against actual ClamAV below. |
| `.venv/bin/python scripts/rehearse_clamav_integration.py` | **1 passed** against the pinned official image, published only to a loopback host port in a separate disposable test container; owned container and signature volume were removed. |
| `.venv/bin/ruff check backend scripts && .venv/bin/ruff format --check backend scripts` | **PASS**; 40 files formatted. |
| `npm --prefix frontend run build` | **PASS**; TypeScript and Vite production build completed. |
| `npm --prefix frontend audit --audit-level=high` | **PASS**; zero known vulnerabilities. |
| `uv tool run --from pip-audit pip-audit -r requirements-dev.lock` | **PASS**; no known vulnerabilities. |
| `docker compose --profile scanner --env-file .env.example config --quiet` | **PASS**. The staging rehearsal also built the app image and validated the Nginx TLS configuration. |
| `git diff --check` | **PASS**. |
| `.github/workflows/ci.yml` Ruby YAML parse and `actionlint` in `rhysd/actionlint:latest` | **PASS** after resolving ShellCheck warnings; this is local static validation only. |
| Local Gitleaks 8.30.1 on the non-ignored Git candidate file snapshot | **PASS**; 1.27 MB scanned, no leaks found. Existing ignored local databases and caches were not scanned or included. |
| `scripts/evaluate_analysis.py` primary fictional dataset with Phase 4 baseline | **PASS**; 5/5 findings, 21/21 observations, all 9/9 canonical citations recovered, zero regression metric deltas. Seven unlabeled alternate citations remain for evaluator review, so citation precision and unsupported rate remain undefined. OBJ-02 cites rows 4 and 5 and retains its timing conflict. |
| Five-minute threshold regression | **PASS** in backend regressions and browser flow: 14:00–14:04 is success at five minutes and failure at two minutes. No evidence labels were changed for this run. |

The primary evaluation remains a small, developer-authored fictional fixture. No independent real-evidence validation is claimed. The normal backend suite skips the optional external-scanner test because production Compose keeps ClamD private; `rehearse_clamav_integration.py` separately ran that test against the real scanner on loopback.

## Git and hosted CI

The worktree remains on `main` and dirty: 85 non-ignored modified/untracked paths at final inspection, including prior Phase 3/4 changes. The existing scope cannot be safely split into a Phase 5-only release by `git diff` alone; every candidate path needs owner/reviewer inspection. No changes were staged, committed, pushed or sent to a remote. `.gitignore` and `.dockerignore` exclude `.env`, secrets, databases, SQLite files, backup archives, private keys and local build/cache files. The pre-existing ignored `drillloop.db` and `.pytest-drillloop.db` were preserved and not included in the release candidate; there was no local `.env` file. Gitleaks found no secrets in the non-ignored candidate snapshot.

`.github/workflows/ci.yml` is only in the local worktree. Hosted CI is **BLOCKED pending reviewed publication**. The prior Phase 4 read-only GitHub check found no remote workflow or effective `main` branch protection; Phase 5 made no remote changes and no hosted run occurred.

To publish after owner approval:

1. Have the repository owner/release manager review the complete 85-path worktree, preserve unrelated approved changes, and identify the exact release scope.
2. Obtain explicit authorization to create a release branch from the approved base and stage only the reviewed paths; inspect `git diff --cached`, run the recorded local gates, and create the reviewed commit.
3. Obtain explicit authorization to publish that branch and open a pull request; publish only to the owner-approved repository and branch.
4. Run hosted Actions on the PR and trusted branch; investigate failures and confirm fork/untrusted PR secret isolation.
5. Repository owner/DevSecOps configures required review, required CI checks and branch protections; verify they apply to the intended branch.
6. Merge only through the approved review and merge process. No merge, tag or deployment is part of this assessment.

## Remaining owner decisions and independent verification

- Approve the ClamAV vendor/image, GPLv2 use, signature provenance/update egress, signature freshness limit, quarantine retention/release and scanner operations. The local 72-hour limit/four daily FreshClam checks are proposed values only.
- Select staging host, TLS/DNS, secret management, identity provider/MFA, evidence classification, retention/deletion, backup encryption, RPO/RTO, monitoring, incident owner and release authority.
- Set expected workload, evidence sizes, ingress rate, latency and availability targets before judging capacity. Repeat with adequate samples in approved staging and measure the approved platform.
- Run hosted CI on a reviewed PR and configure branch protections.
- Complete independent evidence adjudication, security/threat-model/penetration assessment, and accessibility review. Supply a prior compatible image for rollback rehearsal.
- Select an external integration target and contract before claiming an external-integration demo.

| Scope | Verdict | Boundary |
|---|---|---|
| Local demo | **READY** | Synthetic evidence, local identities and isolated data only. |
| Production-like local deployment | **READY** | The tested PostgreSQL 18.6 + HTTPS/Nginx + pinned ClamAV setup passed locally; signature-age value is proposed and the scanner is not organization-approved. |
| Approved staging environment | **NOT READY** | No approved or externally hosted staging, operator sign-off or organization scanner decision. |
| Real external-integration demo | **NOT READY** | No external system, API contract or sandbox was selected. |
| Production release | **NOT READY** | Owner approvals, hosted CI/branch protection, independent reviews, operational targets and rollback evidence remain outstanding. |

## Phase 6 reproduction addendum — 4 November 2026

The Phase 6 review reran the PostgreSQL + HTTPS/Nginx + ClamAV rehearsal in new owned Compose projects. The first run found **80/80 workflows completed** across concurrency 1/2/5/10, with one bounded parser-capacity HTTP 503 safely retried before persistence, 180 ingress 429 responses safely retried, and zero unexpected 5xx responses. The prior Phase 5 run's “zero parser-capacity 503” result remains the recorded result for that earlier run; one safe rejection appeared in this first later replay.

After correcting the TLS Nginx upstream to match the Compose `app` service and removing the rehearsal's upstream rewrite, a second run passed against the checked-in config: **80/80 workflows completed**, zero parser-capacity 503s, 181 ingress 429 responses safely retried, and zero unexpected 5xx responses. The one safe 503 in the preceding replay and zero in this replay show normal variation around a bounded queue; neither run had an incomplete workflow or duplicate persisted records. Do not generalize this small local matrix into production capacity.

Phase 6 also separately reran the actual ClamAV integration test (**1 passed**, owned test container and signature volume cleaned), reran the backend suite after a runtime-config regression fix (**86 passed, 1 skipped**), rebuilt the frontend, reran Python and npm dependency audits, ran Ruff, checked fresh SQLite and PostgreSQL migration consistency, validated Compose and the CI YAML, and passed `git diff --check`. The complete release review and final snapshot details are in [DRILLLOOP_PHASE6_RELEASE_REVIEW.md](DRILLLOOP_PHASE6_RELEASE_REVIEW.md). These checks remain local synthetic verification, not approved staging.

After the runtime-config change, the latest captured rehearsal against the checked-in source also passed: **80/80 workflows**, one safe parser-capacity 503 retried before persistence, 173 ingress 429s safely retried, zero unexpected 5xx, no browser errors, and 84/84 exercise rows restored into a new disposable database. Clean and EICAR scanner capability, invalid-file handling, timeout/outage fail-closed behavior, audit, quarantine cleanup, app/database restart, and recovery passed. The signature database was 51.98 hours old under the proposed, unapproved 72-hour setting. The runner reported no cleanup error and the owned Compose project was absent after completion. This is the third retained passing result; an intervening invocation's output was truncated and its result remains unverified. None of these runs is approved staging evidence.
