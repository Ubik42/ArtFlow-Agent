import pytest

from artflow_agent.domain import EnvironmentSnapshot
from artflow_agent.recipes import RecipeCatalog, RecipeError


def test_bundled_catalog_contains_two_reviewed_recipes() -> None:
    catalog = RecipeCatalog.bundled()
    assert [item.recipe_id for item in catalog.list()] == [
        "composition-preserving-v1",
        "masked-refinement-v1",
    ]


def test_recipe_only_changes_declared_slots() -> None:
    recipe = RecipeCatalog.bundled().get("composition-preserving-v1")
    workflow = recipe.instantiate(
        {
            "source_image": "source.png",
            "positive_prompt": "cold dawn",
            "negative_prompt": "text",
            "seed": 42,
            "denoise": 0.4,
            "width": 1024,
            "height": 1024,
            "filename_prefix": "ArtFlow/test",
        }
    )
    assert workflow["12"]["inputs"]["noise_seed"] == 42
    assert workflow["14"]["inputs"]["steps"] == 20
    assert workflow["14"]["inputs"]["width"] == 1024
    assert workflow["1"]["inputs"]["unet_name"] == "flux-2-klein-base-4b-fp8.safetensors"
    with pytest.raises(RecipeError, match="Unreviewed"):
        recipe.instantiate({"steps": 99})


def test_recipe_reports_environment_incompatibility() -> None:
    recipe = RecipeCatalog.bundled().get("masked-refinement-v1")
    snapshot = EnvironmentSnapshot(
        comfy_url="http://localhost:8188",
        reachable=True,
        nodes=["LoadImage"],
        vram_mb=4096,
    )
    problems = recipe.validate_environment(snapshot)
    assert any("Missing nodes" in problem for problem in problems)
    assert any("VRAM" in problem for problem in problems)
