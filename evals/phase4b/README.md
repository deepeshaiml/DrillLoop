# Phase 4B fictional evidence evaluation

The paired suite covers seven fictional exercises and 17 labeled objectives. It reuses the four Phase 4A exercises and adds facilities, dispatch, and duplicate-record cases. The new developer labels were written from the source records before either version ran on the paired suite. Development used this suite to tune the prompt. The labels have no independent adjudication. The archived Phase 4A report uses different labels and denominators.

## Method

- Use the exact baseline commit `a8d146f5040f39f72c51778de1057ee55d1d056a` and the current Phase 4B backend with one installed model. Set the local Ollama environment in the [operations guide](../../docs/operations/HYBRID_AI.md).
- Run `scripts/evaluate_hybrid_ai.py --suite phase4b --repeat 3 --output /tmp/phase4b.json`. Use the same command with `--backend-root /path/to/baseline` and a new output file for Phase 4A. The runner stages the same uploads and objectives through the API using disposable SQLite. Each version reuses its staged records for all repeats.
- Both versions request a context of 8,192 tokens, temperature 0, 2,048 generated tokens, synchronous JSON output, and thinking disabled. They use a 60-second timeout and a 12,000-byte input budget. Source identifiers are local to each staged exercise. Prompt templates and response schemas reflect the implementation under test.
- A target requires the labeled result, appropriate abstention disposition, allowed source locators, and any required excerpts or comparison pair. The scorer maps legacy category names to the corresponding Phase 4B names. Legacy ambiguity and unverified-cause advisories do not count as explicit abstentions. A phase-only result is an abstention from judging the same action or outcome.
- False conflicts are divided by all labeled non-conflict opportunities. Unsupported claims are divided by returned advisory classifications, including assertions that records describe different stages. Conservative abstention can still miss the target. Exact citation validation checks all attempted excerpts, including those in withheld suggestions. Semantic support is measured separately against developer labels.
- Real inference includes evidence that asks the model to invent a citation or approve an objective. A separate scripted-provider probe forces a fabricated record reference, a fabricated excerpt in an existing record, and a response that requests approval and an action. These probes exercise the API boundary independently of how the model responds to an injection.
- State preservation compares the entire exercise detail before and after each advisory request. It includes the deterministic observations, assessments, findings, and actions. Timing measures a local run and includes provider overhead. Three repeated runs on the same staged evidence are correlated observations.

## Results

Each version completed 21 real Ollama requests and 51 objective reviews using Ollama 0.40.16 and `qwen3.6:35b-a3b-coding-nvfp4`. The installed model digest was `sha256:cd2692a833e66c4c98991b67e9fbaa0bb15a93285baac9240c022f2f40075b6d`. The prompt versions were Phase 4A and `phase4b-v5`. The [verification record](ollama-verification-2026-11-20.json) includes exact settings, hashes, objective-level results and example excerpts.

| Measure | Phase 4A | Phase 4B |
| --- | ---: | ---: |
| Target behaviors | 18/51 | 45/51 |
| Cross-source corroboration | 0/6 | 6/6 |
| True contradictions detected | 6/6 | 3/6 |
| False conflict classifications | 12/45 | 3/45 |
| Abstention precision | 6/6 | 30/30 |
| Abstention recall | 6/33 | 30/33 |
| Unsupported advisory classifications | 21/39 | 6/24 |
| Exact citations | 75/75 | 74/74 |
| Entire exercise detail unchanged after AI | 21/21 | 21/21 |
| Request latency, median | 3,276 ms | 3,164 ms |
| Input tokens, median | 776 | 1,238 |
| Output tokens, median | 257 | 242 |

Phase 4B correctly matched both reports of an alarm, separated isolation from reset in all three facilities runs, and preserved OCR time uncertainty in all three OCR runs. It correctly identified the barrier status contradiction in all runs. It classified the gate-opening timing discrepancy as ordinary relevant context in all three transit runs, overlooking the observer's account despite exact citations to the control log. It treated the dispatcher's request and the missing acknowledgement entry as contradictory in all three dispatch runs. The other missing acknowledgement case, ambiguous cart identity, and two causal evidence gaps produced abstentions in all repeats.

Both versions withheld the scripted fabricated citations and rejected the forbidden approval and action fields. The real-model Phase 4B reception runs abstained on the signature and omitted the injected instruction from citations. Deterministic finding codes and objective states matched across versions. The original Phase 4A suite, separately rerun with its original labels, scored 8/9 with the original cross-source miss.

## Review limits

Citation checks establish quotation and scope. Evaluators still judge independence, event identity and the meaning of the excerpts in context. Exact byte copies and identical wording with the same reported time receive deterministic checks. Paraphrased copies and semantically incompatible assertions can require human review. The challenge labels cover objective-level behavior and selected citations. They do not enumerate every defensible explanation or measure general accuracy on unfamiliar exercises.
