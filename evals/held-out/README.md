# Held-out evaluation set

`synthetic-library-v1.json` and its source CSV form a second, fictional evaluation set. Its labels were recorded before the one-time framework run and were not used to tune the analysis rules. Preserve this dataset and its result as a hold-out; changes prompted by its results require a new revision and a separately held-out set.

This is a process hold-out only. The scenario and labels are authored by the project team, are not independently adjudicated, contain no real exercise records, and do not establish real-world accuracy. The test has one exercise, one CSV source, two objectives, and deterministic rules.

Run from the repository root with the isolated evaluator:

```bash
.venv/bin/python scripts/evaluate_analysis.py \
  --dataset evals/held-out/synthetic-library-v1.json
```

The runner verifies the source SHA-256, creates a private temporary SQLite database, uploads only the fictional fixture, and removes that database on exit. Do not add confidential records to this directory.
