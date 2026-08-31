"""Compatibility entrypoint for the packaged ArtFlow Unreal review action."""

from pathlib import Path
from runpy import run_path

SCRIPT = (
    Path(__file__).resolve().parent
    / "ArtFlowSceneBridge"
    / "Content"
    / "Python"
    / "review_published_variant.py"
)
run_path(str(SCRIPT), run_name="__main__")
