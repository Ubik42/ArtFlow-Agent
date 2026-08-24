from __future__ import annotations

import json
from pathlib import Path

import typer

from .comfy import inspect_environment
from .domain import ArtBrief
from .planning import DeterministicPlanner

app = typer.Typer(no_args_is_help=True, help="ArtFlow Agent development CLI.")


def _read_brief(path: Path) -> ArtBrief:
    return ArtBrief.model_validate_json(path.read_text(encoding="utf-8"))


@app.command("validate-brief")
def validate_brief(path: Path) -> None:
    """Validate an art brief and print its normalized form."""
    brief = _read_brief(path)
    typer.echo(brief.model_dump_json(indent=2))


@app.command()
def plan(path: Path) -> None:
    """Create a deterministic reviewable plan before model-backed planning is enabled."""
    brief = _read_brief(path)
    run_plan = DeterministicPlanner().create_plan(brief)
    typer.echo(run_plan.model_dump_json(indent=2))


@app.command()
def doctor(comfy_url: str = "http://127.0.0.1:8188") -> None:
    """Check whether the configured local ComfyUI runtime is reachable."""
    snapshot = inspect_environment(comfy_url)
    typer.echo(json.dumps(snapshot.model_dump(mode="json"), indent=2, ensure_ascii=False))
    if not snapshot.reachable:
        raise typer.Exit(code=1)

