# Phase 1 fictional evidence quality baseline

This baseline uses the existing `drillloop-evaluation/v1` schema and `scripts/evaluate_analysis.py`. Both cases and all reference labels are fictional, developer-authored, manually checked against their source files before analysis, and not independently adjudicated by domain experts. The source SHA-256 values are checked by the runner. The existing hospital and library datasets remain unchanged.

Run from the repository root:

```bash
.venv/bin/python scripts/evaluate_analysis.py --dataset evals/phase1/water-utility-v1.json
.venv/bin/python scripts/evaluate_analysis.py --dataset evals/phase1/transit-station-v1.json
```

## Recorded baseline

| Measure | Result |
|---|---:|
| Observations | 12/12; precision, recall, and F1 = 1.00 |
| Findings | 2/2 expected findings recovered; 0 false positives, 0 false negatives |
| Exhaustively labeled citations | 4/5 required references; precision 1.00, recall 0.80, unsupported rate 0.00 |
| Repeated identical citation references / duplicate finding codes | 0 / 0 |
| Source wording | 12/12 exact matches |
| Explicit event timestamps | 7/8 matched; one narrative timestamp was not extracted |
| Time confidence | 11/12 matched |
| Objective assessments, elapsed values, and configured thresholds | 6/6 matched; 0 calculation errors |
| Expected unknown-time cases | 4/4 retained |
| Expected unresolved timeline conflicts | 1/1 retained |

The one missing citation is `fictional_shift_notes.txt`, line 1: it repeats the alarm time in narrative text. The text parser preserves the wording but only extracts a timestamp at the start of a line, so this source receives no usable time and is omitted from the timed finding citation. The primary CSV source still supplies the correct 240-second calculation. The transit case retains competing 240- and 660-second intervals and does not produce a finding; the missing acknowledgement remains `insufficient_information`.

Precision and recall above describe only these small, closed synthetic fixtures. They are not independently validated accuracy estimates. The zero unsupported-citation rate is calculable here because these labels explicitly enumerate every expected source reference for each expected finding; unmatched citations in a future non-exhaustive label set must remain unclassified for review.
