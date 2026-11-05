# DrillLoop container deployment and recovery reference

**Scope:** generic self-hosted container foundation, not a production deployment. No hosting provider, TLS operator, evidence classification, retention rule, identity provider, RPO, or RTO has been selected.

**Phase 5 local rehearsal:** `.venv/bin/python scripts/rehearse_staging.py` passed a production-like local workflow with PostgreSQL 18.6, HTTPS/Nginx and actual ClamAV 1.5.4, including scanner failure/restart, concurrency, app/database restart and restore to a new DB. Previous-image rollback was **NOT RUN**. This is not an approved staging deployment or an organization-approved scanner. See `docs/audits/DRILLLOOP_PHASE5_RELEASE_CANDIDATE.md` for results and limitations.

## Release preparation

1. Build the image from a reviewed source revision and record the Git revision in `DRILLLOOP_BUILD_REVISION`; set `DRILLLOOP_BUILD_VERSION` to the release tag. `Dockerfile` pins the base image tags, installs the hash-locked production dependency set, builds the frontend in a separate stage, and runs as UID 10001.
2. Provision PostgreSQL 18 or a compatible supported PostgreSQL service, private persistent storage, encrypted backups, private secret delivery, network policy, TLS ingress, monitoring, and named-user configuration under accountable operators.
3. Create private files for database password, session signing secret, and the configured user JSON. Restrict them to the application operator/runtime. Use an independently generated session secret of at least 32 bytes, unique password hashes, and a tested rotation/revocation plan. Do not put secrets in `.env`, image layers, Git, command arguments, or logs.
4. Set `DRILLLOOP_ENVIRONMENT=production`, `DRILLLOOP_COOKIE_SECURE=1`, `DRILLLOOP_UPLOAD_SCAN_MODE=required`, explicit `DRILLLOOP_TRUSTED_HOSTS`, and `DEMO_SEED=0`. Production config fails closed unless it has PostgreSQL, file-injected credentials, configured users, secure cookies, a trusted-host allowlist, and a scanner boundary. The optional `scanner` Compose profile provides a separate ClamAV service; it is not included in the app image and remains subject to organizational image/license/signature-policy approval. The supplied 72-hour signature-age threshold and four daily FreshClam checks are local proposed values only.
5. Put the app on a private network with PostgreSQL. Compose attaches only the unprivileged Nginx ingress to the loopback-published edge network; the app and database stay on the internal network. `deploy/nginx/drillloop.local.conf` is HTTP-only and loopback-only for local demos. Expose only a TLS ingress for a staging/production network. The `deploy/nginx/drillloop.conf` reference listens on unprivileged container ports **8080 (HTTP redirect) and 8443 (HTTPS)**. The platform must map its approved 80/443 ingress ports to those container ports or adapt the reference; it has placeholder host/certificate paths and is not a ready-to-use TLS deployment. Set trusted hosts to the actual ingress hostname. Configure CORS only if a separate approved UI origin is used.

## Scanner and upload operations

The optional Compose `scanner` profile uses the digest-pinned official ClamAV Debian image. Start it only in the approved local/test boundary with `docker compose --profile scanner up --build --wait`; keep `DRILLLOOP_UPLOAD_SCAN_MODE=required` for staging/production. The ClamD port is not published on the host. ClamD does not provide transport authentication/encryption, so allow access only from the trusted private app/scanner network; keep signature-update egress restricted to approved update sources.

The scanner persists its signature database in `clamav-signatures`, runs controlled FreshClam checks, and has a health check. Docker health alone is insufficient: `/api/ready` also verifies a parseable/current signature timestamp plus clean and EICAR scan capability. A local rehearsal value of 72 hours maximum age and four FreshClam checks per day is **not approved policy**; Security Operations sets the production threshold/update schedule and alerts. Required-mode uploads fail closed for scanner timeout, outage, stale/unknown signatures and malicious verdicts. Accepted/rejected attempts retain scan version, timestamp, status and timing in logs/audit. Per-job quarantine is private tmpfs and is cleaned after each processing decision; it is not a malware-retention/release workflow.

Parser admission uses one bounded isolated worker and at most eight FIFO waiters by default. `DRILLLOOP_PARSER_QUEUE_TIMEOUT_SECONDS` controls wait time (validated range 1–120 seconds). Saturation returns 503 with `Retry-After: 2`; the response states no files were imported. The Nginx request-rate limiter returns structured 429 with retry guidance. Repeated 503/429, queue depth, parser duration and scanner duration should be reviewed through protected `/api/metrics`; do not raise concurrency/resource limits without owner workload targets and a repeated PostgreSQL/scanner matrix.

## Fresh install and upgrade sequence

The normal app startup checks the Alembic revision and the ORM schema and refuses an unversioned, behind-head, or drifted database. It never runs DDL. The `migrate` Compose service is maintenance-profile-only and requires an explicit operator command.

1. For a new database, verify PostgreSQL health, create the database/role, verify secret delivery, take a pre-migration backup (empty for a new DB), and run `docker compose --profile maintenance run --rm migrate`.
2. Run `alembic heads`, `alembic current`, and `alembic check` against the intended database; retain command output and DB identity in the change record.
3. Deploy the app image, wait for `/api/ready`, then run smoke checks for login, an authorized exercise read, source access boundaries, and report export in the approved staging environment.
4. Existing unversioned databases remain a gated DBA task; follow the adoption status in `docs/audits/DRILLLOOP_GO_LIVE_GATE.md` and the migration safeguards in `docs/audits/DRILLLOOP_STAGING_HANDOFF.md`. Never point the migration container at an existing volume before a protected backup, schema/data inspection, owner approval, and rehearsal on an isolated copy. Do not stamp automatically.

## Backup and recovery

`scripts/db_recovery.py` supports on-disk SQLite backup and PostgreSQL custom archives using native `pg_dump`, `pg_restore`, and `createdb`. It verifies SQLite integrity or PostgreSQL archive readability, confirms target names, refuses overwrite, and restores only to a new target. Keep backups outside the app container in private encrypted storage. This utility does not select backup frequency, retention/deletion, encryption key ownership, or legal hold.

PostgreSQL command-line tools must be installed on the operator host. Keep credentials out of URL command arguments; supply the database password through `DATABASE_PASSWORD_FILE`/`PGPASSWORD` in a protected process environment. Before production recovery, restore to a new isolated database, run `alembic current`, `alembic check`, `PRAGMA integrity_check` for SQLite where relevant, and validate exercise/objective/source/finding/reviewer/action/audit counts and source hashes. Then change an approved deployment target through the organization's normal change process.

Uploaded evidence bytes and extracted text are stored in the same database rows in the current application. PostgreSQL/SQLite database backups therefore include source bytes and provenance metadata. No external evidence object store is configured. If a future storage adapter is added, database and object-store snapshots must be coordinated and verified together.

## Rollback and incident handling

Migrations are forward-only; both current downgrade functions stop with an explicit error. Do not downgrade or delete a database to roll back an app. If a release fails, route ingress back to the previous compatible image and preserve the migrated database. If the prior image is schema-incompatible, stop writes and restore a protected pre-upgrade backup into a new database target, validate it, and switch only under an approved recovery plan. Preserve failed migration logs without logging evidence contents or credentials.

Operators still need an owner-approved deployment change process, migration lock/coordination policy, maintenance window, backup schedule, tested encrypted restore, RPO/RTO, retention/legal-hold policy, incident response contacts, paging rules, and rollback authority.

## Staging rehearsal and rollback

The disposable local configuration rehearsal is reproducible from the project root:

```bash
.venv/bin/python scripts/rehearse_staging.py
```

It creates a unique project and volumes, random loopback app/ingress ports, a self-signed one-day certificate, file-injected synthetic test identities/secrets, and a fresh PostgreSQL database. It starts the private ClamAV service, checks its persistent signatures and actual scan capability, performs browser/upload/load/failure/restart tests, and restores the database archive into a **new** database. It removes only resources owned by that generated project. Do not substitute an existing project or database. `scripts/rehearse_clamav_integration.py` separately runs the actual-scanner API pytest against a disposable ClamAV service published only to loopback; it is not the production network topology. `scripts/rehearse_postgres.py` remains a separate demo path that deliberately disables scanning and labels its synthetic evidence not scanned.

Before a real rollback rehearsal, provide the exact prior image and a disposable environment. Exercise (1) deploy/migration of the candidate image, (2) post-migration failure, (3) route ingress to the prior compatible image while preserving the database, (4) when schema compatibility requires it, restore the pre-change backup to a new database and validate schema, row counts, source hashes, reviews, actions and audit events, and (5) confirm readiness and controlled access after switching. Do not downgrade a production database or overwrite the only backup. Phase 5 did not run this previous-image procedure because no prior compatible image was supplied.

For a first real staging environment, follow `docs/audits/DRILLLOOP_STAGING_HANDOFF.md` and close the decisions in `docs/audits/DRILLLOOP_OWNER_DECISIONS.md`. In particular, obtain approval for the scanner image/license, signature provenance/update network and freshness policy, quarantine operations, and monitoring while keeping `DRILLLOOP_UPLOAD_SCAN_MODE=required`. The local Compose service demonstrates an actual scanner integration but does not constitute organization approval; an unavailable or stale scanner returns a safe error without importing the file.
