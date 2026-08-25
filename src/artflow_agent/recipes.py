from __future__ import annotations

import copy
import json
from pathlib import Path
from typing import Any

from pydantic import TypeAdapter

from .domain import EnvironmentSnapshot, RecipeDefinition, RecipeSlot


class RecipeError(ValueError):
    """Raised when a recipe or its approved editable values are invalid."""


class Recipe:
    def __init__(self, definition: RecipeDefinition, workflow: dict[str, Any]) -> None:
        self.definition = definition
        self.workflow = workflow

    def validate_environment(self, snapshot: EnvironmentSnapshot) -> list[str]:
        problems: list[str] = []
        if not self.definition.execution_ready:
            problems.append("Recipe is not yet approved for live execution")
        if not snapshot.reachable:
            problems.append("ComfyUI is not reachable")
            return problems
        missing_nodes = sorted(set(self.definition.required_nodes) - set(snapshot.nodes))
        if missing_nodes:
            problems.append(f"Missing nodes: {', '.join(missing_nodes)}")
        if self.definition.required_models:
            missing_models = sorted(set(self.definition.required_models) - set(snapshot.models))
            if missing_models:
                problems.append(f"Missing models: {', '.join(missing_models)}")
        if (
            self.definition.estimated_vram_mb is not None
            and snapshot.vram_mb is not None
            and snapshot.vram_mb < self.definition.estimated_vram_mb
        ):
            problems.append(
                f"Recipe estimates {self.definition.estimated_vram_mb} MB VRAM; "
                f"environment reports {snapshot.vram_mb} MB"
            )
        return problems

    def instantiate(self, values: dict[str, Any]) -> dict[str, Any]:
        known_slots = {slot.name: slot for slot in self.definition.slots}
        unknown = sorted(set(values) - set(known_slots))
        if unknown:
            raise RecipeError(f"Unreviewed recipe slots: {', '.join(unknown)}")
        missing = sorted(
            slot.name for slot in self.definition.slots if slot.required and slot.name not in values
        )
        if missing:
            raise RecipeError(f"Missing required recipe slots: {', '.join(missing)}")

        workflow = copy.deepcopy(self.workflow)
        for name, value in values.items():
            slot = known_slots[name]
            validated = _validate_slot(slot, value)
            targets = slot.resolved_targets()
            if not targets:
                raise RecipeError(f"Slot {name!r} has no workflow targets")
            for target in targets:
                try:
                    workflow[target.node_id]["inputs"][target.input_name] = validated
                except KeyError as exc:
                    raise RecipeError(
                        f"Slot {name!r} points to a missing workflow input "
                        f"{target.node_id}.{target.input_name}"
                    ) from exc
        return workflow


class RecipeCatalog:
    def __init__(self, root: Path) -> None:
        self.root = root
        self._definitions: dict[str, RecipeDefinition] = {}
        for manifest in sorted(root.glob("*.recipe.json")):
            definition = RecipeDefinition.model_validate_json(manifest.read_text(encoding="utf-8"))
            if definition.recipe_id in self._definitions:
                raise RecipeError(f"Duplicate recipe ID: {definition.recipe_id}")
            self._definitions[definition.recipe_id] = definition

    @classmethod
    def bundled(cls) -> RecipeCatalog:
        source_tree = Path(__file__).resolve().parents[2] / "recipes"
        installed_package = Path(__file__).resolve().parent / "recipes"
        return cls(source_tree if source_tree.exists() else installed_package)

    def list(self, task_type: str | None = None) -> list[RecipeDefinition]:
        definitions = self._definitions.values()
        if task_type is not None:
            definitions = (item for item in definitions if item.task_type == task_type)
        return sorted(definitions, key=lambda item: item.recipe_id)

    def get(self, recipe_id: str) -> Recipe:
        try:
            definition = self._definitions[recipe_id]
        except KeyError as exc:
            raise RecipeError(f"Unknown recipe: {recipe_id}") from exc
        workflow_path = self.root / definition.workflow_file
        try:
            workflow = json.loads(workflow_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            raise RecipeError(f"Cannot load workflow for {recipe_id}: {exc}") from exc
        if not isinstance(workflow, dict):
            raise RecipeError(f"Workflow for {recipe_id} must be a JSON object")
        return Recipe(definition, workflow)


def _validate_slot(slot: RecipeSlot, value: Any) -> Any:
    adapters = {
        "string": TypeAdapter(str),
        "integer": TypeAdapter(int),
        "number": TypeAdapter(float),
        "boolean": TypeAdapter(bool),
    }
    try:
        validated = adapters[slot.value_type].validate_python(value, strict=True)
    except ValueError as exc:
        raise RecipeError(f"Invalid value for slot {slot.name}: {exc}") from exc
    if isinstance(validated, (int, float)) and not isinstance(validated, bool):
        if slot.minimum is not None and validated < slot.minimum:
            raise RecipeError(f"Slot {slot.name} must be >= {slot.minimum}")
        if slot.maximum is not None and validated > slot.maximum:
            raise RecipeError(f"Slot {slot.name} must be <= {slot.maximum}")
    return validated
