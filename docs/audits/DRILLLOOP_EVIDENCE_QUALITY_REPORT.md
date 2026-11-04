# DrillLoop evidence quality report

**Updated:** 4 November 2026
**Scope:** fictional evaluation fixtures only. No representative operational records were used.

## Finding summary

| ID | Evidence | Severity / impact | Status | Verification required | Owner decision |
|---|---|---|---|---|---|
| EQ-01 — missed communication start citation | Revision 1 evaluation matched 8/9 canonical references. `control_room_log.csv`, row 4 was extracted as observation EL-03, but the OBJ-02 start-term list did not match its wording. | Medium: the analysis could omit the source that establishes the measured interval and reduce auditability. | **FIXED** by adding the source wording to the rule and an API regression requiring citations to rows 4 and 5. Revision 2 matches all 9 canonical references. | Keep the regression and review the source-level links for each release. | Independent evaluator must approve the rule interpretation. |
| EQ-02 — seven references outside the canonical citation list | The primary fixture marks canonical required references only; the seven generated additional references were not labeled as exhaustive positives or negatives. | Medium: citation precision and unsupported-citation rate cannot be calculated. Some references corroborate, one conflicts, and one transcript reference is incomplete. | **OPEN — label scope limitation.** All seven items are itemized below; none is silently counted as supported or unsupported. | Independent evaluator adjudicates each reference and revises a separately versioned label set. | Product owner approves evaluation acceptance thresholds; independent evaluator adjudicates evidence. |
| EQ-03 — recording offsets treated as event timestamps | `transcript.json` supplies a recording start and speech offsets, not timestamps for the events described. Revision 1 converted offsets 12.2s, 38.4s, and 69.3s into apparent event times. | High: could place an event on the exercise timeline at the time it was spoken rather than the time it occurred and could affect elapsed-time rules. | **FIXED.** Segment offsets remain in source locators; only an explicit segment `event_time` is parsed as event time. Added tests for offset-only and explicit-time cases. Dataset revision 2 corrects the prior timestamp labels because they encoded the same semantic error. | Keep regression coverage; independently assess temporal semantics against permitted records. | Product/evaluation owner approves whether transcript event times must be manually annotated. |

## Evaluation results

| Dataset | Findings | Observations | Citations | Time/duration and unknown handling | Scope |
|---|---|---|---|---|---|
| `synthetic-hospital-power-outage`, revision 2 | 5/5; precision, recall, F1 = 1.00 | 21/21; precision, recall, F1 = 1.00 | 9/9 canonical required references; recall 1.00. Seven additional references remain unlabeled; precision and unsupported rate are **undefined**. | 17/17 explicitly labeled event timestamps; 4/4 expected event-time unknowns retained; 5/5 objective assessments and durations matched; 1/1 conflict retained; 4/4 listed unknowns retained. | Single developer-authored fictional fixture. |
| `held-out-synthetic-library-evacuation`, revision 1 | 2/2; precision, recall, F1 = 1.00 | 4/4; precision, recall, F1 = 1.00 | 3/3 exhaustive citations; precision and recall = 1.00, unsupported rate 0.00. | 4/4 timestamps and both duration/objective assessments matched. | Process hold-out: developer-authored, run once, not used to tune rules; not independently adjudicated. |

The perfect values above describe only these small, fictional fixtures. They do not establish real-evidence accuracy, reviewer agreement, operational usefulness, or productivity. No actual production or staging evaluation has occurred. The primary fixture's citation labels are incomplete, so the seven additional references cannot be used to calculate precision or an unsupported-citation rate.

## Original citation discrepancies, item by item

The original baseline had five expected findings, nine canonical references, eight canonical matches, and seven other references. The primary objective involved is OBJ-02: “Communicate outage status and obtain unit acknowledgement within three minutes.” Its source evidence is [control_room_log.csv row 4](../../demo/evidence/control_room_log.csv) (09:03 request, EL-03) and row 5 (09:10 response, EL-04). The extracted row 4 wording was correct; the rule's `start_terms` did not include “Outage acknowledgement was requested from the inpatient units by radio.” This was an implementation defect, not a label error. Adding that phrase fixed the missed start and gives 7 minutes elapsed against 3 minutes. A regression checks the finding cites both rows and retains the conflicting evaluator note.

In the final revision-2 isolated evaluation run, the transient database assigned source IDs `69a38a8b-6ed6-40ef-ba20-920d9d8b38c5` to `control_room_log.csv`, `67a776b7-9ed6-48fd-8178-e523071caf67` to `evaluator_notes.txt`, and `b5a117f3-607a-45ac-a9f5-26730ea00eed` to `transcript.json`. The IDs are run-local and will differ on another import; filenames, row/line/segment locators, and source wording below identify the stable evidence.

The seven generated references were:

| Finding / objective | Actual source reference and extracted wording | Rule decision and relationship to expected evidence | Classification / root cause |
|---|---|---|---|
| `POWER_RESTORATION_DELAY` / OBJ-01: “Restore and confirm essential power circuits within 60 seconds of a primary supply interruption.” Expected canonical refs: `control_room_log.csv` rows 2 and 3. | `evaluator_notes.txt`, line 1: “Evaluator A: The primary utility power supply failed.” | Corroborates the start event at CSV row 2. It does not add a new event time; the timed calculation uses 09:02 to 09:06. | **Corroborating duplicate event, not an exact duplicate citation.** Rule matching links every extracted source observation matching the configured start phrase. Label scope omitted alternate-source references. |
| `COMMUNICATION_ACK_DELAY` / OBJ-02: “Communicate outage status and obtain unit acknowledgement within three minutes.” Expected canonical refs: `control_room_log.csv` rows 4 and 5. | `evaluator_notes.txt`, line 3: “Incident Command sent a radio request for each inpatient unit to acknowledge the outage.” | Corroborates the start event at CSV row 4 and supports the configured interval. | **Corroborating duplicate event.** Rule term matching is working; alternative evidence was not exhaustively labeled. |
| `COMMUNICATION_ACK_DELAY` / OBJ-02; expected canonical refs: `control_room_log.csv` rows 4 and 5. | `evaluator_notes.txt`, line 9: “My watch shows acknowledgement at 09:11, while the control room log says 09:10. The acknowledgement time is unresolved.” | The source conflicts with CSV row 5's 09:10 time. The assessment retains the 09:10 and 09:11 interval candidates (420 and 480 seconds), both beyond the 180-second threshold. | **Relevant conflict, unresolved fact.** This is not a duplicate success event or proven unsupported citation. The rule/output correctly leaves the time conflict visible; the citation inventory did not classify it. |
| `COLD_CHAIN_PROCEDURE_COMPLETED` / OBJ-03: “Activate patient-care continuity procedures and preserve medication cold-chain records.” Expected canonical ref: `control_room_log.csv` row 8. | `evaluator_notes.txt`, line 7: “ICU staff completed the emergency medication cold-chain relocation procedure and documented chain of custody.” | Supports completion and chain-of-custody record, in agreement with CSV row 8. | **Corroborating duplicate event.** The event-presence rule selected the phrase; the canonical-only citation labels omit the alternate source. |
| `COLD_CHAIN_PROCEDURE_COMPLETED` / OBJ-03: “Activate patient-care continuity procedures and preserve medication cold-chain records.” Expected canonical ref: `control_room_log.csv` row 8. | `transcript.json`, segment 3, audio offset 69.30–76.80s: “ICU completed the cold-chain relocation procedure.” | Supports completion but does not state that a cold-chain record or chain of custody was preserved. It must not alone establish the full objective. Its old derived 09:08:09 value was speech position, not an event timestamp; it is now unknown unless explicitly annotated. | **Partial / incomplete support; evaluator review required.** The event-presence rule matches “cold-chain relocation procedure” and does not require the record phrase. Add an explicit record criterion only after evaluator approval; the current source row 8 already supplies complete evidence. |
| `RESPONSE_TIME_DISCREPANCY` / OBJ-04: “Capture and reconcile response start and arrival timestamps in the incident log.” Expected canonical refs: `control_room_log.csv` rows 2, 6 and 7. | `evaluator_notes.txt`, line 1: “The primary utility power supply failed.” | Corroborates the start event in CSV row 2; elapsed calculation remains 360 seconds using CSV row 2 and row 6. | **Corroborating duplicate event.** It is correctly associated with the discrepancy finding; canonical labels omit alternate evidence. |
| `RESPONSE_TIME_DISCREPANCY` / OBJ-04: “Capture and reconcile response start and arrival timestamps in the incident log.” Expected canonical refs: `control_room_log.csv` rows 2, 6 and 7. | `evaluator_notes.txt`, line 5: “Facilities technician arrived at the switch room six minutes after power failed.” | Corroborates the arrival at CSV row 6; the separately reported 120 seconds remains in CSV row 7. | **Corroborating duplicate event.** Rule term matching is correct; no evidence adjudication exists for alternate references. |

There are **zero repeated identical `(finding, source, locator)` occurrences** in the output. The word “duplicate” above means the same event appears in another source. No additional reference was classified as definitely unsupported from the available labels. The conflict-bearing line 9 and partial transcript segment 3 need human adjudication before citation precision can be computed.

## Evaluation framework and reproducibility

`scripts/evaluate_analysis.py` loads the exercise, objective rules, and source files from each dataset, verifies each source SHA-256, and runs against a private temporary SQLite database. It reports finding/observation precision and recall only when corresponding labels are marked complete; citation precision and unsupported rate stay null when citation labels are incomplete. It reports unmatched and repeated citation occurrences, false-positive/false-negative and duplicate findings, incorrect objective/category mappings, timestamp/duration discrepancies, event-time unknowns, conflicts, insufficient-information assessments, and per-objective/per-exercise metrics. All generated drafts were `proposed`; reviewer decisions were null.

Commands run:

```bash
.venv/bin/python scripts/evaluate_analysis.py --dataset evals/datasets/synthetic-hospital-v1.json
.venv/bin/python scripts/evaluate_analysis.py --dataset evals/held-out/synthetic-library-v1.json
```

Both commands used fictional sources and disposable databases. The primary evaluation emits a Starlette/httpx deprecation warning from the local test client; it does not invalidate the result. Analysis latency in those runs is a single in-process measurement and is not capacity evidence.

## Remaining verification

- Obtain permitted representative records and have independent evaluators label findings, source references, timestamps, duration, conflicts, and unknowns before analysis outputs are shown.
- Agree acceptance thresholds before testing. Keep a versioned, held-out dataset outside tuning and adjudicate every extra reference.
- Assess whether language describing an event's time, audio recording time, and transcript segment offset must be represented separately in future UI and exports.
- Make no real-world accuracy claim until that independent evaluation is complete.
