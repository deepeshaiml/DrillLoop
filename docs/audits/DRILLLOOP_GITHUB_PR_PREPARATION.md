# DrillLoop GitHub Pull Request Preparation

**Prepared:** 4 November 2026
**Remote:** `origin` → `https://github.com/deepeshaiml/DrillLoop.git`
**Default branch:** `main` (verified through authenticated GitHub API)
**Publication state:** local-only; no branch, commit, push, pull request, release, or repository setting was changed.

## Recommended review unit

Use **one pull request** for the integrated application, schema, upload/scanner controls, container/deployment reference, CI, tests, and current operator documentation. The scanner-before-persistence path, authorization, migrations, and full browser workflow depend on one another; separate mergeable pull requests would create intermediate states that are not covered by the end-to-end verification.

Organize the commits within that pull request for review:

1. `feat: add scoped identity and evidence review workflows`
2. `feat: add versioned persistence and safe recovery`
3. `feat: add bounded upload processing and malware scanning`
4. `build: add reproducible containers and quality gates`
5. `docs: prepare release review and staging operations`

These are proposed messages only. Do not stage or create commits until the repository owner authorizes it.

## Proposed pull request

**Branch:** `release/drillloop-phase6-rc1`
**Base:** `main`
**Title:** `Prepare DrillLoop release candidate with scoped auth, migrations, and upload scanning`

### Description

```markdown
## Summary
- Add scoped named-user authentication, evidence provenance, proposed findings, human review, and corrective-action workflows.
- Add Alembic migrations, PostgreSQL support, isolated upload parsing, optional private ClamAV scanning, and non-destructive recovery tools.
- Add a hardened container/Compose reference, fork-safe quality workflow, reproducible dependency locks, and current operator documentation.

## Verification
- Backend suite: 86 passed, 1 skipped; optional ClamAV integration: 1 passed separately.
- Ruff and formatting, TypeScript/production build, npm and Python dependency audits: passed.
- Fresh SQLite and isolated PostgreSQL migrations/schema checks: passed.
- Four retained local PostgreSQL 18.6 + HTTPS/Nginx + ClamAV browser/load rehearsal results show 80/80 workflows and zero unexpected 5xx each. In order, safe parser-capacity 503 retries were 1/0/1/0 and edge 429 retry counts were 180/181/173/185. The latest run had no browser errors, restored 84/84 exercise rows to a new disposable database, and recorded 52.55-hour-old ClamAV signatures under the proposed, unapproved 72-hour ceiling. One intervening invocation's output was truncated; its result is unverified and excluded from these counts.
- Actionlint, Compose config, and `git diff --check`: passed locally.

## Boundaries
- All evaluation and rehearsal evidence is synthetic.
- Local Docker results are not approved staging or production evidence.
- The remote hosted workflow and branch protections must be configured and verified after this reviewed branch is published.
- Previous-image rollback was not run because no prior compatible image was supplied.
- The latest rehearsal exercised the checked-in Nginx upstream directly. Four invocations have retained passing summaries; one intervening invocation remains unverified. No prior-image rollback was run.
```

The exact path set is in [DRILLLOOP_RELEASE_FILE_MANIFEST.md](DRILLLOOP_RELEASE_FILE_MANIFEST.md). Exclude its nine paths (eight superseded audit snapshots and the empty migration `.gitkeep`); preserve all of them locally without staging or deleting them.

### Public content and test-credential review

No production credentials, private keys, databases, backups, logs, or evidence attachments are in the 81 proposed paths. The candidate-only scan found no Gitleaks matches. CI, tests, and historical local commands contain fixed synthetic test passwords; never reuse them as deployment credentials. The included `scripts/generate_docs.py` contains two company-specific references describing a possible public-safety fit. They are hypotheses rather than evidence, but the content owner must confirm or revise this wording before public publication. No absolute developer home paths were found.

## Local release checks to repeat before publication

Run these after staging only manifest paths and inspect the cached diff. The existing working tree is on `main`; keep all unrelated and excluded files intact.

```bash
git status --short --branch
git diff --cached --name-status
git diff --cached --check
env -u DATABASE_URL .venv/bin/pytest -q
.venv/bin/ruff check backend scripts
.venv/bin/ruff format --check backend scripts
npm --prefix frontend run build
npm --prefix frontend audit --audit-level=high
uv tool run --from pip-audit pip-audit -r requirements-dev.lock
docker compose --profile scanner --env-file .env.example config --quiet
docker run --rm -v "$PWD/.github/workflows:/work:ro" rhysd/actionlint:latest -color /work/ci.yml
git diff --cached --check
```

The scanner-enabled local harness is available as `.venv/bin/python scripts/rehearse_staging.py`; it creates and cleans unique local Docker resources, uses synthetic data, and takes several minutes. It is separate from approval or deployment in a real staging environment.

## Verified remote state

| Item | Verified state | Effect |
|---|---|---|
| Repository/default branch | Public repository; default branch `main`. | Owner review and PR base are known. |
| Hosted workflows | None are present on remote `main`; the local `.github/workflows/ci.yml` is not published. | No hosted result exists. CI starts after authorized publication. |
| `main` protection/rulesets | Branch protection API reports “Branch not protected”; repository rulesets list is empty. | PR review and required checks are not enforced today. |
| Workflow token default | `GITHUB_TOKEN` default permission is read-only; workflow approval for PR reviews is false. | Supports the workflow's read-only permission model. Verify hosted behavior after publication. |
| Fork PR approval | First-time contributors require approval before workflow runs. | Reduces unsolicited fork-run exposure. The local workflow still uses ordinary `pull_request`, no `pull_request_target`, and no repository write permission. |
| Allowed Actions | Repository allows all Actions. | The local actions are SHA-pinned after review; repository owner should consider an allowlist or an explicit pinning policy. |
| Secret scanning | Secret scanning and push protection are enabled. Non-provider-pattern scanning is disabled. | Keep enabled and turn on non-provider patterns if supported by the repository plan. A local scan is still required for the candidate. |
| Dependabot security updates | Disabled. | Repository owner should enable security updates and review the supported dependency update policy. |
| Check name | Local workflow job name is `Test, scan, browser, and container verification`. | After first hosted run, select the exact check context shown by GitHub; do not configure a guessed context. |

The workflow runs on `pull_request`, `push` to `main`/`master`, and `workflow_dispatch`. It sets repository `contents: read`, uses disposable PostgreSQL/ClamAV services, creates owner-marked SQLite directories, uses only test credentials, and writes no deployment secrets. Fork PRs do not receive production secrets. No `pull_request_target` trigger is present. The single CI job covers lint/format, backend tests, dependency audits, frontend build, SQLite/PostgreSQL migrations, browser workflow, Gitleaks, and hardened-container smoke checks.

## Owner publication and branch-protection sequence

1. **Review scope.** Repository owner/release manager checks this report and every `INCLUDE` row in the manifest. Confirm excluded reports and ignored data are not staged. Review security, license, identity, and staging decisions with the listed roles.
2. **Authorize branch and commits.** After explicit authorization, create `release/drillloop-phase6-rc1` from the reviewed `origin/main` base. Stage only `INCLUDE` paths. Inspect `git diff --cached --name-status` and `git diff --cached`; rerun the local checks. Commit in coherent reviewable units using the proposed messages.
3. **Authorize publication.** After the owner approves the reviewed commits, push the branch to the verified `origin` repository and open a PR targeting `main`. Do not publish excluded files, ignored artifacts, or unreviewed additions.
4. **Run hosted CI.** Confirm the PR run checks out the exact branch commit; wait for the full job, inspect logs and dependencies, and resolve any failure. Confirm fork PR behavior and the read-only token in the Actions run summary.
5. **Configure review and required checks.** A repository administrator enables branch protection or a ruleset for `main`, requires at least one approving review from someone other than the author, dismisses stale approvals or requires approval after the latest push, requires conversation resolution, and selects the exact successful CI job context. Verify the settings through GitHub UI/API and test that merge is blocked when either approval or the check is absent.
6. **Enable security controls.** Keep secret scanning and push protection on; enable non-provider secret patterns and Dependabot alerts/security updates where supported. Review Actions policy and keep third-party actions pinned to full commit SHAs. Confirm workflow token permissions remain read-only.
7. **Review and merge normally.** Assigned reviewers inspect product behavior, migrations/data safety, scanner and identity controls, CI/security, and release documentation. Merge only after required approvals and checks pass through the repository's normal process.

All GitHub operations above are owner actions. This preparation has performed read-only remote inspection only.

## Phase 8.3 content-review correction (4 November 2026)

The earlier text scan did not inspect Office package image-description attributes. The baseline pitch deck contained absolute developer-machine paths in three image descriptions; the current release copy replaces them with generic descriptions. The submission draft is now a neutralized publication copy at `Product_Concept_Submission_Draft.md`. The original baseline remains publicly accessible, and these branch changes do not remove its history. A final Gitleaks 8.30.1 run scanned a private snapshot of all 117 index files, the staged diff, and extracted text/metadata from nine Office/PDF artifacts; all returned zero findings. See the Phase 8.3 addendum in [DRILLLOOP_PHASE6_RELEASE_REVIEW.md](DRILLLOOP_PHASE6_RELEASE_REVIEW.md).
