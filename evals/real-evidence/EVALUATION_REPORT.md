# DrillLoop public-document evaluation

21 November 2026 · Developer-authored labels · Independent adjudication **NOT PERFORMED**

## What the sources establish

- **LA25-PLAN, local PDF p. 23, and LA25-CEH, local PDF p. 26.** The schedule says “08:00 All Exercise starts” and “11:00 All Exercise ends.” Interpretation: scheduled clocks for July 24, 2025. Unknowns: actual start, actual end and observed participant actions. Decision: no application finding proposed.
- **LA25-EEG, local PDF p. 4.** “Staff was assigned their FIC/FRC role and responsibility.” Interpretation: a critical task in the evaluation guide. Unknowns: whether any participant actually completed it. Decision: no application finding proposed.
- **LA25-AAR, local PDF p. 7.** “Strength 1: [Observation statement]” is a template slot. Unknowns: completed observations and improvement decisions.
- **NWHRN-AAR, original PDF pp. 11 and 20.** “Area for Improvement 1: ICS/HICS Training.” Interpretation: a published evaluator conclusion, with a related training recommendation in the improvement plan. Unknowns: underlying primary observations, how broad the issue was, and whether the recommendation was implemented. Decision: no new application finding proposed.

Classification and links appear in the [source registry](SOURCE_REGISTRY.md). Private PDFs remain outside Git. The four County inputs were locally rendered from their publisher-linked Office files. The Northwest input was the unchanged original PDF.

## Measured outcomes

| Check | A · 2025 planning set | B · completed evaluator report |
| --- | --- | --- |
| Baseline import through API | 1/4 PDFs. Three refused with `INVALID_TIMESTAMP` on bracketed template prose. | 1/1 PDF |
| Final import and byte-identical download | 4/4 PDFs | 1/1 PDF |
| Exact sampled text on expected page | Baseline 3/13. Final 13/13 | Baseline and final 7/7 |
| Missing sampled passages after fix | 0/13 | 0/7 |
| Repeated sampled text on its expected page | 1 extra occurrence in 13 labels. The AAR/IP template repeats RE-13 in two sections on p. 7. | 0 extra occurrences in 7 labels |
| Parsed records | 1,890 across 77 locally rendered pages | 945 across 24 original pages |
| Scheduled clocks recovered and excluded from event chronology | 4/4 recovered. 0/4 presented as observed event times. | No labeled scheduled clock |
| Objective assessment | Two timing and two presence rules registered. 4/4 insufficient for performance after classification. Baseline falsely confirmed two expected tasks. | Two hand-configured report objectives, 2/2 require review. Independent performance rules **NOT SUPPORTED** on this corpus. |
| Unsupported deterministic proposals | Baseline 2/2, both cited valid EEG lines with the wrong evidentiary role. Final 0 proposals. | 0 proposals |
| Automatic approvals and closures | 0 finding approvals and 0 action closures | 0 finding approvals and 0 action closures |
| OCR | Selectable text on all four inputs | OCR ran on mixed page 1. 0.10 s OCR. No independent OCR transcript for error-rate scoring. |
| Local API timings | Upload with parse and persistence 191–478 ms per PDF. Analysis 4.53 ms round trip, 1.76 ms computed. Export 496 ms. | Upload with parse and persistence 605 ms. Analysis 3.03 ms round trip, 0.41 ms computed. Export 350 ms. |

Times describe one local API run, including its overhead. They do not estimate evaluator labor. The API requires one date and duration. Case B uses an explicitly described first-calendar-day indexing window for a multi-day source. That window does not enter scoring.

Every frozen text label was tied to a file, physical page, text-span hash, evidence role, and clock when present. NFC and collapsed whitespace account for PDF line layout. The test looks for exact contiguous words within extracted records. These are sample anchors, including four objective anchors in Case A and selected objectives, strength, improvement, conclusion and recommendations in B. The app’s objectives were configured by the evaluator. It did not automatically create those objectives or independently reconstruct the published findings.

**NOT EVALUABLE** on this corpus: raw-observation recall, population-wide extraction correctness or duplicates, observed time ordering, elapsed-time error, coverage of true or false conflicts, raw cross-source corroboration, independent findings precision/recall and exhaustive citation recall. The observed-time denominator is zero in both classified cases. The separate fictional rule and browser suites exercise observed timing and disagreements. No MSEL inject-level result or independent SME review was available.

## Local AI comparison

The application ran through cloud-disabled loopback Ollama 0.40.16 with the installed `qwen3.6:35b-a3b-coding-nvfp4` tag, normalized schema hash and prompt `phase4b-v5`. The driver requested temperature 0, thinking off, a 768-token output cap, 32 KiB bounded input and one request slot. The inventory digest is in the machine results. There was no prompt tuning against the frozen labels.

| Run | Actual output | Interpretation and limits |
| --- | --- | --- |
| Baseline full cases | 2/2 context-limited before inference | Large document uploads exceed the bounded record context. |
| Baseline research preview · EEG p. 4 | 2/2 target objectives produced `insufficient_evidence`, 0 citations, 3,039 input and 123 output tokens, 2.69 s | Safe abstention on expected tasks. |
| Baseline research preview · original AAR p. 11 | 1 advisory, 2/2 exact in-context citations, 2,561 input and 68 output tokens, 1.91 s | Located wording for the published ICS objective. No blind evaluation of outcomes. Original p. 11 was rendered as preview page 1 and the mapping is recorded. |
| Final full cases as classified references | 2/2 performance generation requests returned `AI_EVIDENCE_REQUIRED` without inference or persistent changes | Known reference purpose produces safe abstention. The full documents remain available for human source inspection. |
| Fictional instruction negative control | The model abstained and made no workflow change. It still cited the instruction-bearing line. | No approval override occurred. Exact wording checks accepted a semantically weak citation. This negative control does not establish broad adversarial robustness. |
| Real model, separate fictional browser run | 5 advisories, 10/10 exact citations, 2,989 input and 734 output tokens, 10.23 s, no exercise changes | Three corroborations were reasonable. The two contradiction labels require review. For OBJ-02, the role of runner vs. radio and event identity require reconciliation. For OBJ-04, one cited line repeats the two-minute claim and the other also supplies embedded clocks. The pair does not provide two direct conflicting duration assertions. |

Citation fidelity and semantic support are separate. None of the research preview suggestions was saved, promoted or approved. The browser review and promotion rehearsal used a scripted provider explicitly. The product retains human authority. No comparative quality gain, human time savings, or healthcare accuracy is established. The baseline Case A state comparison included the rejected direct DOCX probe’s upload audit event. Its false state flag is an instrumentation discrepancy. The corrected final run took its snapshot immediately before AI generation and found 2/2 state snapshots unchanged.

Artifacts: [first deterministic baseline](results/baseline-deterministic.json), [baseline local AI preview](results/baseline-hybrid.json), [final metrics](results/final.json), [browser and PDF checks](results/browser-verification.json), [frozen labels](reference-labels.json), [case setups](cases.json).

## Reproduce and adjudicate

1. Download the five public files from the manifest’s `download_url` fields into `.eureka-private/sources/` under their recorded filenames. Verify SHA-256 before using them. If an export changes upstream, acquire and version it separately. Full documents and traces remain private.
2. Render the four DOCX files with LibreOffice 26.8.1.1, using an isolated profile. The original downloads stay intact. Match the registered local derivation when using the preserved bytes. When re-rendering trusted matching originals, PDF metadata can change, so use the explicit `--allow-render-variance` option and check the recorded page mappings and new input hashes.

```sh
umask 077
mkdir -p .eureka-private/sources .eureka-private/derived .eureka-private/runs
soffice --headless "-env:UserInstallation=file://$(pwd)/.eureka-private/lo-replay" \
  --convert-to pdf --outdir .eureka-private/derived .eureka-private/sources/*.docx
.venv/bin/python scripts/evaluate_real_evidence.py --allow-render-variance \
  --output .eureka-private/runs/replay.json
```

3. For optional real inference, start a cloud-disabled loopback Ollama process and add `--model qwen3.6:35b-a3b-coding-nvfp4`. `--preview` is only for the disclosed one-page research probes in fresh exercises. The original baseline was `bea3de957afd6a8c405075387163b6020bd6fe28`. For a baseline replay use the evaluator and its registered JSON inputs against that code in an isolated checkout. Neither the baseline nor the final case uses the report’s conclusions as unseen ground truth.
4. For human adjudication, open the publisher source and the registered conversion where applicable. Verify the stable source ID, physical page, wording, evidence role, any explicitly stated clock and the context around the excerpt. Independently judge whether any assertion follows, while recording unsupported claims, gaps and disputes. Allowed judgments are **VERIFIED AGAINST ORIGINAL SOURCE**, **SUPPORTED BUT REQUIRES HUMAN INTERPRETATION**, **INSUFFICIENT EVIDENCE**, **CONTRADICTORY EVIDENCE**, **UNSUPPORTED**, **EXTRACTION FAILURE** and **NOT EVALUABLE**. Retain disagreements. Version new reference labels separately. No independent adjudicator participated in this run.
