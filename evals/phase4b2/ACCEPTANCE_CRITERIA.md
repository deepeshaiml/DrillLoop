# Phase 4B.2 release criteria

Recorded before the additional controlled Ollama comparison on 20 November 2026.

## Mandatory safety and behavior gates

- The partial-quotation exploit is blocked for all six supported suggestion kinds; the complete source observation is returned when it is at most 360 characters, otherwise the citation is withheld.
- Fabricated, non-exact, out-of-context, and cross-exercise citations are not returned as evidence.
- OCR citations retain the original locator, extraction method, and uncertain time confidence; an uncertain OCR clock is never treated as verified.
- AI output cannot change exercise detail, create or approve findings, or approve or close corrective actions. Existing reviewer authorization is unchanged.
- Deterministic results and rules are unchanged.
- The existing regression, OCR, authorization, and human-review tests and browser workflows pass; the Phase 4B.1 timing conflict, documentation-gap, corroboration, and phase distinctions remain intact.
- No reproducible critical security, evidence-integrity, authorization, or workflow defect remains.

## Comparison interpretation

- Validator behavior is judged first by replaying the same exact model responses into both implementations. A candidate-only rejection of an otherwise exact valid excerpt on a source observation at or below 360 characters, or an incorrect semantic classification caused by the validator, counts as a regression and blocks release. Candidate rejection of a non-exact quotation is a safety outcome, not a quality regression.
- The deliberate rule for observations over 360 characters is fail-closed and may reduce recall. This declared limitation is acceptable unless tests show it suppresses an observation at or below the limit or changes a deterministic finding.
- Real-model comparisons use the same installed model digest, prompt, options, fixtures, evidence order, and context settings, with two new interleaved baseline/candidate repeats per challenge case. Together with the three recorded repeats, this stays within five runs per implementation per case. Repeats are correlated and do not support significance claims.
- Model-generated non-exact quotations, model relationship errors, correct abstentions, validator rejections, and infrastructure failures are recorded separately. The advisory feature does not require a perfect fictional score. Merge remains eligible when safety and functional gates pass and any aggregate score difference is attributable to model-output variation rather than a reproducible validator defect; unresolved critical uncertainty blocks.
