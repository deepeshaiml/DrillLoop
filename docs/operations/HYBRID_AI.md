# Hybrid AI assistance

Findings shows AI assistance for administrators and evaluators with a grant to the selected exercise. The existing **Run evidence analysis** action runs the deterministic rules and creates proposed findings. **Generate AI suggestions** separately reviews extracted narrative records and shows temporary suggestions with source links. Only the existing human review workflow can change findings or actions.

## Local setup

Use a trusted Ollama daemon on the same host or network namespace as the native DrillLoop API. Confirm the exact installed model tag with `ollama list`. Ollama 0.40.16 was verified with the locally installed `qwen3.6:35b-a3b-coding-nvfp4`. Choose an installed model approved for your use. DrillLoop never downloads a model.

For a separate local Ollama instance, start it with cloud features and request logging disabled. Use a free loopback port.

```sh
OLLAMA_HOST=127.0.0.1:11435 OLLAMA_NO_CLOUD=1 OLLAMA_DEBUG_LOG_REQUESTS=0 ollama serve
```

Set the variables in the API process environment before starting it. The Compose sample does not forward these options to the container. An Ollama process on the host would be outside a Compose API container’s loopback namespace.

```sh
export DRILLLOOP_AI_ENABLED=1
export DRILLLOOP_AI_PROVIDER=ollama
export DRILLLOOP_AI_ENDPOINT=http://127.0.0.1:11435
export DRILLLOOP_AI_MODEL='<installed-name:tag>'
```

| Variable | Default | Details |
| --- | --- | --- |
| `DRILLLOOP_AI_ENABLED` | `0` | Set to `1` to enable |
| `DRILLLOOP_AI_PROVIDER` | `ollama` | Local provider |
| `DRILLLOOP_AI_MODEL` | Empty | Exact locally installed tag, without a registry prefix |
| `DRILLLOOP_AI_ENDPOINT` | `http://127.0.0.1:11434` | HTTP origin using `127.0.0.1` or `[::1]` and an explicit port |
| `DRILLLOOP_AI_TIMEOUT_SECONDS` | `60` | End-to-end provider request deadline, 1–180 seconds |
| `DRILLLOOP_AI_MAX_INPUT_BYTES` | `12000` | UTF-8 bytes across system instructions and the data prompt, 2,000–32,768 |
| `DRILLLOOP_AI_MAX_OUTPUT_TOKENS` | `2048` | Model generation limit, 128–4,096 |
| `DRILLLOOP_AI_MAX_CONCURRENT` | `1` | Active requests per API worker, 1–4; excess requests receive HTTP 429 |

The provider checks the daemon’s cloud-disabled status and installed model inventory before sending exercise data. A missing status route, enabled cloud features, a missing tag, or a remote-model alias leaves AI unavailable. Proxy settings and redirects are disabled for provider requests. Keep daemon request-body logging disabled.

The selected exercise must have objectives and extracted observations. A request is limited to 128 observations and at most 12 model results. If the complete context exceeds either input limit, the API reports an evidence-limit abstention for the exercise without calling Ollama. Provider errors and objectives that received no valid result have separate messages. Ollama sees exercise-scoped source IDs, filenames, original locators, request-local record numbers, objective text, observation wording, and extraction and time metadata. The backend resolves exact excerpts to their original records before returning citations.

## Fictional demo

1. Build the frontend with `npm --prefix frontend run build`. With the AI variables set, run `.venv/bin/python scripts/evaluate_hybrid_ai.py --serve`. The runner creates a fresh temporary database.
2. Open `http://127.0.0.1:8000`. Sign in as `evaluation-admin` with the fixture-only password defined in the runner.
3. Select **Fictional reception point exercise**. Upload `evals/phase4a/fictional_reception_notes.txt` under **Evidence** and select **Run evidence analysis**.
4. Open **Findings**, select **Generate AI suggestions**, and follow the line 1 citation to its original source. Read the separate proposed deterministic finding and the AI result for the missing signed register. The dataset intentionally includes a fictional instruction in line 2.
5. For the OCR case, select **Fictional scanned pump restoration exercise** and upload `evals/phase2/sources/utility_emergency_log_scanned.pdf`. Generate suggestions and inspect the page citation and uncertain time.

Pass `--suite phase4b --serve` to include the fictional facilities exercise. Upload both `fictional_facilities_*.txt` files from `evals/phase4b/` and generate suggestions to inspect possible corroboration, a discrepancy, different response phases, and a causal evidence gap. With the demo server running, `frontend/e2e/hybrid-ai-workflow.mjs` automates these examples against the live API. Set `DRILLLOOP_E2E_USERNAME`, `DRILLLOOP_E2E_PASSWORD`, and optionally `DRILLLOOP_E2E_BASE_URL`. Screenshots default to a new temporary directory.

To repeat the current evaluation on disposable SQLite storage, run `.venv/bin/python scripts/evaluate_hybrid_ai.py --suite phase4b --repeat 3 --output /tmp/drillloop-phase4b-run.json`. To compare with the merged Phase 4A backend, use the same command with `--backend-root /path/to/phase4a-checkout` and a fresh output path. The paired runner pins the requested Ollama context to 8,192 tokens for both versions. Normal product requests size context from their prompt. Developer labels cover fictional evidence and have no independent adjudication. See the [Phase 4B evaluation](../../evals/phase4b/README.md).

## Review limits

The model chooses an interpretation category, exact excerpts, and missing-information categories. The server checks each excerpt against the scoped observation and shows that complete observation, up to 360 characters, rather than a potentially misleading fragment. Longer observations are withheld from AI results, even when part might be useful; inspect the original evidence. Exact quotation and source links do not establish that an interpretation is correct, and qualifications can also occur outside the extracted observation. The server renders the advisory wording, resolves comparison citations to distinct observations, and displays the two sides of a possible contradiction. Possible corroboration requires a pair from different source IDs. A model-proposed match without that pair can still return source wording for relevance review. Byte-identical sources or repeated observation wording with the same reported time produce an uncertain result. A proposed contradiction that uses an uncertain OCR time becomes an abstention, as does a positive timing advisory on a configured elapsed-time objective using an uncertain OCR citation. Reviewers still judge whether the sources are independent, concern the same event, and support the suggested relationship. Suggestions are temporary and disappear when the Findings panel closes or reloads.
