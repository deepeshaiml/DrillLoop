# Saved AI candidate review

In **Findings**, an evaluator or administrator can generate AI suggestions and select **Save for review** on a suggestion with validated source support. **Open saved candidate** goes directly to that entry. The **Saved AI candidates** queue is available to granted reviewers, evaluators, viewers, and administrators even when generation is disabled. Reviewers and administrators can record a decision. Candidate acceptance and finding approval are separate human decisions.

Open a candidate to read the original source wording, filename, source ID, and locator. Inspect the original source for current citations, especially when the wording or time came from OCR. An exact citation confirms a match to the stored observation. Evaluators verify whether the wording supports the interpretation. Stale candidates retain their historical citations, original objective, and decisions.

## Create a proposed finding

An administrator or reviewer can open an eligible candidate accepted for consideration and select **Create proposed finding**. Read the original quotations and uncertainty, then enter the title, observable facts and interpretation, choose strength or improvement, and confirm the objective and wording. Keep reported times and potential causes qualified whenever the evidence leaves them uncertain.

A candidate needs current, validated support for a relevant observation or corroboration. Abstentions, different response phases, contradictions, unresolved event identity or cause, and candidates with counterevidence stay in candidate review. The server checks for shared supporting observations in findings and current rule results for the same objective. It also blocks promotion if evidence analysis finds a conflict involving the candidate's support. The [architecture policy](../architecture/AI_CANDIDATE_LIFECYCLE.md#11-implemented-phase-4c4-promotion-policy) documents the eligibility and duplicate rules.

Select **Open finding** to go to the regular Findings review. The proposal has an unassigned reviewer. A subsequent review decision is recorded separately, and any corrective action follows its own workflow. The source candidate remains available with its original evidence, acceptance and promotion history.

## Implemented API contract

All paths below start with `/api/exercises/{exercise_id}`. Each request requires the authenticated identity and a live exercise grant within the exercise's organization. Writes use the existing session and CSRF protection.

| Endpoint | Access and parameters | Successful response |
| --- | --- | --- |
| `POST /ai-suggestions` | Admin or evaluator | `200` with provider/model, suggestions, unassessed objectives, validation counts, context-limit flag, and optional token counts. Each suggestion contains `objective_id`, `kind`, `assessment`, `interpretation`, `evidence`, `counterevidence`, `unknowns`, `uncertainty`, `review_reason`, `status: "proposed"`, `reviewer_decision: null`, and nullable `save_token`. |
| `POST /ai-candidates` | Admin or evaluator. Body `{"save_token":"…"}`. Requires `Idempotency-Key`. | `201` with `id` and applied `version`. The interface reads detail for the current state. |
| `GET /ai-candidates` | Any granted role. `limit` is 1–50, default 20. `after` is the previous response's ID cursor. | `200` with `candidates` and nullable `next_after`. |
| `GET /ai-candidates/{id}` | Any granted role. `history_after_version` defaults to 0. `history_limit` is 1–50, default 20. | `200` with the full saved snapshot, current review state and freshness, latest human decision, the requested history page, and nullable `next_history_after_version`. `ETag` is a quoted positive integer such as `"3"`. |
| `POST /ai-candidates/{id}/review` | Admin or reviewer. Body `{"decision":"…","note":null}`. Requires `Idempotency-Key` and `If-Match` with the exact detail ETag. | `200` with `id`, applied `version`, and `decision`. The interface reloads detail and audit history. |
| `POST /ai-candidates/{id}/promote` | Admin or reviewer. Requires exact `If-Match` and `Idempotency-Key`. Body includes `title`, `observation`, `interpretation`, `category`, `objective_id` and `confirmed: true`. | `201` with candidate `id`, applied `version`, `finding_id` and `finding_status: "proposed"`. An exact committed retry returns that creation outcome. Read detail for the current finding status. |

List and detail include `promoted`. Detail includes `linked_finding` with the current finding ID, code, title and status, or a `promotion_block_reason` if candidate policy prevents promotion.

The list summary contains `id`, `exercise_id`, `organization_id`, `objective_id`, `kind`, `assessment`, `status`, `review_state`, `freshness`, `stale_at`, `stale_reasons`, `version`, `created_at`, and `updated_at`. The backend orders by candidate ID and has cursor pagination. The interface fetches six entries at a time and reads their detail snapshots with `history_limit=1` to display interpretation, original objective text, supporting-reference count, and requester attribution. Filters apply to the current page.

Details add `objective_text`, `objective_fingerprint`, `context_fingerprint`, `schema_version`, `interpretation`, `unknowns`, `uncertainty`, `review_reason`, `evidence`, `counterevidence`, `provenance`, `reviewer_decision`, `latest_decision`, and `history`. Citations include observation and source IDs, original filename, locator, complete wording (up to 360 characters), extraction method, time confidence, raw time, source and observation fingerprints, and available OCR metadata and recognition confidence. Generation provenance contains `provider`, `model`, `model_digest`, `prompt_version`, `validator_version`, `context_version`, `generated_at`, and `requested_by_user_id`. The interface omits a null model digest.

### State and recovery

| `review_state` | Decisions for current evidence |
| --- | --- |
| `pending_review` | `accepted_for_consideration`, `rejected`, `more_evidence_required` |
| `accepted_for_consideration` | `rejected`, `more_evidence_required` |
| `more_evidence_required` | `accepted_for_consideration`, `rejected` |
| `rejected` | None |

The optional review note is limited to 3,000 characters. A request for more evidence requires a nonblank note. `reviewer_decision` is null until the first human review. Freshness is independently `current` or `stale`. A stale candidate is read-only, including when its last human state was accepted. Reasons include `validator_changed`, `objective_changed`, `source_unavailable`, `citation_invalid`, and `context_changed`.

An eligible save token expires after 15 minutes. The server signs it for the requesting identity and exercise, checks the evidence at save, and deduplicates token issuance. The browser treats it as opaque and holds it in memory. Each intended write uses a single idempotency key of 1–128 characters from `[A-Za-z0-9._:-]`. A committed replay is authorized first, then returns the original outcome even after token expiry or a later version change. A confirmation uses the ETag of the candidate version displayed when the reviewer chose the action. A retry uses the original payload, key, and review ETag. On a version conflict, the interface reloads the candidate and asks the user to choose any subsequent decision explicitly.

| HTTP status | Relevant response details |
| --- | --- |
| 401 / 403 / 404 | Missing session, insufficient role or CSRF, or unavailable exercise/candidate scope. Token scope mismatch returns `AI_SUGGESTION_NOT_FOUND`. |
| 409 | `AI_CONTEXT_CHANGED`, `AI_SOURCE_UNAVAILABLE`, `AI_CANDIDATE_STALE`, `INVALID_CANDIDATE_TRANSITION`, `IDEMPOTENCY_CONFLICT`, `CANDIDATE_PROMOTION_INELIGIBLE`, `CANDIDATE_ALREADY_PROMOTED`, `AI_CITATIONS_INVALID` (promotion), `FINDING_DUPLICATE`. |
| 412 | `CANDIDATE_VERSION_MISMATCH`. |
| 422 | `AI_REQUEST_INVALID`, `AI_SAVE_TOKEN_INVALID`, `AI_SAVE_TOKEN_EXPIRED`, `AI_CITATIONS_INVALID`, `INVALID_CANDIDATE_VERSION`, `INVALID_IDEMPOTENCY_KEY`, `AI_OBJECTIVES_REQUIRED`, `AI_INVALID_OBJECTIVES`, `AI_EVIDENCE_REQUIRED`, `CANDIDATE_OBJECTIVE_MISMATCH`. |
| 428 | `IDEMPOTENCY_KEY_REQUIRED` or `CANDIDATE_VERSION_REQUIRED`. |
| 429 / 502 / 503 / 504 | `AI_BUSY`, `AI_INVALID_RESPONSE`, `AI_DISABLED`, `AI_UNAVAILABLE`, `AI_SAVE_UNAVAILABLE`, `AI_VERIFICATION_UNAVAILABLE`, `AI_TIMEOUT`. |

Candidate-specific errors use `detail.code` and `detail.message`. Existing authorization errors may supply a string `detail`. Context-limited generation returns a successful abstention without a save token.

Audit events contain `id`, `operation`, `actor`, `actor_user_id`, `exercise_id`, `candidate_id`, `organization_id`, `request_id`, `timestamp`, and `version`. `ai_candidate_saved` records `prior_state: null` and `new_state`. `ai_candidate_reviewed` records `prior_state`, `new_state`, and `note`. `ai_candidate_invalidated` records `prior_freshness`, `new_freshness`, and `reasons` under the system actor. `ai_candidate_promoted` records the retained review state, `finding_id`, creation status and wording confirmation. The detail endpoint pages events in ascending version order and exposes the latest human review separately.

## Run the fictional browser workflow

From the repository root, with the locked Python and frontend dependencies and Playwright Chromium installed:

```sh
npm --prefix frontend run build
python frontend/e2e/run_candidate_review.py
```

The runner migrates a new owned SQLite database, injects a fictional provider, starts the real application on loopback, and restarts it with AI disabled. The browser calls the actual save, candidate review, promotion, finding review, authorization, and evidence APIs. Screenshots default to a new temporary directory. Add `--screenshots /path/to/artifacts` to select a destination and `--axe-script /path/to/axe.min.js` to run focused accessibility scans with an installed axe-core script. This change uses the existing React, TypeScript, and Playwright dependencies. axe-core was used as an optional local test tool with no application dependency.
