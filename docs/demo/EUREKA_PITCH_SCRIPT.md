# DrillLoop Eureka V2 speaking notes

## 30 seconds

After a hospital emergency exercise, evaluators reconcile logs, notes, and scans before they can explain what happened and assign follow-up. DrillLoop connects proposed findings to the original record, gives an authorized human the decision, and carries the decision into a draft after-action report and improvement plan. We tested the local prototype on a fictional end-to-end exercise and on authentic public documents. We’re asking for one permitted dataset and a small reviewer group to measure whether it reduces reconciliation effort while preserving evidence quality.

## 90 seconds

The report is the end of the work. The difficult part is getting from scattered records to a claim you can defend, especially when two sources disagree about timing or an expected task has no completion record. After the report, the team needs to know which corrective action was approved, who owns it, and what evidence supported closure.

DrillLoop begins with exercise objectives and retains the source wording and its page, row, or line. Rules compare evidence to configured targets. Optional local AI suggests how narrative records may relate. An evaluator checks the source, decides whether to accept and promote a candidate, and separately approves or rejects the resulting finding. The action trail and draft AAR/IP show those decisions.

The October submission for EUR-26-014 described a prototype for exercise reviews and action closure. TRL 4 is our own assessment. The pilot would test whether the workflow saves time while preserving evidence quality. V2 adds scanned PDF processing, persistent AI candidate review and explicit promotion. Public-document tests checked extraction and that a plan’s schedule and expected tasks stay outside performance scoring. We have not measured staff time saved. We’re requesting a small paired comparison with real evaluators, a permitted exercise record and an agreed manual baseline.

## 3 minutes

**0:00–0:45, problem.** Two exercise notes can both be credible and disagree about when a response happened. An AAR needs to show which claim has supporting evidence, which time is disputed, and what the evaluator decided. Drafting a report and checking the follow-up work are related jobs.

**0:45–1:30, evidence path.** DrillLoop ingests logs, notes, transcripts and PDFs. It holds the source bytes and records where each observation came from. OCR carries uncertainty. Rules can measure configured elapsed targets. When the records are a plan or published AAR, the reviewer classifies them as references. Planned clocks and published judgments stay visible with their locators.

**1:30–2:15, human decisions.** Optional local AI generates advisory labels and citations. The application validates citation wording and context. A reviewer judges the substance. Saving, candidate acceptance, promotion into a proposed finding, and finding approval are distinct steps. Corrective action approval and closure require recorded human decisions. The draft report reflects that history.

**2:15–3:00, measurement and request.** We imported four prepared PDFs rendered from County-provided planning files and one original Northwest report PDF. Twenty of 20 sampled source passages landed on the expected physical pages. All four sampled schedule clocks stayed outside the observed timeline. A permitted exercise with primary observations, paired manual and assisted reviews, and independent adjudication is the next measurement.

## 9½-minute presentation

| Time | Narration |
| --- | --- |
| 0:00 | “Imagine the evaluator after an emergency exercise. The control room has one log, ward staff have separate notes, and the report still needs a defensible statement about how long recovery took. The person who approves that statement also has to hand off work that can be checked later. DrillLoop brings those records, decisions, and actions into one review.” |
| 0:50 | “This is Night Shift, a fictional hospital exercise. The October 2026 Eureka submission, EUR-26-014, described a TRL 4 prototype. The target for this exercise is to restore and confirm essential circuits within one minute of the outage. V2 adds local OCR and a saved, human-controlled path from an AI suggestion to a proposed finding.” |
| 1:35 | “Here are the original fictional records. I’ll import a scanned pharmacy note and a separate signed-form note. Tesseract extracted the scan. The evidence viewer identifies page 1 and leaves its timing uncertain. A reviewer can open the original page.” |
| 2:35 | “The control-room log records power failure at 09:02 and restoration at 09:06. Four minutes exceeds the sixty-second target. The acknowledgement record has a separate timing disagreement. Both source references stay visible while it is unresolved.” |
| 3:25 | “In Findings, the exercise rule has prepared a proposal with its objective and source links. The review still belongs to a person. We can confirm what the source says. We have no basis here to assign the cause of the delayed transfer.” |
| 4:15 | “This run uses a scripted local reply so everyone sees the same fictional review path. The suggestion cites the signed pharmacy form. We also ran a real local model separately and checked its citations and interpretation. I’ll save this one for review. That creates a candidate and keeps it advisory.” |
| 5:25 | “The named reviewer inspects the original line and accepts the candidate for consideration. A further decision creates a proposed finding with human-entered wording and unknown timing. Look at the two separate statuses before I open the finding.” |
| 6:40 | “Now I open the proposal and approve it as the reviewer. That records a different decision from accepting the candidate. The power-restoration proposal has its own evidence and decision. Its action is a retest against the 60-second objective.” |
| 7:20 | “For this fictional action, the operator records the owner, due date, and acceptance criterion. A person approves the action and records the retest before confirming closure. The audit shows who did that. This is the accountability loop after the report.” |
| 8:15 | “The draft AAR/IP contains the current finding decisions, evidence links, action details, and closure wording. It records what the reviewers decided and the proof they submitted.” |
| 8:55–9:30 | “We also processed authentic records, a 2025 County planning set and a completed Northwest evaluator report. Every one of 20 sampled passages appeared on its expected page. We kept four scheduled clocks outside the observed timeline. The reference-only exercises yielded no performance findings. Help us identify two or three hospital preparedness reviewers and one permitted dataset. We’ll agree on quality and time measures before running the pilot.” |

[Exact clicks and fallback](EUREKA_V2_DEMO_GUIDE.md) · [Evaluation and denominators](../../evals/real-evidence/EVALUATION_REPORT.md)
