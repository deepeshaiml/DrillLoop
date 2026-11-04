# DrillLoop — Demo Runbook

**Updated:** 4 November 2026 (Phase 5). Use a loopback-only environment with fresh isolated storage and fictional/permitted evidence.

## Readiness paths

| Demo path | Verdict | What was verified |
|---|---|---|
| A. Fictional seeded demo | **READY** | Playwright loaded the synthetic seed, saw five source-linked proposed findings, approved one finding, edited/approved/closed its linked action, downloaded the exercise PDF, refreshed, and confirmed persisted state. All content is fictional. |
| B. Unfamiliar evidence with real frontend/backend/persistence | **READY for the tested regression scenario** | Browser created two separate exercises with five-minute and two-minute objectives, uploaded a newly authored CSV, observed the expected pass and failure, checked source citations, reviewed a finding, completed an action, exported a report, refreshed, switched exercises, and confirmed isolation. This is not a field accuracy evaluation. |
| C. Actual external integration | **NOT READY** | No real external system is identified or connected; no credentials/sandbox were supplied. |
| D. Production-like local rehearsal | **READY for the recorded synthetic scenario** | PostgreSQL 18.6, HTTPS/Nginx and actual ClamAV passed scan-before-analysis, failure/recovery, browser and bounded load checks in a disposable project. This is not approved staging or an organization-approved scanner. |

The word “READY” above means the repeatable local scenario passed. It does not authorize uploading confidential/operational evidence or make production claims.

## Prerequisites

- Python 3.12, Node.js 22.12+ or 24+, npm, and a local Chromium-capable browser.
- Repository root checkout; install dependencies with the commands below.
- No cloud account or external API is used. Optional ASR is not required. The current analysis path does not call an LLM.
- Use a new temporary database for each clean demo run. Never use or reset `drillloop.db`, `.pytest-drillloop.db`, a production database, or a pre-existing Docker volume.

## Configure a local named account and isolated database

From the repository root:

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install --require-hashes -r requirements-dev.lock
npm --prefix frontend ci

export DRILLLOOP_DEMO_DIR="$(mktemp -d /tmp/drillloop-demo.XXXXXX)"
chmod 700 "$DRILLLOOP_DEMO_DIR"
export DATABASE_URL="sqlite:///$DRILLLOOP_DEMO_DIR/demo.sqlite3"
export DRILLLOOP_SESSION_SECRET="$(python3 -c 'import secrets; print(secrets.token_hex(32))')"
export DRILLLOOP_COOKIE_SECURE=0
export DRILLLOOP_ENABLE_DEMO_SEED=1
export DEMO_SEED=0
export DRILLLOOP_PASSWORD_HASH="$(PYTHONPATH=backend .venv/bin/python -m app.auth hash-password)"
```

The password helper prompts without echo. Configure one local administrator account using its returned hash:

```bash
export DRILLLOOP_USERS_JSON="$(DRILLLOOP_PASSWORD_HASH="$DRILLLOOP_PASSWORD_HASH" python3 - <<'PY'
import json, os

print(json.dumps([{
    "id": "local-demo-admin",
    "username": "local-demo-admin",
    "name": "Local Demo Reviewer",
    "role": "admin",
    "organization_id": "local-demo",
    "password_hash": os.environ["DRILLLOOP_PASSWORD_HASH"],
}]))
PY
)"
unset DRILLLOOP_PASSWORD_HASH
```

Migrate this new, empty SQLite database before starting the API:

```bash
PYTHONPATH=backend .venv/bin/alembic upgrade head
PYTHONPATH=backend .venv/bin/alembic current
```

This procedure is for the new temporary file above. Never point it at an existing database without the adoption review and protected backup process in the production implementation report.

This is a local demo account, not an enterprise identity setup. Keep the server on loopback; `DRILLLOOP_COOKIE_SECURE=0` is only for local HTTP testing.

## Start services in order

Start the API in terminal 1:

```bash
PYTHONPATH=backend .venv/bin/uvicorn app.main:app --host 127.0.0.1 --port 8000
```

In terminal 2, confirm database readiness:

```bash
curl -fsS http://127.0.0.1:8000/api/health
```

Expected response contains `"status":"ready"`. The endpoint performs `SELECT 1`; a database failure returns HTTP 503.

Start the Vite client in terminal 2 after the readiness check:

```bash
npm --prefix frontend run dev -- --host 127.0.0.1
```

Open <http://127.0.0.1:5173> and sign in with the username and password used for the configured local user. No user, shared reviewer key, or exercise is created automatically.

## A. Fictional seeded demonstration

After sign-in, use **Load fictional demo**. It is shown only when `DRILLLOOP_ENABLE_DEMO_SEED=1`. Seed data and ground truth are invented; label them fictional in the presentation.

| Step | Presenter action | Expected result | Verification |
|---|---|---|---|
| 1 | Open Overview. | `Night Shift: Extended Power Loss`, three sources, source-linked observations, five proposed findings. | Confirm filename and source locators; explain the exercise is synthetic. |
| 2 | Open Timeline and Findings. | Fictional event times and the seed’s unresolved timing discrepancy remain visible. Findings stay proposed. | Open at least one source link; confirm exact source ID, locator, and wording. |
| 3 | Approve or reject one finding while signed in. | Decision is recorded with the configured account name. | Confirm the status and reviewer attribution in the card/audit response. |
| 4 | Open its linked action and edit the action title, owner, due date, and acceptance criteria as explicit fictional demo values. | Proposed action fields update; analysis did not generate an owner or deadline. | Save and refresh; confirm the values persist. |
| 5 | Approve the action after the linked finding and required fields are approved/present. Enter clearly fictional closure evidence. | Action transitions to closed. | Explain that DrillLoop records the entered closure text; it does not verify the real-world work. |
| 6 | Export the report. | `HOSP-PO-2026-01-AAR-IP.pdf` downloads. | Open it and confirm report is exercise-specific and still a review document. |

## B. Unfamiliar-evidence browser regression

The automated browser path lives at `frontend/e2e/live-workflow.mjs`. It must target the fresh disposable database configured above. Run it from `frontend/`:

```bash
DRILLLOOP_E2E_USERNAME=local-demo-admin \
DRILLLOOP_E2E_PASSWORD='the-password-entered-for-the-test-account' \
node e2e/live-workflow.mjs
```

On a clean database the script also checks the fictional seed. It creates two new exercises with different thresholds, uploads one unfamiliar CSV with events at 14:00 and 14:04, verifies five-minute success and two-minute failure, follows source citations, approves a finding, edits and closes a corrective action, exports the exercise report, refreshes, switches exercises, and checks persistence. It asserts no browser page errors. This has passed locally against temporary SQLite; it does not establish accuracy on real evidence.

The backend regression suite includes invalid `99:99`, missing objectives, unsupported rules, missing completion, boundary thresholds, out-of-order rows, contradictory timestamps/required-field statements, access-denied requests, and database-readiness failure.

## Safe reset and repeat

Stop the API with Ctrl-C. For a clean repeat, create a **new** unique temporary directory and change `DATABASE_URL` to a new filename that does not exist. Do not remove or overwrite an old temp database if its contents may be useful. Do not use any existing repository or user database.

The pytest fixture creates and owns a separate temporary database per test; run tests only with `DATABASE_URL` unset:

```bash
unset DATABASE_URL
.venv/bin/pytest -q
```

The fixture refuses caller-supplied database URLs and rejects targets outside its owner-marked temporary directory. The historical audit did reset `.pytest-drillloop.db`; that past data loss is not reversible. Remediation runs do not target that file and its fingerprint has remained unchanged during this remediation.

## Docker Compose alternative

`.env.example` contains paths but no demo account/password. Create mode-0600 database password, session secret, and users JSON files inside a private directory; set the matching `*_FILE` values in `.env`, keep `DEMO_SEED=0`, and use a fresh Compose project with a new volume. Before starting the app, run:

```bash
docker compose up --build --wait db
docker compose --profile maintenance run --build --rm migrate
docker compose up --build --wait
```

PostgreSQL 18 mounts at `/var/lib/postgresql`; the app health check waits for a working database connection. The migration step intentionally applies DDL: run it only against a new volume here, or after an owner-approved upgrade plan and isolated populated-copy rehearsal. Existing Compose volumes were not inspected, migrated, deleted, or reset. Never use `down -v` against existing resources.

## D. Production-like local rehearsal

For the full scanner-enabled local rehearsal, use the isolated harness rather than reusing the demo database above. It creates a uniquely named project, PostgreSQL and ClamAV signature volumes, random loopback ports, TLS test certificate, and synthetic identities, then removes only resources carrying its ownership label:

```bash
.venv/bin/python scripts/rehearse_staging.py
```

It requires Docker Compose, a local browser runtime and the project dependencies. The harness exercises migrations, clean CSV/PDF, EICAR, malformed input, scanner timeout/outage/restart, browser review/action/PDF flow, concurrency, app/database restart and restore to a new database. It preserves unrelated containers, volumes, databases and files. To run only the actual ClamAV API integration test in its own disposable container:

```bash
.venv/bin/python scripts/rehearse_clamav_integration.py
```

The local Compose scanner has no published ClamD port. The 72-hour freshness limit and four daily update checks are proposed values; obtain Security Operations approval before organizational deployment. See [Phase 5 release-candidate results](DRILLLOOP_PHASE5_RELEASE_CANDIDATE.md) for actual outcomes and limits.

## Troubleshooting

| Symptom | Check |
|---|---|
| Sign-in says authentication is not configured | Confirm `DRILLLOOP_USERS_JSON` is a JSON array with a scrypt hash and `DRILLLOOP_SESSION_SECRET` is at least 32 bytes. Restart the API after changing them. |
| Login rejected | Confirm username/password and hash correspond. There is no default login or shared key. |
| CSRF 403 | Refresh the browser session and retry; frontend must retain the current session token. |
| Fictional seed button is missing | Confirm signed-in role is admin/evaluator and `DRILLLOOP_ENABLE_DEMO_SEED=1`. |
| Health returns 503 | Check database URL, permissions, PostgreSQL readiness, and API logs. Response omits database connection details. |
| `99:99` CSV upload fails | Expected controlled HTTP 400 with `INVALID_TIMESTAMP`; correct the source before uploading. |
| Upload rejected | Supported types: UTF-8 TXT/MD/LOG, CSV, JSON event/transcript, selectable-text PDF; 15 MB/file, 10 files and 30 MB/batch. |
| Scanner not ready or upload gets `SCANNER_UNAVAILABLE` | Required scan mode is fail closed. Check private scanner service health, ClamD capability, signature freshness and app logs; do not bypass scanning to retry. |
| Upload gets `PARSER_CAPACITY_EXHAUSTED` | No files were imported. Wait for the response's `Retry-After` interval, then retry once; do not rapidly resubmit. Queue size and wait time are bounded. |
| Audio says model unavailable | Expected unless faster-whisper is installed and `WHISPER_MODEL_PATH` points to an already staged local model. No model download occurs. |
| Compose fails to start | Replace every `.env` placeholder; inspect only the unique test project you started. Never use `down -v` on existing resources. |

## C. Actual external integration

**NOT READY.** The product requirements do not name an external system, API contract, sandbox, or credential. Obtain those prerequisites before implementing or claiming a real connector. No real transaction or confidential record was used in this verification.
