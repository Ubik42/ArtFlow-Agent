from __future__ import annotations

import time
import uuid
from collections.abc import Mapping
from pathlib import Path
from typing import Any, Self

import httpx

from .domain import EnvironmentSnapshot, OutputArtifact, QueuedJob, UploadedInput


class ComfyError(RuntimeError):
    """Raised when ComfyUI rejects or fails a workflow operation."""


class ComfyGateway:
    def __init__(
        self,
        comfy_url: str,
        *,
        timeout_seconds: float = 10.0,
        client: httpx.Client | None = None,
    ) -> None:
        self.base_url = comfy_url.rstrip("/")
        self._owns_client = client is None
        self.client = client or httpx.Client(base_url=self.base_url, timeout=timeout_seconds)

    def close(self) -> None:
        if self._owns_client:
            self.client.close()

    def __enter__(self) -> Self:
        return self

    def __exit__(self, *_: object) -> None:
        self.close()

    def inspect(self) -> EnvironmentSnapshot:
        try:
            stats_response = self.client.get("/system_stats")
            stats_response.raise_for_status()
            stats = stats_response.json()
            object_response = self.client.get("/object_info")
            object_response.raise_for_status()
            object_info = object_response.json()
        except (httpx.HTTPError, ValueError, TypeError):
            return EnvironmentSnapshot(comfy_url=self.base_url, reachable=False)

        devices = stats.get("devices") or []
        system = stats.get("system") or {}
        vram_bytes = devices[0].get("vram_total") if devices else None
        model_inventory = _extract_model_inventory(object_info)
        return EnvironmentSnapshot(
            comfy_url=self.base_url,
            reachable=True,
            comfyui_version=system.get("comfyui_version"),
            python_version=system.get("python_version"),
            pytorch_version=system.get("pytorch_version"),
            device_name=devices[0].get("name") if devices else None,
            models=sorted({name for values in model_inventory.values() for name in values}),
            model_inventory=model_inventory,
            nodes=sorted(object_info),
            vram_mb=int(vram_bytes / 1024 / 1024) if isinstance(vram_bytes, (int, float)) else None,
        )

    def queue(self, workflow: Mapping[str, Any], client_id: str | None = None) -> QueuedJob:
        resolved_client_id = client_id or str(uuid.uuid4())
        try:
            response = self.client.post(
                "/prompt", json={"prompt": dict(workflow), "client_id": resolved_client_id}
            )
            response.raise_for_status()
            payload = response.json()
            return QueuedJob(
                prompt_id=payload["prompt_id"],
                client_id=resolved_client_id,
                number=payload.get("number"),
            )
        except (httpx.HTTPError, ValueError, KeyError, TypeError) as exc:
            raise ComfyError(f"ComfyUI rejected the workflow: {exc}") from exc

    def validate_workflow(self, workflow: Mapping[str, Any]) -> list[str]:
        try:
            response = self.client.get("/object_info")
            response.raise_for_status()
            object_info = response.json()
        except (httpx.HTTPError, ValueError, TypeError) as exc:
            raise ComfyError(f"Could not inspect ComfyUI workflow schema: {exc}") from exc
        return _validate_workflow_against_object_info(workflow, object_info)

    def upload_image(
        self,
        path: Path,
        *,
        subfolder: str = "ArtFlow",
        overwrite: bool = False,
    ) -> UploadedInput:
        if not path.is_file():
            raise FileNotFoundError(path)
        try:
            with path.open("rb") as stream:
                response = self.client.post(
                    "/upload/image",
                    data={
                        "type": "input",
                        "subfolder": subfolder,
                        "overwrite": str(overwrite).lower(),
                    },
                    files={"image": (path.name, stream, "application/octet-stream")},
                )
            response.raise_for_status()
            return UploadedInput.model_validate(response.json())
        except (httpx.HTTPError, ValueError, TypeError) as exc:
            raise ComfyError(f"Could not upload {path.name}: {exc}") from exc

    def download_output(self, artifact: OutputArtifact, destination: Path) -> Path:
        content = self.fetch_output_bytes(artifact)
        destination.parent.mkdir(parents=True, exist_ok=True)
        temporary = destination.with_suffix(destination.suffix + ".part")
        temporary.write_bytes(content)
        temporary.replace(destination)
        return destination

    def fetch_output_bytes(self, artifact: OutputArtifact) -> bytes:
        try:
            response = self.client.get(
                "/view",
                params={
                    "filename": artifact.filename,
                    "subfolder": artifact.subfolder,
                    "type": artifact.type,
                },
            )
            response.raise_for_status()
        except httpx.HTTPError as exc:
            raise ComfyError(f"Could not download {artifact.filename}: {exc}") from exc
        return response.content

    def history(self, prompt_id: str) -> dict[str, Any] | None:
        try:
            response = self.client.get(f"/history/{prompt_id}")
            response.raise_for_status()
            payload = response.json()
        except (httpx.HTTPError, ValueError, TypeError) as exc:
            raise ComfyError(f"Could not read job history for {prompt_id}: {exc}") from exc
        return payload.get(prompt_id)

    def wait(
        self, prompt_id: str, *, timeout_seconds: float = 300, poll_seconds: float = 1
    ) -> dict[str, Any]:
        deadline = time.monotonic() + timeout_seconds
        while time.monotonic() < deadline:
            entry = self.history(prompt_id)
            if entry is not None:
                status = entry.get("status") or {}
                if status.get("status_str") == "error":
                    raise ComfyError(f"ComfyUI job {prompt_id} failed")
                if status.get("completed") is True or entry.get("outputs"):
                    return entry
            time.sleep(poll_seconds)
        raise TimeoutError(f"Timed out waiting for ComfyUI job {prompt_id}")

    def collect_outputs(self, history_entry: Mapping[str, Any]) -> list[OutputArtifact]:
        artifacts: list[OutputArtifact] = []
        for node_id, node_outputs in (history_entry.get("outputs") or {}).items():
            for kind in ("images", "audio", "gifs"):
                for item in node_outputs.get(kind, []):
                    if isinstance(item, Mapping) and "filename" in item:
                        artifacts.append(
                            OutputArtifact(
                                filename=str(item["filename"]),
                                subfolder=str(item.get("subfolder", "")),
                                type=str(item.get("type", "output")),
                                node_id=str(node_id),
                            )
                        )
        return artifacts


MODEL_LOADER_INPUTS = {
    "checkpoints": (("CheckpointLoaderSimple", "ckpt_name"),),
    "diffusion_models": (("UNETLoader", "unet_name"),),
    "text_encoders": (
        ("CLIPLoader", "clip_name"),
        ("DualCLIPLoader", "clip_name1"),
        ("DualCLIPLoader", "clip_name2"),
    ),
    "vae": (("VAELoader", "vae_name"),),
}


def _extract_model_inventory(object_info: Mapping[str, Any]) -> dict[str, list[str]]:
    inventory: dict[str, list[str]] = {}
    for category, sources in MODEL_LOADER_INPUTS.items():
        values: set[str] = set()
        for node_name, input_name in sources:
            try:
                choices = object_info[node_name]["input"]["required"][input_name][0]
            except (KeyError, IndexError, TypeError):
                continue
            if isinstance(choices, list):
                values.update(str(choice) for choice in choices)
        inventory[category] = sorted(values)
    return inventory


def _validate_workflow_against_object_info(
    workflow: Mapping[str, Any], object_info: Mapping[str, Any]
) -> list[str]:
    problems: list[str] = []
    for node_id, node in workflow.items():
        if not isinstance(node, Mapping):
            problems.append(f"Node {node_id} must be an object")
            continue
        class_type = node.get("class_type")
        spec = object_info.get(class_type)
        if not isinstance(spec, Mapping):
            problems.append(f"Node {node_id} uses unavailable class {class_type!r}")
            continue
        inputs = node.get("inputs")
        if not isinstance(inputs, Mapping):
            problems.append(f"Node {node_id} inputs must be an object")
            continue
        input_spec = spec.get("input") or {}
        required = input_spec.get("required") or {}
        optional = input_spec.get("optional") or {}
        hidden = input_spec.get("hidden") or {}
        allowed_inputs = set(required) | set(optional) | set(hidden)
        for input_name in sorted(set(required) - set(inputs)):
            problems.append(f"Node {node_id} ({class_type}) is missing input {input_name!r}")
        for input_name in sorted(set(inputs) - allowed_inputs):
            problems.append(f"Node {node_id} ({class_type}) has unknown input {input_name!r}")
        for input_name, value in inputs.items():
            schema = required.get(input_name) or optional.get(input_name)
            if _is_link(value):
                source_id, output_index = str(value[0]), value[1]
                source = workflow.get(source_id)
                if not isinstance(source, Mapping):
                    problems.append(
                        f"Node {node_id} input {input_name!r} links to missing node {source_id}"
                    )
                    continue
                source_spec = object_info.get(source.get("class_type")) or {}
                outputs = source_spec.get("output") or []
                if not isinstance(output_index, int) or not 0 <= output_index < len(outputs):
                    problems.append(
                        f"Node {node_id} input {input_name!r} uses invalid output {output_index} "
                        f"from node {source_id}"
                    )
                elif isinstance(schema, list) and schema and isinstance(schema[0], str):
                    output_type = outputs[output_index]
                    if output_type != schema[0]:
                        problems.append(
                            f"Node {node_id} input {input_name!r} expects {schema[0]} but node "
                            f"{source_id} output {output_index} is {output_type}"
                        )
                continue
            _validate_literal(node_id, class_type, input_name, value, schema, problems)
    return problems


def _is_link(value: Any) -> bool:
    return (
        isinstance(value, list)
        and len(value) == 2
        and isinstance(value[0], (str, int))
        and isinstance(value[1], int)
    )


def _validate_literal(
    node_id: str,
    class_type: Any,
    input_name: str,
    value: Any,
    schema: Any,
    problems: list[str],
) -> None:
    if not isinstance(schema, list) or not schema:
        return
    declared_type = schema[0]
    metadata = schema[1] if len(schema) > 1 and isinstance(schema[1], Mapping) else {}
    if metadata.get("image_upload") is True:
        return
    choices: list[Any] | None = None
    if isinstance(declared_type, list):
        choices = declared_type
    elif declared_type == "COMBO" and isinstance(metadata.get("options"), list):
        choices = metadata["options"]
    if choices is not None and value not in choices:
        problems.append(
            f"Node {node_id} ({class_type}) input {input_name!r} has unavailable value {value!r}"
        )
        return
    if isinstance(value, (int, float)) and not isinstance(value, bool):
        minimum = metadata.get("min")
        maximum = metadata.get("max")
        if minimum is not None and value < minimum:
            problems.append(f"Node {node_id} input {input_name!r} is below {minimum}")
        if maximum is not None and value > maximum:
            problems.append(f"Node {node_id} input {input_name!r} is above {maximum}")


def inspect_environment(comfy_url: str, timeout_seconds: float = 3.0) -> EnvironmentSnapshot:
    with ComfyGateway(comfy_url, timeout_seconds=timeout_seconds) as gateway:
        return gateway.inspect()
