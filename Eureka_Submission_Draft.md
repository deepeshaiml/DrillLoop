# Eureka Submission Draft — DrillLoop

This draft is based on the project files and recorded synthetic benchmark. It distinguishes current prototype evidence from proposed pilot work and unverified assumptions.

## Idea details

### 1. What are you submitting?

**Submission route:** Employee idea (as currently represented in the submission). No department challenge name is identified.

### 2. Which theme fits best?

**Public Safety Intelligence.** DrillLoop is a governed evidence-review workflow for emergency exercise evaluations. Its current MVP uses fixed, inspectable rules for finding candidates and requires a human reviewer to approve findings and corrective-action closure. Optional local AI can reword an action draft; it does not plan or execute operational decisions.

### 3. Idea title

**DrillLoop: Evidence-Linked Exercise Reviews and Action Closure**

### 4. One-line summary

**DrillLoop is a local-first prototype designed to help emergency-preparedness evaluators turn exercise records into evidence-linked After-Action Reports and Improvement Plans, with explicit human approval and evidence-backed corrective-action closure. Its deterministic workflow preserves source references and unresolved timing issues; a proposed pilot would test reporting effort, citation accuracy and follow-up completeness against existing practice.**

### 5. What problem are you solving?

The proposed first pilot segment is hospital preparedness teams. In one exercise-to-report workflow, evaluators reconcile notes, event logs, timelines, and transcripts to prepare an After-Action Report and Improvement Plan (AAR/IP). Findings can be difficult to verify later without exact source references, and corrective actions can remain incomplete when ownership, due dates, acceptance criteria, or closure evidence are missing.

The project materials contain no customer interviews, reporting-time baseline, exercise-frequency data, willingness-to-pilot evidence, or measured monetary cost. The operational problem and potential workload reduction remain hypotheses to validate with a hospital preparedness team. Candidate user: exercise evaluator or preparedness staff. Candidate report approver: preparedness lead or exercise sponsor. Budget owner and procurement path: not yet identified.

### 6. What is your AI solution?

DrillLoop is a local-first web prototype for the hospital exercise-to-report workflow. A user defines an exercise and its objectives, then imports notes, CSV event logs, JSON timeline/transcript records, or selectable-text PDFs. The system preserves the source and records a locator such as a CSV row, note line, PDF page, or transcript segment. It builds a timeline while leaving missing times unplaced and conflicting times unresolved.

The included MVP uses a fixed, deterministic workflow to extract observations, match the fictional scenario’s signals, map candidate findings to objectives, attach exact evidence IDs, draft corrective actions, and prepare an AAR/IP. Proposed findings remain visibly separate from evaluator-approved findings. A reviewer must approve or reject findings; action approval and closure have reviewer gates, and closure requires evidence.

Optional local extensions are available but are not needed for the demo: faster-whisper can transcribe audio when a compatible model is already installed locally, and a local Ollama model can reword an action the rules have already proposed. The project has not measured ASR accuracy, multilingual performance, speaker diarization, or local LLM quality. The sample transcript is pre-generated and includes a labeled synthetic recognition error.

The differentiation hypothesis is source-level evidence traceability combined with explicit reviewer decisions and closure evidence. Veoci advertises after-action reporting and corrective-action follow-up; D4H advertises emergency-team readiness software. The project has not compared either product against DrillLoop on the same exercise-to-report workflow, and traceability differentiation is not validated. A relevant Presight delivery advantage has not been established in the project materials.

### 7. Technology readiness

**Provisional self-assessment: TRL 4 on the conventional 1–9 scale; not independently established.**

The repository records a local web prototype with API, UI, persistent demo storage, evidence ingestion, timeline, proposed findings, reviewer decisions, action tracking, PDF export, automated tests, and a fictional end-to-end exercise. The technical check used one closed synthetic fixture. Prototype performance and TRL have not been independently validated from an operational deployment, customer pilot, user study, or real exercise records. Optional ASR/LLM paths were not benchmarked. The program’s TRL definitions may differ from the conventional scale.

### 8. Tags

Emergency preparedness, exercise evaluation, evidence traceability, human-in-the-loop AI, corrective action management, AAR/IP, local-first AI, hospital resilience

### 9. What are you submitting as?

**Prototype.** DrillLoop is a functional local web MVP, but it is not a hosted production service or an autonomous AI agent. The current analysis is a controlled workflow with deterministic rules and human review.

### 10. Expected impact

**Initial target segment:** hospital preparedness teams. **Primary user:** exercise evaluator or preparedness staff. **Potential report approver:** preparedness lead or exercise sponsor. **Budget owner:** not yet identified. Other possible future segments include municipal emergency-management teams, civil-defense organizations, airports, critical-infrastructure operators, exercise providers, and defense-support training organizations.

**Proposed pilot comparison:** prepare an AAR/IP from the same permitted exercise records using the current process and DrillLoop, then compare:

- Time to assemble an AAR/IP, measured against the organization’s existing process.
- Evaluator review and correction workload for proposed findings.
- Whether each finding has an accurate, usable source citation.
- Whether conflicting or missing times remain visible instead of being silently resolved.
- Completion of action ownership, due dates, acceptance criteria, reviewer decisions, and closure evidence.

No success thresholds are set; a pilot partner would define them against its baseline. The project has no measured staff time saved, labor-cost reduction, customer revenue, or field performance. The first commercial model to test is a **per-exercise pilot fee**, without a proposed price. Annual organizational subscriptions, private deployment, custom templates, and support services are additional unvalidated options. There are no recorded sales or signed commitments.

## Team and contact

### 11. Who is the lead?

- **Name:** [Not provided in project materials]
- **Email:** [Not provided in project materials]
- **Department:** [Not provided in project materials]
- **Function / role:** [Not provided in project materials]

The submission is represented as an individual idea. The submitter’s relevant experience, delivery capacity, and available time are not described in the project materials.

### 12. Individual or team submission?

**Submission mode:** Individual idea, as represented in the submission.

- **Team members and roles:** Not applicable to the individual submission.
- **Relevant experience and skills:** Not provided in project materials.
- **Available time / capacity:** Not provided in project materials.
- **Support needed:** hospital preparedness or continuity adviser; evaluator feedback; a permitted pilot environment and approved evidence; security and privacy review; and product/customer discovery. No adviser, pilot partner, or support commitment is recorded.

### Delivery and validation plan

1. Map one hospital preparedness team’s current exercise-to-report workflow and identify the evaluator, report approver, and budget owner.
2. Establish a baseline for reporting time, evidence verification, reviewer corrections, and corrective-action follow-up.
3. Compare current practice and DrillLoop on the same permitted exercise records, including missing timestamps, conflicting records, ambiguous notes, and transcription errors.
4. Agree pilot success thresholds with the partner, review findings with an emergency-preparedness adviser, and record results and limitations.

No delivery schedule, partner, adviser, or evaluation-team capacity is currently documented.

### Data governance and security status

The demo stores uploaded source bytes and extracted text in its configured database and records an audit history of reviewer actions. It uses a shared demo reviewer key. Production-grade identity and role-based access, tenant isolation, encryption, retention/deletion controls, malware scanning, and a security assessment are not implemented or evidenced. Local-first operation alone does not establish security. The packaged sample uses fictional evidence; no real patient or operational records were used in its benchmark.

### Commercial and delivery hypothesis

The first commercial model proposed for discovery is a per-exercise pilot fee. Willingness to pay, procurement ownership, delivery cost, and sales cycle have not been validated. No specific Presight capability or customer access advantage is evidenced in the project materials; any such advantage would need to be substantiated before inclusion in a final value proposition.

## Documents and prototype

### 13. Pitch deck

- [Editable 13-slide PowerPoint](DrillLoop_Pitch_Deck.pptx) — includes speaker notes on every slide.
- [Pitch deck PDF](DrillLoop_Pitch_Deck.pdf).

### 14. Idea document

- [Idea document PDF](DrillLoop_Idea_Document.pdf).
- [Editable idea document DOCX](DrillLoop_Idea_Document.docx).

### 15. Optional attachments (choose up to three)

Recommended attachments:

1. [Evaluation report PDF](DrillLoop_Evaluation_Report.pdf) — synthetic benchmark scope, metrics, and limitations.
2. [Technical design](DrillLoop_Technical_Design.md) — architecture, workflow, data model, and security boundaries.
3. [Architecture diagram PDF](DrillLoop_Architecture.pdf). The editable [SVG source](DrillLoop_Architecture.svg) is also available.

The synthetic benchmark data is in [`demo/benchmark_results.json`](demo/benchmark_results.json), and labeled fictional findings are in [`demo/ground_truth.json`](demo/ground_truth.json). These can replace an attachment if the form accepts raw data files.

### 16. Prototype evidence

- **Public code repository:** [https://github.com/deepeshaiml/DrillLoop](https://github.com/deepeshaiml/DrillLoop)
- **Screenshots:** [Overview](assets/DrillLoop_Demo_Overview.png), [Findings](assets/DrillLoop_Demo_Findings.png), and [Corrective Actions](assets/DrillLoop_Demo_Actions.png).
- **Live demo URL:** none is currently documented; the prototype runs locally.
- **Web build ZIP:** not currently prepared.

### 17. How should judges test it?

The project includes fictional demo records only and has not been validated for protected patient or operationally sensitive evidence.

**Docker path:** clone the repository, run `cp .env.example .env`, then `docker compose up --build`. Open `http://localhost:8000`. The demo reviewer name/key are `Exercise Reviewer` / `demo-reviewer`; these are laptop-demo credentials, not production authentication.

**Walkthrough:**

1. Select **Night Shift: Extended Power Loss** (`HOSP-PO-2026-01`).
2. Open the timeline. See the 09:02 power failure, 09:06 restoration, and the unresolved 09:10 / 09:11 acknowledgement conflict.
3. Open **Findings**. Inspect the proposed power-restoration finding and follow its links to `EL-01` and `EL-02` in the source log. Confirm it is marked proposed until a reviewer decides.
4. Review the communication-delay finding and the synthetic low-confidence transcript segment. The incorrect transcript wording is flagged; the response-time discrepancy relies on the independent event log.
5. Open **Corrective Actions**. See the intentionally missing owner. Assign a fictional demo owner if testing the approval flow; action approval requires an approved linked finding, owner, and due date.
6. Record fictional closure evidence and confirm that a reviewer decision is needed to close the action.
7. Export the AAR/IP PDF and inspect the separate observation, interpretation, evidence links, reviewer status, and action register.

Full setup and error-case details are in [`DEMO_GUIDE.md`](DEMO_GUIDE.md). There is no hosted demo URL at present. In the review that generated this feedback, the repository, screenshots, and documents were not available to the reviewer for inspection; prototype evidence therefore remains independently unverified in that review.

## Applicant details not present in the project materials

- Lead name, email, department, and function.
- Submitter experience, delivery capacity, and available time.
- Identified hospital pilot partner, report approver, and budget owner.
- Program-specific TRL definition and any independent TRL evidence.
- A substantiated Presight delivery advantage, if applicable.
