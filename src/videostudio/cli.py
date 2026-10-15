from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import List, Optional

import uvicorn

from videostudio.llm import DEFAULT_MODELS, LLMConfig
from videostudio.lore import seed_default_canon
from videostudio.orchestrator import DurableMacroOrchestrator
from videostudio.server import create_app
from videostudio.storage import StudioStorage


def run_cli(argv: Optional[List[str]] = None) -> int:
    parser = argparse.ArgumentParser(
        prog="videostudio",
        description="VideoStudio: Automated Episodic Video Generation Pipeline",
    )
    subparsers = parser.add_subparsers(dest="command", required=True)

    # 1. produce command
    prod_parser = subparsers.add_parser(
        "produce",
        help="Execute the end-to-end 6-phase episodic video production workflow",
    )
    prod_parser.add_argument("--root-dir", default=".", help="Workspace root directory")
    prod_parser.add_argument("--episode-id", default="S01E01", help="Episode identifier (e.g. S01E01)")
    prod_parser.add_argument(
        "--seed",
        default="An encrypted harmonic from decommissioned Beacon 9 forces Commander Elena Vance and Dr. Marcus Koren into the Sub-Level 4 Cryogenic Relay Vault.",
        help="Narrative story seed",
    )
    prod_parser.add_argument(
        "--season-arc",
        default="The Jovian Shadow Conspiracy",
        help="Overarching season narrative arc",
    )
    prod_parser.add_argument(
        "--simulate-drift",
        default="SC01_SH01",
        help="Comma-separated shot IDs to simulate initial identity drift on (triggers Semantic Loop)",
    )
    prod_parser.add_argument(
        "--llm-provider",
        choices=["deterministic", "openrouter", "gemini", "openai", "anthropic", "ollama"],
        default="deterministic",
        help="LLM provider for the 5-agent reasoning council (default: deterministic)",
    )
    prod_parser.add_argument(
        "--llm-model",
        default=None,
        help="Optional LLM model identifier (e.g. anthropic/claude-3.7-sonnet for openrouter)",
    )

    # 2. serve command
    serve_parser = subparsers.add_parser(
        "serve",
        help="Start the interactive VideoStudio Production Control Room Web UI & FastAPI server",
    )
    serve_parser.add_argument("--root-dir", default=".", help="Workspace root directory")
    serve_parser.add_argument("--host", default="127.0.0.1", help="Bind host")
    serve_parser.add_argument("--port", type=int, default=8000, help="Bind port")

    args = parser.parse_args(argv)

    if args.command == "produce":
        storage = StudioStorage(root_dir=args.root_dir)
        seed_default_canon(storage)
        drift_set = {
            s.strip() for s in (args.simulate_drift or "").split(",") if s.strip()
        }
        llm_config = LLMConfig(
            provider=args.llm_provider,
            model=args.llm_model or DEFAULT_MODELS[args.llm_provider],
        )
        orchestrator = DurableMacroOrchestrator(
            storage=storage,
            event_callback=lambda ev: print(
                f"[{ev['phase']}] {ev['node']}: {ev['detail']}"
            ),
        )
        run_state = orchestrator.execute_episode_workflow(
            episode_id=args.episode_id,
            story_seed=args.seed,
            season_arc=args.season_arc,
            simulate_drift_shots=drift_set,
            llm_config=llm_config,
        )
        print(
            json.dumps(
                {
                    "workflow_id": run_state.workflow_id,
                    "status": run_state.status,
                    "llm_provider": llm_config.provider,
                    "llm_model": llm_config.model,
                    "otio_timeline_path": run_state.otio_timeline_path,
                    "semantic_loop_iterations": run_state.graph_state.get(
                        "semantic_loop_iterations", 0
                    ),
                },
                indent=2,
            )
        )
        return 0

    if args.command == "serve":
        app = create_app(root_dir=args.root_dir)
        uvicorn.run(app, host=args.host, port=args.port)
        return 0

    return 1


def main() -> None:
    sys.exit(run_cli())


if __name__ == "__main__":
    main()
