# DrillLoop Reader Guide

This guide gives readers a quick way to understand the project. The other documents contain the same story at different levels of detail.

## DrillLoop in one sentence

DrillLoop helps exercise evaluators turn notes and event logs into **proposed** findings that link back to evidence, then track improvement tasks until a human reviewer checks the completion proof.

## Start with this example

The fictional hospital exercise sets this objective: **restore essential power within 60 seconds of a power failure.** The uploaded control-room log says:

- `EL-01`, `control_room_log.csv`, row 2, 09:02: primary utility power failed.
- `EL-02`, `control_room_log.csv`, row 3, 09:06: backup power was stable and essential circuits were restored.

The two records show about four minutes between failure and restoration. That is longer than the exercise target of one minute. DrillLoop can therefore propose this finding:

> **Proposed improvement:** Essential power restoration took about four minutes, exceeding the 60-second objective. Evidence: `EL-01` and `EL-02`. Cause of the delay: unknown from these records. Reviewer decision: pending.

This example separates three things:

1. **Observed facts:** what the source records say, with a file and row that a person can open.
2. **Interpretation:** why the observed facts may miss the exercise objective.
3. **Decision:** whether an authorized evaluator accepts the proposed finding.

DrillLoop must not fill the unknown cause with a guess. The finding remains proposed until a human reviews it.

## Choose the right document

| If you are… | Start here | Then read… |
|---|---|---|
| New to the project | [README](README.md) | [Demo Guide](DEMO_GUIDE.md) |
| An exercise evaluator or preparedness lead | [Demo Guide](DEMO_GUIDE.md) | [Idea Document](DrillLoop_Idea_Document.pdf), then the [Evaluation Report](DrillLoop_Evaluation_Report.pdf) |
| A manager considering a pilot or purchase | [Business Case](DrillLoop_Business_Case.pdf) | [Idea Document](DrillLoop_Idea_Document.pdf) and its assumptions |
| A developer | [Technical Design](DrillLoop_Technical_Design.md) | [Execution Plan](EXECUTION_PLAN.md), source code, and [Progress Log](PROGRESS.md) |
| An AI agent assisting with review or implementation | [Agent Instructions](AGENTS.md) | This guide, then the technical design and the labeled files in `demo/` |

## Plain-language glossary

| Term | Meaning in DrillLoop |
|---|---|
| Exercise objective | A target the team agreed to practice, such as “restore essential power within 60 seconds.” |
| Observation | A statement copied or extracted from a source, such as an event-log row or evaluator note. |
| Finding | An evaluator’s conclusion about how performance compared with an objective. A finding is only a proposal until a human approves it. |
| Evidence link / source locator | A direct pointer to the supporting file and place in it: a CSV row, note line, PDF page, or transcript segment. |
| Corrective action | A task intended to improve performance next time. It needs an owner, due date, and a clear way to tell whether it is done. |
| Acceptance criteria | The observable proof that an action is complete. Example: “A timed radio drill meets the three-minute acknowledgement target in three consecutive tests.” |
| Closure evidence | The record a reviewer checks before marking an action complete, such as a dated drill result. |
| AAR/IP | After-Action Report and Improvement Plan: a summary of what happened, what was learned, and which improvements will be tracked. |
| HSEEP | FEMA’s Homeland Security Exercise and Evaluation Program, a doctrine for planning and evaluating exercises. DrillLoop borrows concepts; it is not FEMA-certified. |
| ASR | Automatic speech recognition: software that turns audio into text. A transcript can contain mistakes and needs human review. |
| LLM | Large language model: software that can draft or rephrase text. In this MVP, an optional local model may reword an action; it cannot create or approve findings. |
| Precision / recall | Precision asks “Of the findings proposed, how many matched the labels?” Recall asks “Of the expected labeled findings, how many were found?” The current scores use one synthetic example only. |
| F1 score | A single score that combines precision and recall. A high F1 on this sample does not imply the same score on new evidence. |
| FTE | Full-time equivalent: one person’s full-year workload, used to describe staffing assumptions. |
| SaaS | Software as a Service: software hosted and operated for customers through a subscription. |
| Local-first | The demo can run on the user’s computer without sending evidence to a cloud AI service. |
| SHA-256 fingerprint | A long digital checksum used to detect whether the uploaded source file changed. It does not prove that the source itself is true. |
| Fixed rules / deterministic | Clear, pre-written checks that return the same result for the same input. They are easier to inspect but can miss wording outside the examples they recognize. |
| CSV / JSON | Common file formats: CSV is a spreadsheet-like table; JSON stores named data fields in a structured text form. |
| SQLite / PostgreSQL | Two kinds of databases. SQLite is convenient for one local demo; PostgreSQL is designed to store data for a deployed service. |
| OCR | Optical character recognition: software that tries to read words from a scanned image. This MVP does not do OCR; its PDF reader needs selectable text. |
| WER / RSS | Word error rate compares a transcript with the spoken words. Resident set size (RSS) is the amount of computer memory a running process uses. |
| RBAC / SSO | Role-based access control gives different permissions to different job roles. Single sign-on (SSO) uses an organization’s existing login service. Neither is implemented in the demo. |
| SME | Subject-matter expert: a person with specific emergency preparedness or exercise-evaluation knowledge. |

## Guidance for AI agents

When an AI agent reads DrillLoop evidence or proposes a change, it should:

1. Read `AGENTS.md` and preserve its evidence and human-approval rules.
2. Quote the source or identify its exact observation ID and locator for every factual claim.
3. Keep source text, interpretation, and uncertainty in separate fields.
4. Use `unknown` or `null` for missing time, cause, owner, or decision. Do not invent values to complete a record.
5. Label any proposed finding `proposed`; never mark it approved or closed.
6. Treat `demo/ground_truth.json` as fictional expected labels for this fixture, not as observed real-world truth.

### Example agent response

The following is a **conceptual review record**, not an API request format:

```json
{
  "status": "proposed",
  "finding_code": "POWER_RESTORATION_DELAY",
  "objective_id": "OBJ-01",
  "observed_facts": [
    {
      "evidence_id": "EL-01",
      "source": "control_room_log.csv",
      "locator": "row 2",
      "time": "09:02",
      "quote": "Primary utility power supply failed at the hospital."
    },
    {
      "evidence_id": "EL-02",
      "source": "control_room_log.csv",
      "locator": "row 3",
      "time": "09:06",
      "quote": "Backup generator was stable and essential circuits were restored four minutes after the primary supply failed."
    }
  ],
  "interpretation": "The recorded restoration took about four minutes, exceeding the 60-second exercise target.",
  "unknowns": ["The cause of the delay is not established by these records."],
  "reviewer_decision": null,
  "action_draft": {
    "owner": null,
    "acceptance_criteria": "A timed test shows essential power restored within 60 seconds.",
    "status": "proposed"
  }
}
```

The action text is only a draft. An evaluator must check whether it is appropriate, assign an actual owner, and approve it. A later reviewer must inspect closure evidence before the action is closed.

## What the benchmark does and does not say

The included benchmark checks whether the fixed rules recover the labels in one deliberately constructed fictional scenario. It matched all eight expected event rows and all five expected finding codes in that fixture. It does **not** show how well the system performs on a new exercise, whether the evidence supports a finding in professional judgment, how much staff time is saved, or whether a language or speech model is accurate. See the [Evaluation Report](DrillLoop_Evaluation_Report.pdf) for definitions and limits.
