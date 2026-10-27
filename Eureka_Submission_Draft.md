# Eureka Submission Draft — DrillLoop

This is a working copy of the Eureka form text. Contact information is omitted here because the public repository is not the place to publish a work email. The portal form contains the lead’s contact details.

## Idea details

### Submission route

Individual employee idea.

### Theme

Public Safety Intelligence.

### Title

DrillLoop: Evidence-Linked Exercise Review and Action Closure

### One-line summary

DrillLoop helps hospital preparedness evaluators turn exercise records into draft after-action reports and improvement plans, link findings to their sources, and track corrective actions through human review and proof of completion.

### Problem

The proposed first use case is a hospital preparedness evaluator reviewing records from a tabletop exercise and preparing an After-Action Report and Improvement Plan (AAR/IP). Evaluators may need to reconcile notes, event logs, timelines, and transcripts. A finding is harder to verify when its source is unclear, and corrective actions can lack an owner, due date, or completion evidence.

The candidate report preparer is an exercise evaluator or preparedness staff member. A preparedness lead or exercise sponsor is a candidate report approver. The budget owner and procurement path have not been identified. Exercise frequency, reporting time, verification effort, willingness to pilot, and monetary cost have not been measured.

### Solution

DrillLoop is a local-first web application. A user defines an exercise and objectives, then imports notes, CSV event logs, JSON event/transcript records, or selectable-text PDFs. It preserves original files and exact source locators, such as a CSV row, note line, PDF page, or transcript segment. Missing times remain unplaced and conflicting times remain visible.

The current MVP uses a fixed, deterministic workflow to extract observations, identify candidate findings, map them to stated objectives, attach evidence IDs, draft corrective actions, and prepare an AAR/IP. Findings remain proposed until a human reviewer approves or rejects them. Action approval and closure require reviewer checks and closure evidence.

The rules were built around one fictional hospital power-outage exercise. Performance on an unfamiliar exercise and the incremental value of optional AI have not been measured. Optional faster-whisper transcription requires a locally staged model; optional Ollama can reword an action already proposed by the rules. Neither path was included in the benchmark. The sample transcript is pre-generated and contains a labeled synthetic recognition error.

Veoci markets after-action reporting and corrective-action follow-up. DrillLoop’s proposed distinction—source-level traceability, explicit reviewer decisions, and evidence-backed closure—has not been validated in a comparable workflow. A possible fit with Presight public-safety work is also unverified; no integration or customer demand is established.

### Technology readiness

TRL 4, provisional self-assessment on the conventional 1–9 scale. The evidence is a working local prototype and technical checks on one closed synthetic fixture. There has been no operational pilot, independent TRL assessment, evaluator study, or validation on unfamiliar exercise records. The Eureka program’s TRL definitions may differ from the conventional scale.

### Tags

Emergency preparedness, exercise evaluation, evidence traceability, human-in-the-loop AI, corrective action management, AAR/IP, local-first AI, hospital resilience.

### Submission type

Web app. DrillLoop is a functional local MVP, not a hosted production service or an autonomous AI agent.

## Expected impact and validation plan

The initial segment hypothesis is hospital preparedness teams. The primary user is an exercise evaluator or preparedness staff member. A preparedness lead or exercise sponsor is a candidate report approver. The budget owner is unknown. Other sectors in the project materials are possible future markets, not validated customers.

A proposed discovery and pilot sequence is:

1. Interview two or three prospective hospital-preparedness users and observe one existing review process with permission.
2. Establish a baseline for report preparation, evidence verification, reviewer corrections, and action follow-up.
3. If a partner agrees, compare the current process and DrillLoop using the same permitted exercise records.
4. Use evaluator-labeled records from an unfamiliar exercise to measure missed findings, incorrect findings, unsupported claims, and timeline agreement.
5. Select one relevant alternative with the pilot partner and compare source-location precision, reviewer decisions, and closure evidence on the same workflow.
6. Agree success thresholds with the partner before measuring results.

These are proposed activities, not completed interviews or a confirmed pilot. No success thresholds, savings, customer revenue, or field performance have been measured. The first commercial model proposed for discovery is a per-exercise pilot fee; no price, willingness-to-pay evidence, staffing plan, or delivery-cost model is established. Annual subscriptions, private deployment, custom templates, and support services remain later hypotheses. The separate Business Case lists validation inputs without inventing prices or costs.

## Lead and team

The Eureka form identifies the lead as an individual submitter in Product–Synergy / AI Engineering. The project demonstrates delivery of a working web prototype and evidence-review workflow; prior emergency-preparedness experience is not stated. Available time is not specified. Proposed support needs are a preparedness-domain adviser, evaluator participation, permitted pilot data, and security/privacy review. No adviser or pilot partner is confirmed.

## Data governance and security status

The demo stores uploaded source bytes and extracted text in its configured database and records reviewer audit events. It uses a shared demo reviewer key, not named accounts or role-based access. Tenant isolation, encryption at rest, retention/deletion controls, malware scanning, and a security assessment are not implemented or evidenced. The default workflow makes no cloud-model call; optional ASR is local and Ollama is configured as a local/private service. The packaged benchmark uses fictional records and does not establish safe handling of protected patient or operational data.

## Documents and prototype evidence

### Pitch deck

- [Dedicated Eureka pitch deck, editable PPTX with speaker notes](DrillLoop_Pitch_Deck.pptx)
- [Pitch deck PDF](DrillLoop_Pitch_Deck.pdf)

### Idea document

- [Idea document PDF](DrillLoop_Idea_Document.pdf)
- [Editable idea document DOCX](DrillLoop_Idea_Document.docx)

### Three supporting attachments

1. [Evaluation report PDF](DrillLoop_Evaluation_Report.pdf) — closed synthetic benchmark and limitations.
2. [Business case PDF](DrillLoop_Business_Case.pdf) — commercial options and the information required before pricing or financial projections.
3. [Architecture PDF](DrillLoop_Architecture.pdf).

### Prototype evidence

- Public repository: [github.com/deepeshaiml/DrillLoop](https://github.com/deepeshaiml/DrillLoop)
- Screenshots: [Overview](assets/DrillLoop_Demo_Overview.png), [Findings](assets/DrillLoop_Demo_Findings.png), [Corrective Actions](assets/DrillLoop_Demo_Actions.png).
- Hosted demo URL: none.
- Web build ZIP: not prepared; the full workflow requires the API and database.

### How judges can test it

The demo uses fictional records. Clone the repository, run `cp .env.example .env` and `docker compose up --build`, then open `http://localhost:8000`. Demo login: `Exercise Reviewer` / `demo-reviewer`.

Select **Night Shift: Extended Power Loss** (`HOSP-PO-2026-01`). Review the timeline and the unresolved 09:10/09:11 discrepancy. Open a proposed finding and follow its source links. Review the action with the intentionally missing owner, then try the reviewer-gated approval and closure flow. Export the AAR/IP PDF. Full details are in [DEMO_GUIDE.md](DEMO_GUIDE.md).

## Portal upload checklist

The previous AI Coach review reported that linked materials were unavailable for inspection, although screenshots and a repository were listed. The portal should show the actual screenshot and document files as uploaded and previewable. The Business Review deck is a separate artifact; the dedicated 13-slide Eureka Pitch Deck is the primary pitch presentation. Lead email belongs in the Eureka form, not this public repository copy.
