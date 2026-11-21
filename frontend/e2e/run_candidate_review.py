"""Run the fictional candidate browser test against a fresh migrated local database."""

from __future__ import annotations

import argparse
import json
import os
import secrets
import subprocess
import sys
import tempfile
from contextlib import asynccontextmanager
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from scripts.isolated_runtime import configure, serve  # noqa: E402

WORDING = "No matching handoff entry was found in the fictional dispatch notebook."
EXCERPT = "matching handoff entry was found in the fictional dispatch notebook"
PROMOTION_WORDING = (
    "The fictional dispatcher recorded the signed panel handoff in the exercise log."
)


class FictionalProvider:
    async def generate(self, _system: str, evidence: str, _schema: dict):
        from app.ai_evaluation import ProviderReply

        context = json.loads(evidence)
        records = {item["text"]: item["record"] for item in context["records"]}
        suggestions = []
        for objective in context["objectives"]:
            if objective.startswith("PROMOTION-"):
                suggestions.append(
                    {
                        "objective_id": objective,
                        "kind": "relevant_observation",
                        "citations": [
                            {"record": records[PROMOTION_WORDING], "excerpt": PROMOTION_WORDING}
                        ],
                        "missing_information": ["verified_timing"],
                    }
                )
            else:
                suggestions.append(
                    {
                        "objective_id": objective,
                        "kind": "insufficient_evidence",
                        "citations": []
                        if objective == "OBJ-UNSOURCED"
                        else [{"record": records[WORDING], "excerpt": EXCERPT}],
                        "missing_information": ["completion_record"],
                    }
                )
        return ProviderReply(json.dumps({"suggestions": suggestions}))


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--screenshots", type=Path)
    parser.add_argument("--axe-script", type=Path, help="Optional local axe-core minified script.")
    args = parser.parse_args()
    if not (ROOT / "frontend" / "dist" / "index.html").is_file():
        parser.error("Build the production frontend before running the browser test.")
    if args.axe_script and not args.axe_script.is_file():
        parser.error("The selected axe-core script does not exist.")

    configure()
    os.environ["DRILLLOOP_AI_ENABLED"] = "0"
    from app import db
    from app.ai_evaluation import AiService, AiSettings
    from app.auth import hash_password
    from app.main import app

    password = secrets.token_urlsafe(24)
    users = [
        ("candidate-admin", "Fictional Evaluation Lead", "admin"),
        ("candidate-reviewer", "Fictional Independent Reviewer", "reviewer"),
        ("candidate-viewer", "Fictional Exercise Viewer", "viewer"),
        ("candidate-evaluator", "Fictional Exercise Evaluator", "evaluator"),
    ]
    os.environ["DRILLLOOP_USERS_JSON"] = json.dumps(
        [
            {
                "id": username,
                "username": username,
                "name": name,
                "role": role,
                "organization_id": "synthetic-evaluation",
                "password_hash": hash_password(password),
            }
            for username, name, role in users
        ]
    )
    db.migrate_database()
    original_lifespan = app.router.lifespan_context

    @asynccontextmanager
    async def with_fictional_provider(application):
        async with original_lifespan(application):
            application.state.ai_evaluation = AiService(
                AiSettings("http://127.0.0.1:11434", "fictional-provider:test", 5, 12_000, 1024, 1),
                FictionalProvider(),
            )
            yield

    screenshots = (
        args.screenshots or Path(tempfile.mkdtemp(prefix="drillloop-candidate-screenshots-"))
    ).resolve()
    screenshots.mkdir(parents=True, exist_ok=True)
    browser_env = {
        **os.environ,
        "DRILLLOOP_CANDIDATE_E2E_PASSWORD": password,
        "DRILLLOOP_CANDIDATE_E2E_SCREENSHOTS": str(screenshots),
        "DRILLLOOP_CANDIDATE_E2E_AXE": str(args.axe_script.resolve()) if args.axe_script else "",
    }
    command = ["node", "frontend/e2e/candidate-review-workflow.mjs"]
    try:
        app.router.lifespan_context = with_fictional_provider
        with serve(app) as port:
            browser_env["DRILLLOOP_E2E_BASE_URL"] = f"http://127.0.0.1:{port}"
            for mode in ("review", "promotion"):
                subprocess.run([*command, mode], cwd=ROOT, env=browser_env, check=True)
    finally:
        app.router.lifespan_context = original_lifespan

    with serve(app, port=port):
        for mode in ("ai-disabled", "promotion-restart"):
            subprocess.run([*command, mode], cwd=ROOT, env=browser_env, check=True)


if __name__ == "__main__":
    main()
