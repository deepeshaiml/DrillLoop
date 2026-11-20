# Phase 4B.1 conflict regression and held-out evaluation

## Reproduced failures

- **Transit timing.** CSV record `TS-02`, `transit_control_log.csv` row 3, reports the opening at 09:04. `fictional_dispatcher_notes.txt` line 1 attributes 09:11 to the platform observer, repeats the desk's 09:04 value, and says the opening time remains unresolved. Both records were available in source order. In the full baseline rerun the model returned the timing disagreement once and ordinary alarm and opening context twice. A separate raw-reply trace showed the model submitting a valid timing pair after a same-source corroboration. The old validator downgraded the first result to relevance and skipped the later result for that objective.
- **Dispatch acknowledgement.** The request in `fictional_dispatch_log.txt` line 3 and the missing entry in `fictional_dispatch_notes.txt` line 2 passed exact quotation checks. The raw reply assigned `contradiction` to the pair. Neither source asserts whether the supervisor acknowledged. The old validator checked the pair's shape and provenance without distinguishing a documentation gap from a denial of the event.

An initial candidate added rule-matched completion cues and clock mentions to the prompt payload. The model still missed the timing disagreement, so the candidate also added server-side checks. On the first held-out set the candidate introduced corroboration errors on separate phases and an unsupported causal hypothesis. The validator-only recovery restores the original Phase 4B prompt and payload. It can retain a later grounded contradiction over a weaker relevance result. It can also surface an explicit timing dispute when one recorded completion and one independently sourced note match the configured rule, the note explicitly marks the time disputed, both clocks appear in separately attributed completion clauses, and one repeats the recorded value. Otherwise it leaves event association to the model and evaluator. It checks the original clause for a quoted documentation gap so cutting off a negation does not turn missing paperwork into a claim about the event. When a cited, rule-matched start has a unique independent account with the same exact clock, the validator can retain both citations as possible corroboration. A speculative source cannot corroborate a causal explanation. OCR citations retain their original uncertainty, including when a timing abstention needs one uniquely matched completion excerpt.

## Method

The regression suite at `evals/phase4b` is unchanged. The held-out suite has eight new fictional exercises and nine labeled objectives. It includes conflicting and compatible timestamps, phases, missing acknowledgements, a substantive denial, repeated incidents, a scanned time, unsupported causality, paraphrased corroboration, and an incomplete result. The labels were authored from the source records before implementation tuning. There was no independent reviewer. The source and label checksums were frozen in `SHA256SUMS`. Development comparisons initially used the existing regression suite. The first held-out results then informed the decision to restore the Phase 4B prompt and payload. The first set therefore also serves as development evidence. A separate set under `confirmation/` was authored and checksummed before writing the recovery. It contains five fictional exercises and nine labeled objectives. All labels are developer-authored.

The baseline was the open PR head `dc6210119a93fa34148c4e55e0d9e3e3520e6ac1`. Both versions used the same 0.40.16 Ollama daemon with cloud disabled and the installed `qwen3.6:35b-a3b-coding-nvfp4` model. The final candidate and baseline used the same `phase4b-v5` prompt and structured response schema. The model digest and exact prompt hashes are in the verification record. Both requested context 8,192, temperature 0, generation limit 2,048, synchronous structured output and thinking disabled. The application input limit was 12,000 bytes and the deadline was 60 seconds. Each version used three repeat inferences on each staged exercise. Repeats share fixtures and are correlated.

Run `python scripts/evaluate_hybrid_ai.py --suite phase4b1 --repeat 3 --output /tmp/held-out.json` with AI enabled against the trusted local Ollama daemon. Use `--backend-root /path/to/baseline-checkout` and a new output path for the baseline. Use `--suite phase4b` for the regression collection and `--suite phase4b1-confirmation` for the fresh held-out confirmation. To diagnose a specific fictional exercise, use `--case` and `--capture-model`. All requests use disposable SQLite and the normal scoped API. The runner measures model citation attempts separately from source excerpts the advisory validator constructs directly from the scoped records.

## Results

Each cell compares the current PR head rerun with the validator-only candidate. The published Phase 4B run previously scored 45/51 on the regression set. The baseline rerun scored 42/51 with the same model and requested settings. The runtime stages new source identifiers in each run. [Per-case results, telemetry, hashes and raw baseline examples](verification-2026-11-20.json)

| Measure | Regression suite, 7 exercises | First set, 8 exercises | Fresh confirmation, 5 exercises |
| --- | ---: | ---: | ---: |
| Target behaviors | 42/51 → 51/51 | 18/27 → 24/27 | 18/27 → 21/27 |
| True conflicts | 4/6 → 6/6 | 6/6 → 6/6 | 6/6 → 6/6 |
| False conflicts | 4/45 → 0/45 | 3/21 → 0/21 | 0/21 → 0/21 |
| Cross-source matches | 6/6 → 6/6 | 3/3 → 3/3 | 3/3 → 3/3 |
| Abstention precision | 29/29 → 33/33 | 9/9 → 15/15 | 9/9 → 12/12 |
| Abstention recall | 29/33 → 33/33 | 9/18 → 15/18 | 9/18 → 12/18 |
| Unsupported classifications | 9/28 → 0/21 | 6/18 → 3/15 | 9/18 → 6/15 |
| Exact model citations | 78/78 → 75/75 | 42/48 → 42/42 | 45/45 → 45/45 |
| OCR uncertainty preserved | 3/3 → 3/3 | 0/3 → 3/3 | 3/3 → 3/3 |
| Complete state preserved | 21/21 → 21/21 | 24/24 → 24/24 | 15/15 → 15/15 |
| Median request latency | 3.71 s → 3.30 s | 1.84 s → 1.85 s | 2.04 s → 3.22 s |
| Median input / output tokens | 1,242 / 265 → 1,220 / 260 | 795 / 138 → 794 / 145 | 956 / 146 → 949 / 246 |

### Per-case errors and remaining limits

- The fresh baseline missed the transit disagreement in two repeats, called the dispatch acknowledgement gap a contradiction in all three, called the historical inspection gap different phases in all three, and misclassified one other acknowledgement gap. The validator-only candidate passed both named cases and all other regression labels in all three repeats.
- On the first challenge set, the baseline called `FORM-ACK` contradictory, selected irrelevant context for `ROOM-ID`, and returned no accepted result for `SCAN-TIME`. The discarded prompt candidate also called the distinct cooling phases and the speculative lift cause corroboration. The final validator-only candidate preserved the phase distinction and causal abstention. Its only remaining miss on this set was `ROOM-ID`, where it cited both room releases without abstaining on which incident the witness meant.
- On the fresh confirmation set, both versions called the isolation and return-to-service records corroboration for `PANEL-STAGES`. Both used that pair for `PANEL-ID` even though the unnumbered release concerns a different set of records. Each miss occurred in all three repeats. The candidate abstained on `WEIR-TIME` while preserving the OCR uncertainty. The baseline had labeled that pair corroboration. There were no new critical case errors in the confirmation run.

The timing checks cover a narrow pattern of objective-matched evidence. The model can still misassociate events with similar wording or give the wrong relationship label. OCR may misread identifiers and times. The image source and original extraction metadata remain visible to the reviewer. These fictional results do not establish accuracy on operational exercises.
