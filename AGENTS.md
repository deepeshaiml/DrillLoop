# DrillLoop Agent Instructions

These are project rules for coding assistants and analysis agents. For a plain-language overview, glossary, and worked evidence example, read [DRILLLOOP_READER_GUIDE.md](DRILLLOOP_READER_GUIDE.md).

## Product constraints
- DrillLoop is an evidence-backed exercise evaluation and corrective-action workflow. It must never invent exercise events or imply AI findings are approved.
- Synthetic demo evidence and ground truth must be clearly labeled fictional.
- Every proposed finding needs source-level evidence links. Unsupported or conflicting evidence must be flagged and left for evaluator review.
- Only human reviewers approve/reject findings or close actions.
- Do not claim official FEMA/HSEEP certification, speaker diarization, multilingual accuracy, or measured human productivity without evidence.
- Keep an offline demo path; cloud model APIs are optional only.

## Engineering conventions
- Prefer small, maintainable components and explicit schemas over opaque agent behavior.
- Preserve source provenance: filenames, source IDs, line/page/segment references, timestamps, and uncertainty.
- Add validation and clear errors for malformed or unsupported inputs, missing objectives, and unavailable models.
- Track implementation and actual verification in `PROGRESS.md`; never report tests or benchmarks that were not run.
- Keep generated documents and slides editable where possible. Speaker notes must contain substantive narration on every slide.
- Use commercially permitted dependencies/models and record license/version assumptions in the technical design.

## Evidence response format for AI-assisted work
- Start with the source wording and cite its source ID and locator (file plus row, line, page, or transcript segment).
- Put any evaluation in a separate `interpretation` field; list missing or conflicting facts as `unknowns`.
- Keep the decision `proposed` and the reviewer decision `null` until an authorized human acts.
- Leave an owner `null` when the source does not identify one. Do not make up a responsible person, deadline, cause, or event time to make a draft look complete.
- The JSON example in the Reader Guide is conceptual only, not an API schema.
