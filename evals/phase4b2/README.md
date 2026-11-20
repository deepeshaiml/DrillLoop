# Phase 4B.2 fictional citation-context regression

`citation_cases.json` contains fictional observations and developer-authored expected
full quotations. These examples were authored before the final regression run and
their SHA-256 digest is recorded in `SHA256SUMS`. They have not been independently
adjudicated. The fake-provider API test applies each excerpt to every supported
classification and checks that the complete observation and source locator survive.
Separate tests exercise fabricated and short excerpts, long records, OCR metadata,
cross-exercise isolation, conflicting suggestions, and exercise-state preservation.

The validator checks the model's excerpt against an observation from the authorized
exercise and displays the whole extracted observation when it is at most 360
characters. Longer observations are withheld, even if a sentence within them might
be useful, because a qualification could occur elsewhere in the observation. The
limit can therefore reduce recall. Source links still lead to the original document;
OCR text and times must be checked against the source. Context outside an extracted
observation can still matter, and complete quotation does not prove that the model's
relationship label is semantically correct. Human review remains mandatory.
The checked-in Phase 4A/4B/4B.1 fictional text and CSV records reviewed for this
release contain no observation line longer than the limit. The adversarial long
record case is synthetic and intentionally withheld. The limit may still suppress
useful observations in other exercises; this comparison does not estimate that rate.

Citation counters continue to count references attempted and accepted by validation;
a reference withheld because its full observation is too long is not matched. A
server-added citation does not count as a model citation attempt. The rejected count
continues to include candidate results withheld or superseded by the one-result-per-
objective contract.

## Final release assessment — 20 November 2026

The predeclared criteria are in `ACCEPTANCE_CRITERIA.md`. The deterministic
comparison replayed 15 identical fictional responses through the original PR
head and the correction; response-free outcomes are in `validator-comparison.json`.
The controlled real-model summary, per-case outcomes, request settings, and hashes
are in `controlled-real-model-summary.json`. Raw traces from the final two
interleaved runs remain in `/tmp/drillloop-4b2-final.kjqLyV`, a mode-700 temporary
directory outside the repository. Earlier targeted OCR traces remain local and are
excluded from the commit.

### Deterministic validator comparison

- For the confirmed handoff case, the original validator returned `handoff entry was found in the notebook.` as positive-looking evidence. Phase 4B.2 returned the complete source sentence, `No matching handoff entry was found in the notebook.` The identical exact substring was tested under all six classifications.
- With `corroboration`, the original returned that partial quotation as a possible corroboration. Phase 4B.2 retained the complete record and abstained on the documentation gap. For contradiction and different-phase proposals, both validators abstained when the complete source showed that the second account was only missing documentation. Unknown and insufficient-evidence results retained the full source in both.
- A valid negative outcome, `The emergency gate did not open.`, remained available as evidence in both. A fabricated positive quotation was rejected in both. For an observation longer than 360 characters, the original returned a partial quotation and Phase 4B.2 withheld it under the predeclared limit. This is the known recall trade-off.
- Replaying six captured OCR replies produced identical citation acceptance and classifications in both validators: four replies with exact source wording were accepted with OCR uncertainty, and two replies that quoted `source_time` metadata rather than source text were rejected. Existing API tests also confirm exercise scoping and unchanged exercise state. No valid citation at or below the output limit was incorrectly rejected in the deterministic comparison.

### Controlled local Ollama comparison

The same local Ollama 0.40.16 daemon used `qwen3.6:35b-a3b-coding-nvfp4`
(digest `cd2692a833e66c4c98991b67e9fbaa0bb15a93285baac9240c022f2f40075b6d`),
cloud disabled, `phase4b-v5` prompt and hash, temperature 0, 8,192 context,
2,048 output tokens, thinking disabled, 12,000-byte application input limit,
identical fictional fixtures and evidence ordering, and disposable SQLite.
Two new paired runs alternated baseline/candidate order for each case and were
added to the three recorded complete-suite repeats per version. The suite totals
below therefore use five full runs per implementation; repeated cases are
correlated, and an earlier targeted OCR diagnostic is reported separately rather
than added to those totals.

| Measure | Original PR head | Phase 4B.2 |
| --- | ---: | ---: |
| Target behaviors | 40/45 | 36/45 |
| True conflicts | 10/10 | 10/10 |
| False conflicts | 0/35 | 0/35 |
| Cross-source matches | 5/5 | 5/5 |
| Expected abstentions | 25/30 | 21/30 |
| Unsupported claims | 5/25 | 5/25 |
| Exact citation attempts | 77/77 | 73/81 |
| OCR uncertainty preserved on returned suggestions | 5/5 | 1/5 |
| Exercise state unchanged | 40/40 | 40/40 |

The entire four-point target-score difference is in `SCAN-TIME`: baseline 5/5,
candidate 1/5. `ROOM-ID` remains a miss in both at 0/5. The new runs produced
exact OCR citations in both versions for repeat 4. In repeat 5, the candidate
model instead returned `source_time: 13:18` and `source_time: 13:13` as citations;
neither is a substring of the supplied observations. Both validators reject
those same captured replies, leave the objective unassessed, and avoid claiming
a verified OCR time. No request timed out or failed at the infrastructure layer.

An earlier, separate three-repeat targeted OCR diagnostic varied in the opposite
direction: it preserved the OCR abstention once on the baseline and three times
on the candidate. The same-response replay shows that the validator change does
not cause these inconsistent results. The model sometimes quotes the source
records correctly and sometimes copies metadata labels as if they were source
text. The scores are descriptive of a small fixed fictional set, not a reliable
measure of accuracy. This model-quality uncertainty is accepted for the optional,
disabled-by-default advisory path; no safety or functional gate failed.

The three-repeat Phase 4B.2 regression and fresh confirmation remain 51/51 and
21/27 respectively. The fresh confirmation retains the two documented panel
event-association errors. These developer-authored fictional results do not
establish general semantic accuracy or operational performance. No labels or
source fixtures were changed to improve a score.
