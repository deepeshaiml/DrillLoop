# DrillLoop Demo Guide

## What you will see

The demo uses a fictional two-hour hospital exercise called **Night Shift: Extended Power Loss** (`HOSP-PO-2026-01`). Every person, event, note, and transcript in it is invented. The exercise tests whether a hospital team can respond to a long power outage.

The main example is simple: the log says power failed at 09:02 and essential circuits were restored at 09:06. The exercise target is 60 seconds. DrillLoop proposes a finding about the delay and links it to those two log records. It does not know the cause of the delay. A human evaluator must review the proposal.

The sample also includes a seven-minute communication delay, a response time that conflicts with the event timestamps, a cold-chain procedure that went well, an action with no owner, and a vague untimed note that should not become a finding.

## Start the app

Use the local commands in [README.md](README.md), or run:

```bash
cp .env.example .env
docker compose up --build
```

Open <http://localhost:8000>. The local setup does not need a cloud account. The demonstration reviewer name and key are `Exercise Reviewer` / `demo-reviewer`.

## Five-minute walkthrough

1. **Open Overview.** Confirm that the hospital scenario and four exercise targets are shown. Tell viewers that all records are fictional.
2. **Open Timeline.** Show the 09:02 power failure and 09:06 restoration. Explain that four minutes is longer than the 60-second exercise target.
3. **Show the disagreement.** The control-room log says the ICU acknowledgement arrived at 09:10; an evaluator’s watch note says 09:11. DrillLoop shows both times and leaves the disagreement unresolved.
4. **Open Findings.** Select the power-restoration proposal. Open its source links to see the exact event-log rows. The proposal stays marked **Proposed** until a reviewer decides.
5. **Open the communications proposal.** It links to the radio request, the late acknowledgement, and the evaluator’s different time.
6. **Show the transcript warning.** One pre-written transcript segment says “too minutes” with 58% confidence. This is an invented speech-recognition error. The finding about the recorded “two minutes” response claim instead cites the independent event log.
7. **Review one finding.** Use the reviewer key to approve or reject it. Explain that approval is a person’s decision, not the system’s.
8. **Open Corrective Actions.** An action has a missing owner by design. Leave it blank to show the gap, or assign a fictional person to demonstrate editing. A reviewer can approve the action only after its finding is approved and the required fields are present.
9. **Show closure.** Enter fictional completion evidence and use **Record closure**. The action should not be closed without reviewer confirmation and evidence.
10. **Export the report.** Download the After-Action Report and Improvement Plan (AAR/IP). It shows evidence, interpretation, review status, and actions separately.

## Words used in the app

- **Observation:** what a source actually says, such as a row in the event log.
- **Finding:** an evaluator’s conclusion about an observation and an exercise target. It remains a proposal until approved.
- **Corrective action:** a task intended to improve performance in a future exercise.
- **Acceptance criteria:** how the team will show that the task is done. For example, “Three timed radio drills meet the three-minute target.”
- **Closure evidence:** a record a reviewer checks before marking an action complete.
- **Source link:** a direct path to the file and row, note line, PDF page, or transcript segment behind a claim.

The [Reader Guide](DRILLLOOP_READER_GUIDE.md) has a longer glossary and a safe example for AI agents.

## Show upload and error handling

- **Upload a supported file:** On Evidence, upload `demo/evidence/control_room_log.csv`, `evaluator_notes.txt`, or `transcript.json`, then select **Analyze**.
- **Unsupported file:** Try an image or DOCX file. The app explains that this file type is not supported.
- **Broken file:** Try a CSV without the required columns or invalid JSON. The app returns a clear error instead of treating it as valid evidence.
- **No exercise targets:** Create an exercise without targets and try to analyze it. The app reports that targets are required.
- **Reviewer access:** Clear the reviewer key and try to approve a finding or close an action. The app rejects the decision. Browsing and evidence upload remain available.
- **Speech recognition unavailable:** The default demo says the model is unavailable. It does not silently download a model.

## Optional local AI features (developer setup)

These features are not needed for the walkthrough or benchmark.

### Local wording suggestion

If Ollama and a compatible local language model are already installed, set:

```bash
export OLLAMA_BASE_URL=http://127.0.0.1:11434
export OLLAMA_MODEL=qwen3:4b
```

Restart the API and analyze the exercise. The model may reword a corrective action that the rules already proposed. It cannot create a finding, change the evidence links, or make a reviewer decision. The project has not tested this model’s accuracy or speed.

### Local speech-to-text

Speech-to-text is sometimes called automatic speech recognition (ASR). To enable the optional faster-whisper path, install its extra dependency and provide a model already downloaded to your computer:

```bash
.venv/bin/pip install -r requirements-asr.txt
export WHISPER_MODEL_PATH=/path/to/local/faster-whisper-model
```

The application saves transcript segments and their relative times. It does not identify speakers, provide word-level confidence, or claim multilingual accuracy. A person must check the transcript against the audio. No real audio file is included in the demo.

## Reset the review state

For local SQLite, stop the API before moving or deleting `drillloop.db`; restarting creates a fresh demo record. For Docker, data is in the named `drillloop-postgres` volume. Keep the volume if you want to preserve decisions. Delete or replace it only when you intentionally want a fresh demo.

## Benchmark limits

The benchmark checks one synthetic scenario against labels written for that same scenario. It matched 8 of 8 expected event rows, 5 of 5 expected findings, and 9 of 9 expected event-record links. It does not show accuracy on other exercises, whether evaluators agree with the proposals, staff time saved, or the quality of optional AI models. Details are in [DrillLoop_Evaluation_Report.pdf](DrillLoop_Evaluation_Report.pdf).
