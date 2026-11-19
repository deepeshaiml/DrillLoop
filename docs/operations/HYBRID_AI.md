# Phase 4A hybrid AI assistance

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
| `DRILLLOOP_AI_PROVIDER` | `ollama` | Phase 4A provider |
| `DRILLLOOP_AI_MODEL` | Empty | Exact locally installed tag, without a registry prefix |
| `DRILLLOOP_AI_ENDPOINT` | `http://127.0.0.1:11434` | HTTP origin using `127.0.0.1` or `[::1]` and an explicit port |
| `DRILLLOOP_AI_TIMEOUT_SECONDS` | `60` | End-to-end provider request deadline, 1–180 seconds |
| `DRILLLOOP_AI_MAX_INPUT_BYTES` | `12000` | UTF-8 bytes across system instructions and the data prompt, 2,000–32,768 |
| `DRILLLOOP_AI_MAX_OUTPUT_TOKENS` | `2048` | Model generation limit, 128–4,096 |
| `DRILLLOOP_AI_MAX_CONCURRENT` | `1` | Active requests per API worker, 1–4; excess requests receive HTTP 429 |

The provider checks the daemon’s cloud-disabled status and installed model inventory before sending exercise data. A missing status route, enabled cloud features, a missing tag, or a remote-model alias leaves AI unavailable. Proxy settings and redirects are disabled for provider requests. Keep daemon request-body logging disabled.

The selected exercise must have objectives and extracted observations. Phase 4A limits each request to 128 observations and at most 12 results. The API rejects oversized context instead of dropping potentially conflicting records. It identifies objectives that received no accepted suggestion. Ollama sees request-local record and source numbers, objective text, observation wording, and extraction/time metadata. The backend reattaches filenames, original locators, and source IDs after matching every excerpt to its exact extracted text.

## Fictional demo

1. Build the frontend with `npm --prefix frontend run build`. With the AI variables set, run `.venv/bin/python scripts/evaluate_hybrid_ai.py --serve`. The runner creates a fresh temporary database.
2. Open `http://127.0.0.1:8000`. Sign in as `evaluation-admin` with the fixture-only password defined in the runner.
3. Select **Fictional reception point exercise**. Upload `evals/phase4a/fictional_reception_notes.txt` under **Evidence** and select **Run evidence analysis**.
4. Open **Findings**, select **Generate AI suggestions**, and follow the line 1 citation to its original source. Read the separate proposed deterministic finding and the AI result for the missing signed register. The dataset intentionally includes a fictional instruction in line 2.
5. For the OCR case, select **Fictional scanned pump restoration exercise** and upload `evals/phase2/sources/utility_emergency_log_scanned.pdf`. Generate suggestions and inspect the page citation and uncertain time.

With the demo server running, `frontend/e2e/hybrid-ai-workflow.mjs` automates both examples against the live API. Set `DRILLLOOP_E2E_USERNAME`, `DRILLLOOP_E2E_PASSWORD`, and optionally `DRILLLOOP_E2E_BASE_URL`. Screenshots default to a new temporary directory.

To repeat the four-case model evaluation on a fresh database, run `.venv/bin/python scripts/evaluate_hybrid_ai.py --output /tmp/drillloop-phase4a-run.json`. The runner compares the exercise detail before and after AI assistance and stages fictional Phase 1 narratives, an OCR fixture, and the Phase 4A reception notes. The developer labels in `evals/phase4a/cases.json` are synthetic and have no independent adjudication.

## Review limits

The model chooses an interpretation category, exact excerpts, and missing-information categories. The server renders the advisory wording. Exact excerpt validation verifies what the source record says and where it came from. Assessing whether the selected records actually corroborate, contradict, or address an objective still requires evaluator review. OCR-derived times keep their source uncertainty. Suggestions are discarded when the Findings panel closes or reloads. Results are absent from reports and workflow history.
