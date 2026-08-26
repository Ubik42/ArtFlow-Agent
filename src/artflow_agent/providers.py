from __future__ import annotations

from pathlib import Path
from typing import Any, Protocol

from .comfy import ComfyGateway
from .domain import EnvironmentSnapshot, GenerationReceipt, OutputArtifact, UploadedInput
from .execution import execute_recipe
from .recipes import Recipe


class RecipeExecutionProvider(Protocol):
    """Provider port used by orchestration; transport details stay behind adapters."""

    provider_id: str

    def inspect(self) -> EnvironmentSnapshot: ...

    def upload_image(self, path: Path, *, subfolder: str) -> UploadedInput: ...

    def execute(
        self,
        recipe: Recipe,
        values: dict[str, Any],
        *,
        environment: EnvironmentSnapshot | None = None,
    ) -> GenerationReceipt: ...

    def download_output(self, artifact: OutputArtifact, destination: Path) -> Path: ...


class ComfyRecipeProvider:
    """Local ComfyUI adapter for the reviewed-recipe provider port."""

    provider_id = "comfy-local"

    def __init__(self, gateway: ComfyGateway) -> None:
        self.gateway = gateway

    def inspect(self) -> EnvironmentSnapshot:
        return self.gateway.inspect()

    def upload_image(self, path: Path, *, subfolder: str) -> UploadedInput:
        return self.gateway.upload_image(path, subfolder=subfolder)

    def execute(
        self,
        recipe: Recipe,
        values: dict[str, Any],
        *,
        environment: EnvironmentSnapshot | None = None,
    ) -> GenerationReceipt:
        return execute_recipe(self.gateway, recipe, values, environment=environment)

    def download_output(self, artifact: OutputArtifact, destination: Path) -> Path:
        return self.gateway.download_output(artifact, destination)
