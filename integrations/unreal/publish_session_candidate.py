"""Compatibility entrypoint for the packaged ArtFlow Unreal publish action."""

from pathlib import Path
from runpy import run_path

SCRIPT = (
    Path(__file__).resolve().parent
    / "ArtFlowSceneBridge"
    / "Content"
    / "Python"
    / "publish_session_candidate.py"
)
run_path(str(SCRIPT), run_name="__main__")
