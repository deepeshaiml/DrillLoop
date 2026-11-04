# DrillLoop Demo Guide

## What is verified

The packaged **Night Shift: Extended Power Loss** exercise is fictional. It is available only when demo seeding is enabled and a signed-in editor selects **Load fictional demo**. It demonstrates source-linked observations, five proposed findings, human review, corrective actions, and PDF export. Do not present its facts or labels as real exercise outcomes.

The frontend, API, SQLite/PostgreSQL persistence, named-user session, and deterministic analysis were also exercised in a browser with new fictional CSV evidence. One exercise had a five-minute threshold and a 14:00–14:04 interval (confirmed success); another had a two-minute threshold with the same evidence (confirmed failure). The browser run reviewed and approved the finding, assigned action fields, approved and closed the action with entered closure evidence, exported a report, refreshed, switched exercises, and confirmed state persisted. This was a controlled regression scenario, not independent evaluation on real exercise material.

## Start with a fresh local database

Use Python 3.12, Node.js 22.12+ or 24+, npm, and a local browser. From the repository root:

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
```

Apply the initial schema to this newly created temporary database before starting the API:

```bash
PYTHONPATH=backend .venv/bin/alembic upgrade head
PYTHONPATH=backend .venv/bin/alembic current
```

Create a password hash. The helper prompts for a password and does not echo it:

```bash
export DRILLLOOP_PASSWORD_HASH="$(PYTHONPATH=backend .venv/bin/python -m app.auth hash-password)"
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

The local admin role can create exercises, upload evidence, analyze, and review. This is a local demonstration account, not enterprise identity or production account provisioning. Keep both services bound to loopback and use fictional or otherwise permitted evidence.

Start the backend in one terminal:

```bash
PYTHONPATH=backend .venv/bin/uvicorn app.main:app --host 127.0.0.1 --port 8000
```

Confirm readiness. The health endpoint checks the configured database:

```bash
curl -fsS http://127.0.0.1:8000/api/health
```

Start Vite in a second terminal:

```bash
npm --prefix frontend run dev -- --host 127.0.0.1
```

Open <http://127.0.0.1:5173>, sign in with the configured username and password, and create or seed an exercise. The API does not create an account or seed data automatically. `DEMO_SEED` stays `0`; the explicit synthetic seeding endpoint is enabled by `DRILLLOOP_ENABLE_DEMO_SEED=1`.

## Five-minute fictional walkthrough

1. Select **Load fictional demo**. Confirm the exercise is labeled fictional and that candidate findings remain proposed.
2. Open Timeline and Findings. Follow the source ID and exact row, note, or segment locators; explain that the rule engine does not certify the conclusion.
3. Review a finding as the signed-in admin or reviewer. The audit actor comes from the authenticated account; the browser cannot choose a reviewer name.
4. In Corrective actions, assign an owner and due date only as an explicit human-entered demo value. Approve the linked finding first, then approve the action.
5. Enter clearly fictional closure evidence and close the action. DrillLoop records that text; it does not verify the real-world completion.
6. Export the PDF and confirm that findings, source links, interpretations, decisions, and actions are exercise-specific.

The supplied seed is not a real-integrated demo. Its records, people, events, and labels are synthetic.

## Repeatable browser regression with unfamiliar evidence

The regression script uses Playwright and Chromium. It expects the fresh local server/database above and will create uniquely named exercises in that database. From `frontend/`:

```bash
DRILLLOOP_E2E_USERNAME=local-demo-admin \
DRILLLOOP_E2E_PASSWORD='the-password-entered-for-the-test-account' \
node e2e/live-workflow.mjs
```

On a fresh database it also loads the fictional seed and asserts five rendered source-linked proposals. It then creates two exercises with different objective thresholds, uploads the same unfamiliar CSV, checks a pass and a failure, reviews a cited finding, completes an action lifecycle, downloads a PDF, refreshes, and switches exercises. The script must point only at the disposable local database selected in `DATABASE_URL`; choose a new temporary directory for a clean rerun.

## Safe reset and tests

To repeat the demonstration from a clean state, stop the API and create a new unique temporary directory and database URL. Leave the prior database intact if its records might be needed. Never reset or reuse `drillloop.db`, `.pytest-drillloop.db`, or another existing database.

Tests create unique databases inside a temporary directory owned by the pytest process. The fixture fails before tests start if `DATABASE_URL` is already set. Run tests only with that variable unset:

```bash
unset DATABASE_URL
.venv/bin/pytest -q
```

Do not run tests against a demo or deployment database.

## Supported evidence and known limitations

- Supported inputs: UTF-8 TXT/MD/LOG, CSV, JSON event/transcript records, and selectable-text PDFs. OCR is not implemented.
- File limit is 15 MB each, ten files and 30 MB aggregate per upload batch; structured evidence is limited to 10,000 rows/segments; PDFs are limited to 250 pages and 2 million extracted characters.
- Parser timeouts/process isolation and an ingress-level request-body limit are not implemented. Do not expose the upload endpoint to untrusted networks.
- Deterministic analysis supports explicitly configured elapsed-time, reported-duration, event-presence, and required-field rules. Phrase matching is exact substring logic and needs evaluator-authored rule terms. Ambiguous, missing, or conflicting evidence remains in a needs-review/unknown state.
- Objectives lock after analysis begins so findings and prior decisions cannot silently become stale. Start a new exercise to change post-analysis objectives.
- Owners and due dates are not inferred by analysis; reviewers/editors enter them explicitly.
- Local named-user passwords are configured in environment JSON. No enterprise identity provider is selected, no invitation directory exists, and session revocation requires secret rotation; production needs an approved identity and session strategy.
- No external incident-management, hospital, document, or messaging connector is defined or implemented. No vendor endpoint or credential is assumed.
- The current analysis does not invoke an LLM. Optional local ASR can be configured only with the package and a local model directory; it has no diarization and has not been measured on real audio.
- No real or confidential exercise evidence has been authorized or evaluated here.

## Docker Compose

Compose uses PostgreSQL 18.6 at `/var/lib/postgresql`, waits for database health, and includes an application readiness probe that checks `SELECT 1`. Create `.env` from `.env.example`, replace all placeholders with unique local secrets and a properly configured `DRILLLOOP_USERS_JSON`, then run `docker compose up --build --wait`. The isolated Compose run used disposable resources and verified authentication, upload, deterministic analysis, and persistence across an app-container restart. Do not run Compose against an existing volume without backing it up and reviewing a migration plan.

## Real integrations and production

**Real external-integration demo: NOT READY. Production: NOT READY.** No real external system has been named, configured, or exercised. The local demo has no enterprise identity provider, migration framework, backup/restore or retention procedure, managed secret service, TLS/ingress policy, CI/CD, monitoring/alerts, load tests, operational owner, or deployment rollback rehearsal. Use the updated audit backlog and production checklist before claiming production readiness.
