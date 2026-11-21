# Eureka executive questions

| Question | Answer |
| --- | --- |
| What problem does this solve? | Evaluators reconcile scattered records to decide what happened and what needs improvement. Follow-up work can lose its connection to the evidence and reviewer decision. |
| Who uses it? | Hospital preparedness leads, exercise evaluators, and the people who verify corrective actions. |
| Who would pay? | A hospital or coalition preparedness program is the initial buyer hypothesis. Budget ownership, purchasing process and willingness to pay need discovery. |
| What is different from an AAR/IP template? | The record preserves evidence at page, line, row or segment level, and links it to findings, decisions, action owners and closure evidence. Comparison with current tools remains open. |
| Why use AI with rules? | Rules work well for explicit configured checks. A local model can point the evaluator to potentially related narrative records. Its review cost and incremental benefit need measurement. |
| How do you limit hallucinations? | The system verifies citations against stored wording, enforces source purpose and review states, and exposes unknowns. Reviewers still decide whether a quote supports the interpretation. |
| Can the model approve a finding? | No. A human accepts a candidate, separately promotes it to a proposed finding, then makes an authorized finding decision. Action approval and closure also require human decisions. |
| How are citations checked? | DrillLoop retains the file hash and bytes, extracted observation, original locator and extraction method. For AI output, it resolves the record and checks contiguous wording before displaying its context. |
| What if sources disagree? | Unresolved timing disputes stay visible with their source links. A person can determine whether the records describe the same event or different stages. |
| Will it run offline? | The built local demo runs offline. Optional local Ollama needs a preinstalled model and a cloud-disabled loopback daemon. |
| Can it process scans? | Yes, within the PDF and OCR budgets. Page references and uncertainty help reviewers check the original. Image-text and multilingual accuracy remain unmeasured on representative data. |
| How accurate is it on real records? | Twenty of 20 sampled passages appeared on labeled pages. The cases used public plans and a published evaluator report. Participant-performance accuracy and independent expert agreement remain unmeasured. |
| What can safely be uploaded? | This evaluation uses permitted public materials and fictional records. Before a pilot, the participating organization must approve data scope, access, retention and the security boundary. |
| How long to produce a report? | We measured local export latency on the tested files. Evaluator preparation, verification and editing time have yet to be compared with a manual baseline. |
| What is the proposed pilot? | Two or three stakeholders, one permitted exercise, manual and assisted review, plus independent checking of evidence and decisions. |
| What does it cost to operate? | Local rules have no per-request model API cost. Staff time, hardware, support and deployment costs have yet to be measured for a hospital pilot. |
| What is still unvalidated? | Primary evaluator-record performance, independently adjudicated accuracy, workflow savings, adoption, willingness to pay, and production deployment suitability. |
| What would the next investment fund? | Evaluator discovery, permitted primary exercise data, independent adjudication, and a paired time-and-quality study. |

[Proposed pilot and KPIs](EUREKA_PILOT_PROPOSAL.md) · [Measured results](../../evals/real-evidence/EVALUATION_REPORT.md)
