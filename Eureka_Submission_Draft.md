# Eureka Submission Draft — DrillLoop

Use this as a copy-ready draft for the Eureka form. It is based on the project files and recorded synthetic benchmark. Text marked **Confirm** needs the submitter’s own information or a decision before submission. Do not turn estimates, proposed pilots, or synthetic results into claims about real users.

## Idea details

### 1. What are you submitting?

**Confirm one:**

- [ ] Employee idea
- [ ] Department challenge — challenge name: **[Confirm name]**

The project materials do not establish which submission route applies.

### 2. Which theme fits best?

**Recommended: Agentic AI for Mission-Critical Ops.** DrillLoop supports the review of emergency exercise evidence and corrective actions. Describe it as a human-controlled AI-assisted workflow: the current MVP uses fixed, inspectable rules for findings; optional local AI can reword an action draft, but cannot create evidence, approve a finding, or close an action. It is not an autonomous operational decision-maker.

### 3. Idea title

**DrillLoop: Evidence-Linked Emergency Exercise Evaluation**

### 4. One-line summary

**DrillLoop turns emergency exercise notes and logs into source-linked finding drafts that evaluators can review and track through verified corrective-action closure.**

### 5. What problem are you solving?

After an exercise, evaluators in hospitals and emergency-management organizations may need to reconcile notes, event logs, timelines, and transcripts before writing an After-Action Report and Improvement Plan (AAR/IP). Findings can be difficult to verify later if the report does not point back to the exact source record, and improvement tasks can stall when an owner, due date, or completion evidence is missing.

DrillLoop is intended to reduce the effort of assembling and checking this material and make follow-up more traceable. **The project has not measured how often this occurs at a customer organization, the hours it consumes, or its monetary cost.** Do not state a quantified cost or saving without customer-baseline evidence.

### 6. What is your AI solution?

DrillLoop is a local-first web prototype. A user defines an exercise and its objectives, then imports notes, CSV event logs, JSON timeline/transcript records, or selectable-text PDFs. The system preserves the source and records a locator such as a CSV row, note line, PDF page, or transcript segment. It builds a timeline while leaving missing times unplaced and conflicting times unresolved.

The included MVP uses a fixed, deterministic workflow to extract observations, match the fictional scenario’s signals, map candidate findings to objectives, attach exact evidence IDs, draft corrective actions, and prepare an AAR/IP. Proposed findings remain visibly separate from evaluator-approved findings. A reviewer must approve or reject findings; action approval and closure have reviewer gates, and closure requires evidence.

Optional local extensions are available but are not needed for the demo: faster-whisper can transcribe audio when a compatible model is already installed locally, and a local Ollama model can reword an action the rules have already proposed. The project has not measured ASR accuracy, multilingual performance, speaker diarization, or local LLM quality. The sample transcript is pre-generated and includes a labeled synthetic recognition error.

The product’s positioning hypothesis is source-level evidence traceability combined with explicit reviewer decisions and closure evidence. Existing products already advertise AAR and corrective-action functions, so do not claim those functions alone are unique. The differentiator still needs customer and competitor validation.

### 7. Technology readiness

**Provisional self-assessment: TRL 4, if the Eureka form uses the conventional 1–9 scale. Confirm this against the program’s definitions before submitting.**

Evidence for this provisional level: a working local web prototype with API, UI, persistent demo storage, evidence ingestion, timeline, proposed findings, reviewer decisions, action tracking, PDF export, automated tests, and a fictional end-to-end exercise. The recorded technical check used one closed synthetic fixture. There has been no operational deployment, customer pilot, user study, or validation with real exercise records. Optional ASR/LLM paths were not benchmarked.

### 8. Tags

Emergency preparedness, exercise evaluation, evidence traceability, human-in-the-loop AI, corrective action management, AAR/IP, local-first AI, hospital resilience

### 9. What are you submitting as?

**Recommended: Prototype (web app).** It is also a web application, but the submission should not call it a production-ready AI agent. The current analysis is a controlled workflow with deterministic rules and human review.

### 10. Expected impact

**Target users:** hospital preparedness and safety teams, municipal emergency-management teams, civil-defense organizations, airports, critical-infrastructure operators, exercise providers, and defense-support training organizations.

**Potential outcomes to measure in a pilot:**

- Time to assemble an AAR/IP, measured against the organization’s existing process.
- Evaluator review and correction workload for proposed findings.
- Whether each finding has an accurate, usable source citation.
- Whether conflicting or missing times remain visible instead of being silently resolved.
- Completion of action ownership, due dates, acceptance criteria, reviewer decisions, and closure evidence.

These are proposed pilot measures, not demonstrated customer outcomes. The project has no measured staff time saved, labor-cost reduction, customer revenue, or field performance. Candidate commercial models in the business case include per-exercise pricing, annual organizational subscriptions, private deployment, custom templates, and support services; these are options to validate, not current sales or signed commitments.

## Team and contact

### 11. Who is the lead?

- **Name:** [Confirm]
- **Email:** [Confirm]
- **Department:** [Confirm]
- **Function / role:** [Confirm]

Do not infer identity or contact details from a GitHub username or local account name.

### 12. Individual or team submission?

**Confirm:** [Individual / Team]

- **Team members and roles:** [Confirm names and roles, if team]
- **Relevant experience and skills:** [Confirm from the actual people; the project’s requested agent roles do not establish human team credentials]
- **Available time / capacity:** [Confirm]
- **Support needed:** preparedness or hospital-continuity subject-matter review; evaluator feedback; a permitted pilot environment and synthetic/de-identified evidence; security and privacy review; and product/customer discovery. These are support needs to consider, not confirmed commitments.

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
3. [Architecture diagram](DrillLoop_Architecture.svg).

The synthetic benchmark data is in [`demo/benchmark_results.json`](demo/benchmark_results.json), and labeled fictional findings are in [`demo/ground_truth.json`](demo/ground_truth.json). These can replace an attachment if the form accepts raw data files.

### 16. Prototype evidence

- **Public code repository:** [https://github.com/deepeshaiml/DrillLoop](https://github.com/deepeshaiml/DrillLoop)
- **Screenshots:** [Overview](assets/DrillLoop_Demo_Overview.png), [Findings](assets/DrillLoop_Demo_Findings.png), and [Corrective Actions](assets/DrillLoop_Demo_Actions.png).
- **Live demo URL:** none is currently documented; the prototype runs locally.
- **Web build ZIP:** not currently prepared.

### 17. How should judges test it?

The project includes fictional demo records only. Do not upload patient, protected, or operationally sensitive evidence.

**Docker path:** clone the repository, run `cp .env.example .env`, then `docker compose up --build`. Open `http://localhost:8000`. The demo reviewer name/key are `Exercise Reviewer` / `demo-reviewer`; these are laptop-demo credentials, not production authentication.

**Walkthrough:**

1. Select **Night Shift: Extended Power Loss** (`HOSP-PO-2026-01`).
2. Open the timeline. See the 09:02 power failure, 09:06 restoration, and the unresolved 09:10 / 09:11 acknowledgement conflict.
3. Open **Findings**. Inspect the proposed power-restoration finding and follow its links to `EL-01` and `EL-02` in the source log. Confirm it is marked proposed until a reviewer decides.
4. Review the communication-delay finding and the synthetic low-confidence transcript segment. The incorrect transcript wording is flagged; the response-time discrepancy relies on the independent event log.
5. Open **Corrective Actions**. See the intentionally missing owner. Assign a fictional demo owner if testing the approval flow; action approval requires an approved linked finding, owner, and due date.
6. Record fictional closure evidence and confirm that a reviewer decision is needed to close the action.
7. Export the AAR/IP PDF and inspect the separate observation, interpretation, evidence links, reviewer status, and action register.

Full setup and error-case instructions are in [`DEMO_GUIDE.md`](DEMO_GUIDE.md). For judges who cannot run Docker, use the screenshots and public repository; there is no hosted demo URL at present.

## Confirm before submission

- Choose employee idea versus department challenge, including challenge name if applicable.
- Confirm the lead’s name, work email, department, and function.
- Confirm individual/team status, actual team members, skills, and available time.
- Verify the Eureka program’s TRL definitions and accept or revise the provisional TRL 4 assessment.
- Decide whether the recommended theme fits the panel’s taxonomy.
- Check the upload requirements and attach the linked PDF/PPTX/SVG files from the repository.
- Keep the synthetic benchmark framed as a technical check of one fixture; do not state measured human savings or real-world accuracy.
