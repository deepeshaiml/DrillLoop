"""Launch or rehearse the fictional Eureka demo on an owned, loopback-only workspace."""

from __future__ import annotations

import argparse
import json
import os
import secrets
import subprocess
import sys
import threading
import urllib.request
from collections.abc import Iterator
from contextlib import asynccontextmanager
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from scripts.isolated_runtime import configure, serve  # noqa: E402

OWNER = "eureka-operator"
REVIEWER = "eureka-reviewer"
VIEWER = "eureka-viewer"
EXERCISE = "HOSP-PO-2026-01"
WORDING = "The fictional pharmacy supervisor signed the backup refrigerator temperature check form."
PRIVATE = ROOT / ".eureka-private"
RUNTIME_KEYS = (
    "DATABASE_URL",
    "DRILLLOOP_TEST_MODE",
    "DRILLLOOP_ENVIRONMENT",
    "DRILLLOOP_TEST_DB_ROOT",
    "DRILLLOOP_TEST_DB_TOKEN",
    "DRILLLOOP_UPLOAD_SCAN_MODE",
    "DRILLLOOP_COOKIE_SECURE",
    "DRILLLOOP_ENABLE_DEMO_SEED",
    "DEMO_SEED",
    "DRILLLOOP_SESSION_SECRET",
    "DRILLLOOP_DEMO_OWNER_ID",
    "DRILLLOOP_USERS_JSON",
)


class ControlledDemoProvider:
    async def generate(self, _system: str, evidence: str, _schema: dict):
        from app.ai_evaluation import ProviderReply

        context = json.loads(evidence)
        records = [row for row in context["records"] if row["text"] == WORDING]
        suggestions = []
        if records and "OBJ-03" in context["objectives"]:
            suggestions.append(
                {
                    "objective_id": "OBJ-03",
                    "kind": "relevant_observation",
                    "citations": [{"record": records[0]["record"], "excerpt": WORDING}],
                    "missing_information": ["verified_timing"],
                }
            )
        return ProviderReply(json.dumps({"suggestions": suggestions}))


def create_workspace(parent: Path) -> Path:
    from scripts.generate_phase2_ocr_fixtures import _native_pdf, _render_pages, _scan_pdf

    workspace = configure(retain_under=parent)
    from app.auth import hash_password

    users = [
        (OWNER, "Fictional Exercise Operator", "admin"),
        (REVIEWER, "Fictional Independent Reviewer", "reviewer"),
        (VIEWER, "Fictional Exercise Viewer", "viewer"),
    ]
    passwords = {username: secrets.token_urlsafe(24) for username, _, _ in users}
    os.environ["DRILLLOOP_DEMO_OWNER_ID"] = OWNER
    os.environ["DRILLLOOP_USERS_JSON"] = json.dumps(
        [
            {
                "id": username,
                "username": username,
                "name": name,
                "role": role,
                "organization_id": "eureka-fictional-demo",
                "password_hash": hash_password(passwords[username]),
            }
            for username, name, role in users
        ]
    )
    (workspace / "runtime.json").write_text(
        json.dumps({key: os.environ[key] for key in RUNTIME_KEYS}), encoding="utf-8"
    )
    (workspace / "credentials.json").write_text(json.dumps(passwords, indent=2), encoding="utf-8")
    (workspace / "fictional_pharmacy_handoff.txt").write_text(WORDING + "\n", encoding="utf-8")
    scan = _scan_pdf(
        _render_pages(
            _native_pdf(
                [
                    [
                        "FICTIONAL HOSPITAL EXERCISE - SYNTHETIC ONLY",
                        "[09:21] Pharmacy staff reviewed the backup thermometer.",
                        "The handoff time was not recorded.",
                    ]
                ]
            )
        )
    )
    (workspace / "fictional_pharmacy_scan.pdf").write_bytes(scan)
    return workspace


def resume_workspace(parent: Path, name: str) -> Path:
    workspace = parent / name
    if (
        workspace.is_symlink()
        or not workspace.is_dir()
        or workspace.resolve().parent != parent.resolve()
        or not workspace.name.startswith("drillloop-eval-")
    ):
        raise ValueError("--resume requires the name of a private Eureka run.")
    config = json.loads((workspace / "runtime.json").read_text())
    url = config.get("DATABASE_URL", "")
    if (
        set(config) != set(RUNTIME_KEYS)
        or config.get("DRILLLOOP_TEST_DB_ROOT") != str(workspace)
        or config.get("DRILLLOOP_TEST_MODE") != "1"
        or not url.startswith(f"sqlite:///{workspace}/test-eval-")
        or not Path(url.removeprefix("sqlite:///")).is_file()
    ):
        raise ValueError("The selected Eureka run does not have a valid owned database.")
    for key in (
        "DATABASE_PASSWORD_FILE",
        "DRILLLOOP_USERS_FILE",
        "DRILLLOOP_SESSION_SECRET_FILE",
        "DRILLLOOP_TRUSTED_HOSTS",
        "DRILLLOOP_CORS_ORIGINS",
    ):
        os.environ.pop(key, None)
    os.environ.update(config)
    os.environ["DRILLLOOP_TEST_DB_ALLOW_EXISTING"] = "1"
    sys.path.insert(0, str(ROOT / "backend"))
    return workspace


def ready(url: str) -> None:
    opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
    with opener.open(url + "/api/ready", timeout=5) as response:
        if json.load(response)["status"] != "ready":
            raise RuntimeError("The local demo did not report readiness.")


def verify_browser(url, workspace, args, mode):
    passwords = json.loads((workspace / "credentials.json").read_text())
    artifact = PRIVATE / "artifacts" / workspace.name
    artifact.mkdir(mode=0o700, parents=True, exist_ok=True)
    variables = {
        **os.environ,
        "DRILLLOOP_E2E_BASE_URL": url,
        "DRILLLOOP_EUREKA_CREDENTIALS": json.dumps(passwords),
        "DRILLLOOP_EUREKA_WORKSPACE": str(workspace),
        "DRILLLOOP_EUREKA_ARTIFACTS": str(artifact),
        "DRILLLOOP_EUREKA_AXE": str(args.axe_script.resolve()) if args.axe_script else "",
        "DRILLLOOP_EUREKA_MODEL": args.model or "",
    }
    subprocess.run(
        ["node", "frontend/e2e/eureka-workflow.mjs", mode],
        cwd=ROOT,
        env=variables,
        check=True,
    )


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--port", type=int, default=8765, help="Loopback port (0 for an unused port)"
    )
    parser.add_argument("--resume", help="Name of a previous owned private run")
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument("--controlled", action="store_true", help="Use a scripted fictional reply")
    mode.add_argument("--model", help="Use an installed model on a cloud-disabled local Ollama")
    parser.add_argument("--ollama-port", type=int, default=11479)
    parser.add_argument("--verify", choices=("fictional", "public", "ollama"))
    parser.add_argument("--axe-script", type=Path)
    args = parser.parse_args()
    if not 0 <= args.port <= 65535 or not 1 <= args.ollama_port <= 65535:
        parser.error("Ports must be in range (demo 0–65535, Ollama 1–65535).")
    if args.resume and args.verify:
        parser.error("Verification requires a fresh workspace.")
    if args.verify == "ollama" and not args.model:
        parser.error("--verify ollama requires --model.")
    if not (ROOT / "frontend/dist/index.html").is_file():
        parser.error("Run npm --prefix frontend run build before launching the demo.")
    if args.axe_script and not args.axe_script.is_file():
        parser.error("The axe-core script must be a local file.")
    os.umask(0o077)
    parent = PRIVATE / "demo"
    parent.mkdir(mode=0o700, parents=True, exist_ok=True)
    workspace = resume_workspace(parent, args.resume) if args.resume else create_workspace(parent)
    os.environ["DRILLLOOP_AI_ENABLED"] = "0"
    if args.model:
        os.environ.update(
            DRILLLOOP_AI_ENABLED="1",
            DRILLLOOP_AI_ENDPOINT=f"http://127.0.0.1:{args.ollama_port}",
            DRILLLOOP_AI_PROVIDER="ollama",
            DRILLLOOP_AI_MODEL=args.model,
            DRILLLOOP_AI_TIMEOUT_SECONDS="110",
            DRILLLOOP_AI_MAX_INPUT_BYTES="32768",
            DRILLLOOP_AI_MAX_OUTPUT_TOKENS="768",
            DRILLLOOP_AI_MAX_CONCURRENT="1",
        )
    from app import db
    from app.ai_evaluation import AiService, AiSettings
    from app.main import app

    if not args.resume:
        db.migrate_database()
    original = app.router.lifespan_context

    @asynccontextmanager
    async def with_controlled_provider(application) -> Iterator[None]:
        async with original(application):
            application.state.ai_evaluation = AiService(
                AiSettings("http://127.0.0.1:11479", "eureka-controlled:test", 5, 32000, 768, 1),
                ControlledDemoProvider(),
            )
            yield

    if args.controlled or args.verify == "fictional":
        app.router.lifespan_context = with_controlled_provider
    with serve(app, port=args.port) as port:
        url = f"http://127.0.0.1:{port}"
        ready(url)
        print(f"Ready on {url} | private run {workspace.name}", flush=True)
        print(f"Disposable demo accounts: {workspace / 'credentials.json'}", flush=True)
        if args.verify:
            verify_browser(url, workspace, args, args.verify)
        else:
            try:
                threading.Event().wait()
            except KeyboardInterrupt:
                return
    if args.verify == "fictional":
        app.router.lifespan_context = original
        os.environ["DRILLLOOP_AI_ENABLED"] = "0"
        with serve(app, port=port):
            ready(url)
            verify_browser(url, workspace, args, "restart")


if __name__ == "__main__":
    main()
