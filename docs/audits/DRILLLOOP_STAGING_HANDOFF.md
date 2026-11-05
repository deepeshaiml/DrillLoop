# DrillLoop Staging Handoff

**Prepared:** 4 November 2026
**Status:** Local engineering handoff prepared. No staging host, DNS record, certificate, secret, identity provider, scanner policy, or operator has been selected or approved.

## Staging entry criteria

The repository includes a Docker Compose reference and a reproducible synthetic rehearsal. An approved staging deployment requires organization-owned infrastructure, security decisions, and named operators. The local PostgreSQL/HTTPS/ClamAV rehearsal does not satisfy those approvals.

For the first staging deployment, keep the scope to synthetic evidence until the data owner approves a classification and handling policy for any real evidence. Required-scan mode must remain enabled. Upload acceptance is blocked until Security Operations approves the scanner service, signature/update policy, freshness threshold, quarantine handling, and alert owner.

## Latest local verification boundary

The latest captured local rehearsal used PostgreSQL 18.6, the checked-in HTTPS/Nginx configuration, and the digest-pinned ClamAV service. Its synthetic browser workflow passed with no browser errors; the 80/80 workflow load matrix completed across concurrency 1/2/5/10 with zero parser-capacity rejections, 185 bounded ingress 429 retries, and zero unexpected 5xx. Clean/EICAR scanning, invalid-file rejection, scanner timeout/outage fail-closed behavior, audit/quarantine cleanup, restart persistence, and restore of 84/84 exercise rows into a new disposable database passed. ClamAV signatures were 52.55 hours old against the proposed, unapproved local 72-hour ceiling. The harness reported no cleanup error and its unique Docker project was removed. These results show reproducible local mechanics only; they do not approve hosting, scanner policy, capacity, or organizational staging.

Four rehearsal summaries are retained as passes. An intervening invocation's output was truncated before its check summary could be retained; its status is unverified and it is excluded from these counts.

## Infrastructure and resource prerequisites

Select an organization-managed cloud container platform, organization-managed VM/container host, or private on-premises platform. The chosen environment must provide:

- Supported container runtime or a reviewed equivalent, controlled image registry, patch process, and restricted administrative access.
- A private network between the application, PostgreSQL, ClamAV, and ingress. Do not publish the database or ClamD ports to public networks.
- A stable hostname, owner-managed DNS, approved TLS termination, renewal monitoring, and a trusted-host allowlist.
- Persistent PostgreSQL storage and persistent ClamAV signature storage. Provide separately protected backup storage and a documented restore target.
- Secret delivery from the selected platform's secret facility or private mounted files; do not store deployment credentials in the repository, image, command history, or plain environment files.
- Health checks, log/metric collection, alert delivery, incident access, and an assigned operator roster.

The current Compose resource limits are **reference values to size and approve**, not staging capacity requirements:

| Component | Local reference limit | Storage/network behavior |
|---|---:|---|
| Application | 1 CPU, 1 GiB RAM | Non-root, read-only root, temporary 64 MiB `/tmp`, 64 MiB private quarantine tmpfs. Source bytes and extracted text are persisted in PostgreSQL. |
| PostgreSQL | 1 CPU, 2 GiB RAM | PostgreSQL 18.6 image is digest-pinned; persistent volume at `/var/lib/postgresql`; private internal app/database network. |
| ClamAV | 2 CPU, 5 GiB RAM | Digest-pinned ClamAV Debian 1.5.4 image; persistent `/var/lib/clamav` signature volume; no host port; separate signature-update egress network. |
| Nginx ingress | 0.25 CPU, 128 MiB RAM | Unprivileged image, read-only root, loopback binding in local Compose. TLS reference listens on container ports 8080 and 8443. |

Repeat the workload against the approved platform and tune only after the service owner defines expected upload sizes, active users, concurrency, arrival rate, latency, availability, and storage targets.

## DNS, TLS, ingress, and secrets

1. The network/platform owner selects the hostname, DNS zone, certificate authority, TLS termination point, renewal mechanism, and public/private reachability.
2. Replace `drillloop.example.invalid` in the Nginx reference with the approved hostname. The config expects certificate files at `/etc/nginx/tls/fullchain.pem` and `/etc/nginx/tls/privkey.pem`. Map the approved ingress 80/443 ports to container 8080/8443, or use an approved adapter with equivalent redirects, TLS, request limits, security headers, and forwarding headers.
3. `deploy/nginx/drillloop.conf` now targets the Compose application service name `app`; keep ingress and app on a network where that name resolves. The checked-in rehearsal uses this configuration directly and changes only its test hostname and certificate.
4. Set `DRILLLOOP_TRUSTED_HOSTS` to only the deployed hostname. Set `DRILLLOOP_CORS_ORIGINS` only when a separately hosted UI requires an approved origin.
5. Deliver `DRILLLOOP_DB_PASSWORD_FILE`, `DRILLLOOP_SESSION_SECRET_FILE`, and `DRILLLOOP_USERS_FILE` through the chosen secret mechanism. The session secret must be at least 32 bytes. User configuration contains scrypt password hashes, named identities, organization IDs, and roles; it does not contain plaintext passwords.
6. Restrict secret files to the app/database operator roles and set private filesystem permissions. Define rotation, emergency account revocation, and session invalidation. Compose secrets are local file mounts; confirm the selected platform's delivery and access-audit behavior.

Do not copy the local `.env.example` values into staging. It deliberately demonstrates local loopback setup, HTTP cookies, and disabled scanning. Staging/production runtime validation requires PostgreSQL, secure cookies, file-injected secrets, named users, trusted hosts, required scanning, and both `DEMO_SEED=0` and `DRILLLOOP_ENABLE_DEMO_SEED=0`.

## PostgreSQL and migration sequence

- Provision PostgreSQL 18 or an approved compatible PostgreSQL service, a dedicated application database and role, TLS/network policy as required by the selected platform, storage monitoring, and backup ownership.
- Confirm the target is a fresh database or follow the existing-database adoption procedure. Existing unversioned or populated databases are never automatically stamped, dropped, or migrated; rehearse against a protected clone with the DBA.
- For a new target, verify database health, deliver credentials, run a protected pre-migration backup where applicable, then apply the versioned migrations with the explicit maintenance job. Run `alembic current` and `alembic check`; verify application readiness before ingress traffic.
- Compose starts the application without startup DDL. Keep schema deployment as an explicit, reviewed operation. Review migration scripts and compatibility with the application image before every release.

Example for the reviewed Compose reference only:

```bash
docker compose --profile maintenance run --build --rm migrate
```

Do not run this command against an existing volume until the database owner has approved the adoption, backup, clone rehearsal, and maintenance plan.

## ClamAV operation and failure policy

The local service is `clamav/clamav-debian:1.5.4` pinned by digest. The technical design records GPLv2. ClamD has no protocol authentication or transport encryption; keep it inside the trusted private app/scanner network, control who can join that network, and allow signature-update egress only to approved sources.

Before accepting uploads, Security Operations and Legal must decide:

- Approved scanner vendor/image/version and GPLv2 obligations for the intended organizational use.
- Signature provenance, outbound update destinations, proxy/firewall rules, update cadence, stale-signature alerting, and who investigates update failures.
- Maximum signature age. The local 72-hour limit is a test configuration only; the local FreshClam setting requests four checks daily. Neither is approved policy.
- Quarantine access, cleanup verification, false-positive review, retention, release authorization, and audit retention.
- Scanner outage, timeout, unhealthy, and stale-signature response. The application currently fails closed in required mode; no file is accepted or persisted without a clean verdict.

The app readiness endpoint checks ClamD `PING`/`VERSION`, parseable signature time, signature age, a clean scan, and EICAR detection. Container health alone is not evidence of scanner capability. Alert on readiness failure, update age, scan failures/timeouts, rejection rates, and quarantine cleanup errors.

## Persistent storage, backup, and recovery

- PostgreSQL owns source bytes, extracted content, findings, reviews, actions, and audit data. The current reference does not put uploaded source files in object storage.
- ClamAV signatures use a persistent volume. Per-upload quarantine is temporary private storage and should be empty after completion, rejection, timeout, cancellation, or parser failure.
- Define storage encryption, key custody, backup encryption, backup retention, access logging, off-site copy policy, and the owner of restore credentials before storing organizational evidence.
- `scripts/db_recovery.py` supports PostgreSQL custom-format backups and integrity checks, with restore only to a new target. Restore the backup, validate migration state, row counts, relevant source hashes, permissions, and app readiness before any target switch.
- The final local rehearsal restored a 93,562-byte archive to a new disposable database and matched 84/84 exercise rows. This verifies mechanics only; it sets no RPO, RTO, schedule, encryption policy, or operator acceptance.
- Assign a database operator and recovery authority. Rehearse a restore on the selected platform and record elapsed time and data checks against owner-approved RPO/RTO.

## Application startup and smoke tests

Start the app only after the platform, secrets, PostgreSQL, scanner, and ingress configuration are approved. Set `DRILLLOOP_ENVIRONMENT=staging`, `DRILLLOOP_COOKIE_SECURE=1`, `DRILLLOOP_UPLOAD_SCAN_MODE=required`, explicit trusted hosts, and `DEMO_SEED=0`. Provide named test accounts through the approved file-secret mechanism. Do not enable demo seeding in an organizational environment.

Run these checks after migrations and before inviting reviewers:

1. Confirm container image digest/version, runtime user, read-only root, dropped capabilities, resource limits, network reachability, and secret mounts.
2. Check `/api/live` and `/api/ready`; verify ready status includes the approved scanner and current signature metadata.
3. Confirm TLS chain, hostname, redirect, HSTS/security headers, Secure/HttpOnly/SameSite cookies, trusted-host rejection, and ingress rate-limit response.
4. Sign in with a staging test identity. Create an exercise and objective using synthetic facts, upload a clean synthetic CSV and selectable-text PDF, and confirm every observation/finding includes source IDs and locators.
5. Confirm unsupported/conflicting evidence remains unknown or flagged; verify findings remain proposed until a named authorized reviewer acts, and action closure requires human-entered evidence.
6. Confirm another unauthorized identity cannot read exercise detail, evidence download, report, metrics, or review endpoints; verify audit identity is server-derived.
7. Restart app and database one at a time; verify readiness and expected persisted synthetic records.

## Scanner failure and upload concurrency tests

In the approved staging boundary, test an EICAR fixture, clean file, invalid timestamp/type, scanner timeout, unavailable scanner, stale/unparseable signature, parser timeout/cancellation, queue saturation, oversized upload, and rejected-batch retry. For each rejected scan/parser case, verify no source, observation, finding, or action was persisted; the client receives a safe error and retry guidance only when retry is safe; audit and metrics identify the outcome; temporary quarantine is cleaned; and service readiness/alerts recover.

Four retained Phase 6 replay results each completed 20 synthetic workflows at concurrency 1/2/5/10. Safe parser-capacity 503 retries were 1/0/1/0; edge 429 retries were 180/181/173/185; all four had zero unexpected 5xx responses and completed all 80 workflows. A separate invocation's output was truncated and is unverified. Repeat with owner-approved evidence sizes and rates on the selected staging platform; compare throughput, p50/p95, resources, queue depth, retries, DB pool, scanner age, and errors to thresholds set by the service owner. Local values are not acceptance targets.

## Rollback and release control

- Keep the prior approved application image by immutable digest and record its database compatibility. The current local rehearsal did not have a prior image, so image rollback is unverified.
- Migrations refuse downgrade. Rollback requires the approved forward-fix or restoration of a protected pre-change backup into a **new** database target, validation, and an owner-authorized traffic switch. Never overwrite the current database or volume during rollback.
- Before the first staging release, rehearse release approval, migration, smoke checks, scanner failure, backup restore to a new target, previous-image behavior, DNS/ingress change reversal, and access revocation. Assign the decision authority for rollback and incident declaration.
- Preserve release image digests, migration revision, backup identity, approval record, smoke results, rollback outcome, and operator handoff in the organization's change system.

## Organizational approvals and technical verification

| Requirement | Technical verification possible in this repository | Organizational decision/approval required |
|---|---|---|
| Container behavior, migrations, authz paths, scanner fail-closed flow, backup/restore mechanics, and synthetic browser/load workflows | Yes, in isolated local resources and later in the selected staging environment. | Platform/security acceptance and authorization to run in staging. |
| Host, DNS, TLS provider, secret manager, storage encryption, network boundary, and monitoring destination | Only configuration and probes after selection. | Platform/network/security owners select and approve providers, boundaries, access, and renewal. |
| Evidence type, classification, retention, deletion, legal hold, privacy, backup encryption, RPO/RTO | Code can enforce approved values after decisions; local rehearsal cannot set policy. | Data owner, privacy/legal, security, DBA, and continuity owners. |
| Scanner license, signature provenance, freshness/update egress, quarantine process, alerts, and outage policy | Engine/version/capability/failure behavior can be retested. | Legal and Security Operations approve vendor, policy, operator, and evidence-release authority. |
| Enterprise identity, MFA, account lifecycle, role mapping, and session revocation | Local configured-account tests pass; integration test requires selected IdP. | Identity owner and security architect. |
| Service ownership, support, incident response, change control, and rollback authority | Rehearsal records can be produced after owners are named. | Executive sponsor/platform owner assigns accountable roles and approves operations. |
| Analysis acceptance and real evidence use | Synthetic fixtures and citations can be inspected. | Independent evaluators set acceptance thresholds and adjudicate permitted representative data. |

The 17 decisions, options, role owners, and deferral consequences are detailed in [DRILLLOOP_OWNER_DECISIONS.md](DRILLLOOP_OWNER_DECISIONS.md). Start with hosting, ingress/TLS, operator ownership, scanner approval/update policy, staging identity scope, data scope, and recovery handling. Production-only decisions include RPO/RTO targets, long-term retention, production availability, and external integration if it becomes a requirement.

## Owner decision handoff — all 17 open decisions

`OD-01` through `OD-17` map to rows 1–17 in the existing owner decision register. Recommendations below are proposals; none represents an approval or a selected vendor, platform, identity provider, integration, or data policy.

| ID | Required decision and why it blocks | Compatible options; proposal | Owner role | Required stage | If deferred |
|---|---|---|---|---|---|
| OD-01 | Select where the app, database, scanner, and ingress run; no approved host or network exists. | Organization-managed cloud container platform; organization-managed VM/container host; private on-premises platform. **Proposal:** choose only after data-residency, private-network, storage, and operator requirements are reviewed. | Platform owner / security architect | Before any approved staging deployment. | No approved target, network boundary, patching, backup, or operator access model. |
| OD-02 | Assign hostname, DNS, TLS termination, renewal, and key custody; current host/certificate values are placeholders. | Owner ingress/load balancer, approved certificate service, or internal DNS/PKI. **Proposal:** one owner-managed TLS termination point with monitored renewal and HSTS. | Network/platform owner | Before staging ingress is exposed. | No trusted hostname/certificate or accountable renewal path. |
| OD-03 | Decide whether organizational staging requires an enterprise IdP; only configured local password accounts exist. | Approved OIDC/SAML gateway with role mapping; local accounts for isolated synthetic demo if policy permits. **Proposal:** use the organization’s standard IdP for organizational users; do not infer which one. | Identity owner / security architect | Before organizational user access; can defer for isolated synthetic-only rehearsal with written scope. | No provisioning, central revocation, or enterprise audit identity; blocks organizational rollout. |
| OD-04 | Set MFA policy; local password authentication has no MFA. | MFA through selected IdP; approved risk-based policy; no MFA only for isolated demo identities. **Proposal:** require the organization’s standard MFA for interactive evidence access. | Identity owner / security | Before organizational evidence access. | Privileged/user access policy remains unapproved; blocks organization use unless an explicit exception exists. |
| OD-05 | Classify evidence and state permitted content; evidence and extracted text are stored in database and backups. | Approved classifications and allowed evidence categories; prohibit restricted data until controls are approved. **Proposal:** synthetic-only staging first, then least-sensitive category specifically approved for a pilot. | Data owner / privacy and security | Before any real evidence enters staging. | Data residency, encryption, access, logging, export, and incident controls cannot be accepted. |
| OD-06 | Define retention, deletion, and legal-hold behavior; no automated retention job exists. | Period by exercise/contract; owner-triggered deletion; archive under policy; legal hold. **Proposal:** define an explicit synthetic staging cleanup schedule, then policy-based lifecycle before real data. | Data owner / privacy / legal | Before evidence is retained in staging; real evidence requires approved lifecycle. | Data may remain in DB/backups without an authorized deletion or hold process. |
| OD-07 | Approve backup encryption and key/restore ownership; local mechanics do not protect organization backup keys. | Platform-managed encrypted backups; separately encrypted `pg_dump`; both under approved key management. **Proposal:** organization-controlled keys and restricted restore roles. | Database owner / security operations | Before sensitive-evidence staging; required for production. | Backups can be inaccessible, overexposed, or inconsistent with data policy. |
| OD-08 | Set tolerated data-loss window (RPO); no backup interval is an approved target. | Owner-selected interval based on ingestion and replication design. **Proposal:** set after workload and backup schedule are known. | Business continuity owner / data owner | Production design and acceptance. | Production recovery cannot be assessed; may defer for disposable synthetic staging. |
| OD-09 | Set service recovery time (RTO); local restore duration is not a target. | Owner-selected value measured in the target environment. **Proposal:** time full service recovery, including app, DB, secrets, ingress, and operators. | Business continuity owner / operations owner | Production design and acceptance. | No production recovery target or staffing/cost basis; may defer for disposable synthetic staging. |
| OD-10 | Decide whether an external integration is in scope; no destination is selected or implemented. | Standalone scope; or a named approved exercise/document/records system. **Proposal:** keep staging standalone until a product owner names a destination. | Product owner / integration owner | Only if external-integration demo or production integration is required. | No integration claim can be made; standalone staging may proceed. |
| OD-11 | Approve API/schema and sandbox if an integration destination is selected. | Versioned export-only or bidirectional contract with synthetic sandbox. **Proposal:** require stable IDs, locators, timestamps, error/retry rules, and data owner before implementation. | Integration owner / destination system owner | Before integration development or test. | Integration cannot be implemented or safely verified; standalone staging unaffected. |
| OD-12 | Select and approve the scanner service, license, signatures, quarantine, outage, and release process. | Organization-operated ClamAV/ClamD; approved managed scanner adapter; or no uploads until approved. **Proposal:** review the pinned local ClamAV integration as a candidate without assuming approval. | Security operations / evidence custodian | Before any staging upload is accepted. | Required mode must keep uploads fail-closed; blocks upload-based staging and production. |
| OD-13 | Set normal/burst concurrency, upload sizes, and arrival rate; current parser has one worker and eight waiters. | Owner-defined workflow and evidence workload. **Proposal:** approve a conservative bound and repeat the matrix on staging. | Product owner / SRE | Before capacity acceptance; staging can run only within an explicitly bounded test scope meanwhile. | Local load data cannot justify throughput or capacity claims; saturation behavior remains unaccepted. |
| OD-14 | Set availability and latency targets; none is an SLA today. | Owner-defined uptime, maintenance, API/workflow p50/p95/p99, upload, and analysis targets. **Proposal:** define by workflow and evidence size after platform selection. | Product owner / SRE | Production acceptance; collect staging measurements against proposed targets. | No production service level, alert threshold, or capacity basis. |
| OD-15 | Set independent evaluation thresholds and labels; developer fixtures do not define domain acceptance. | Finding/citation precision/recall, unsupported-citation ceiling, unknown/conflict handling, reviewer agreement, and stop criteria. **Proposal:** agree before a blind evaluation and adjudicate each citation. | Product owner / independent evaluation lead | Before real-evidence evaluation or any accuracy claim. | Use remains demonstration-only; no general accuracy claim is supported. |
| OD-16 | Name accountable service, release, incident, database, scanner, and rollback owners. | Named internal service/on-call team; contracted managed-operations owner; defer deployment. **Proposal:** assign role owners before staging, then name individuals in the controlled service register. | Executive sponsor / operations leader | Before approved staging release. | No one can accept release, respond to incidents, authorize migrations, or own recovery. |
| OD-17 | Approve scanner signature freshness, update cadence/egress, and stale behavior; local 72-hour/four checks are proposed only. | Security-approved freshness window, update sources/schedule, alert and upload response; or a different approved scanner contract. **Proposal:** Security Operations sets values from threat and update-service requirements. | Security operations / evidence custodian | Before scanner-enabled staging uploads. | Readiness remains governed by an unapproved threshold; uploads must stay disabled/fail-closed. |

### Priorities for the first staging deployment

- **Required for any approved deployment:** OD-01 hosting, OD-02 TLS/DNS, OD-12 scanner approval if uploads are tested, OD-16 operational owner.
- **Required for organizational users:** OD-03 identity and OD-04 MFA, or a written decision limiting the stage to isolated synthetic identities.
- **Required before real evidence:** OD-05 classification, OD-06 retention/deletion, and OD-07 backup encryption/ownership. Keep initial data synthetic if these are open.
- **Required before upload acceptance and capacity sign-off:** OD-12 scanner approval, OD-13 workload, and OD-17 signature/update policy. Keep required scanning fail-closed.
- **Production-only unless the business chooses otherwise:** OD-08 RPO, OD-09 RTO, OD-14 availability/latency targets, OD-15 real-evidence evaluation thresholds, and OD-10/11 integration decisions when integration is required.
