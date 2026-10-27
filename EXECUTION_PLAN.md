# DrillLoop Execution Plan

## Goal
Deliver a runnable, offline-capable fictional hospital power-outage exercise demo with evidence ingestion, traceable timeline, proposed findings, human review, corrective actions, and AAR/IP export, alongside the requested technical, evaluation, business, and pitch materials.

## Work sequence
1. Inspect the empty starter directory, establish repository rules and this plan.
2. Verify current official framework versions, model licenses, FEMA HSEEP guidance, competitor positioning, and public AAR examples.
3. Design the evidence/finding/action schema and synthetic scenario with labeled ground truth and edge cases.
4. Build a FastAPI service with persistent SQLite default / PostgreSQL Compose option, file parsers, deterministic evidence-grounded analysis, review and corrective-action endpoints, and PDF export.
5. Build a React/TypeScript judge-facing UI for sample exercise, evidence upload, timeline, evidence-linked finding review, action tracking, and report download.
6. Add demo seed data, Docker setup, automated tests, benchmark script, README and demo guide.
7. Run tests and actual benchmark; record results and limitations.
8. Generate editable DOCX and PPTX with meaningful notes, PDF exports, architecture SVG, business/evaluation PDFs, and verify files/rendered slides.
9. Finalize PROGRESS.md with commands, outputs, test results, and known limitations.
10. Review every reader-facing artifact for plain-language definitions, a worked evidence example, consistent scenario details, and an AI-agent safety example; regenerate and visually recheck PDFs and slides.

## Acceptance checks
- Fresh local setup instructions work without cloud credentials.
- Synthetic evidence generates only source-supported proposed findings with citation references.
- Conflicting/absent times remain uncertain; inaccurate reported response time is flagged against source evidence.
- Finding approval/rejection and action closure are reviewer-controlled and auditable.
- Reports separate observed facts, interpretation, and actions.
- Requested deliverable files exist and are readable; PPTX notes exist on all slides.
