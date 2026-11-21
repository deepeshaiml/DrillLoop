# Eureka V2 readiness · 21 November 2026

**Fictional stakeholder demonstration READY. Overall evidence and model evaluation PARTIAL.** The local rehearsal completed with a controlled fictional response, explicit human promotion, separate finding approval, corrective-action closure, PDF and AI-disabled restart. Authentic-document findings are limited to extraction and source-purpose handling. EUR-26-014 remains a self-assessed TRL 4 prototype.

| Gate | Verdict | Evidence |
| --- | --- | --- |
| A. Authentic document evaluation | **PARTIAL** | Public browser journeys PASS. Verified 5/5 prepared PDF uploads, 20/20 sampled exact passages on expected physical pages, and 4/4 planned clocks. The 2025 MSEL and underlying evaluator records were unavailable. |
| B. Evidence integrity | **PASS** | Reference-classified sources retain their bytes and locators. Zero observed events from 4 planned clocks. Two former false success proposals eliminated. Exact AI citation validation and semantic review remain distinct. |
| C. Deterministic functionality | **PASS** | Five fictional rule proposals before human decisions. Authenticated end-to-end and backend checks passed. |
| D. AI-assisted functionality | **PARTIAL** | Real local preview and browser inference passed. One instruction-bearing quotation surfaced in an abstention. Two fictional timing relationships require semantic review. |
| E. Human-controlled workflow | **PASS** | Save, acceptance, promotion into proposed, finding approval, action review and closure were exercised separately. Version and retry guard tests passed. |
| F. Stakeholder demonstration | **READY** | Rehearsed the complete fictional scenario at the default loopback URL with screenshots, two Playwright recordings, a recovered candidate and a verified PDF. |
| G. Eureka presentation package | **READY** | 30-second, 90-second, 3-minute and 9½-minute scripts, exact clicks, Q&A, evaluation and pilot proposal. |
| H. Real-world product validation | **NOT VALIDATED** | No pilot, independent adjudication, operational accuracy, adoption or measured time savings. |
| I. Production readiness | **NOT ASSESSED** | Scope was the local stakeholder demo and targeted engineering checks. |

## Verification and remaining limitations

- Local backend **350 passed, 1 skipped**. The skipped integration requires ClamAV. SQLite startup and migrations ran for the evaluations and rehearsals. Local PostgreSQL and container verification were unavailable because the Docker daemon was offline.
- Playwright passed the existing live workflow, scanned and mixed PDF workflows, candidate review/promotion/restart, and the new public and fictional journeys. The existing workflow covered 320, 390, 768, 1024 and 1440 px. Seven scoped axe checks across the candidate and Eureka runs reported zero violations. Assertions covered role denial, keyboard focus, concurrency, failures and retry. No uncaught browser errors were reported on the successful runs.
- The fictional PDF had six pages, all visually inspected. The 31- and 52-page public browser exports had their first, middle and final pages visually sampled. Text checks verified exercise identity, source purpose, decision status, attribution, promotion provenance, action details and closure wording where applicable.
- Python lint/format, production frontend build, Python and npm dependency audit, and staged whitespace/secret scans passed locally. The public-source permissions and research conclusions remain open for owner review in the unmerged evaluation PR.
- **P1 corrected:** PDF placeholder prose caused invalid timestamp errors. Evaluation-guide wording generated unsupported positive performance findings. Source purpose is now chosen at upload, and reference records stay out of the observed sequence and scoring. Previously imported sources need evaluator classification before performance use.
- **P2 open:** Direct Office files require conversion, MSEL and primary observations are missing, source byte reuse rights are unverified, and AI requires semantic review. A multi-day published report exceeds the single-window exercise metadata model.

Launch with `.venv/bin/python scripts/serve_eureka_demo.py --controlled` and use the printed credentials at **http://127.0.0.1:8765**. See the [demo guide](EUREKA_V2_DEMO_GUIDE.md), [pitch scripts](EUREKA_PITCH_SCRIPT.md), [executive Q&A](EUREKA_EXECUTIVE_QA.md), [pilot proposal](EUREKA_PILOT_PROPOSAL.md), and [evaluation report](../../evals/real-evidence/EVALUATION_REPORT.md).

Local captures and rehearsal PDF are under `.eureka-private/artifacts/drillloop-eval-i3hqj1hs/`. The public browser captures and PDFs are held separately under `.eureka-private/artifacts/drillloop-eval-n0qxxbtw/`.
