from __future__ import annotations

import copy
import hashlib
import json
from collections.abc import Mapping
from datetime import UTC, datetime
from pathlib import Path, PurePosixPath, PureWindowsPath
from typing import Any, Literal

from pydantic import AwareDatetime, BaseModel, ConfigDict, Field, model_validator

SHA256_PATTERN = r"^[0-9a-f]{64}$"
MATERIAL_ID_PATTERN = r"^[a-z0-9][a-z0-9._-]{2,63}$"
SAFE_COMFY_INPUT_PATTERN = r"^ArtFlow/[A-Za-z0-9_./-]+\.(?:png|jpg|jpeg|webp)$"
REQUIRED_PBR_CHANNELS = ("base_color", "normal", "roughness", "metallic", "ambient_occlusion")


class PBRBoundaryError(RuntimeError):
    """Raised before an unreviewed or capability-stale PBR graph can be submitted."""


class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class PBRChannelContract(StrictModel):
    channel: Literal["base_color", "normal", "roughness", "metallic", "ambient_occlusion"]
    filename_suffix: str = Field(pattern=r"^[a-z0-9_]{2,32}$")
    color_space: Literal["srgb", "linear"]
    pixel_format: Literal["rgb8", "gray8"]
    semantic: str = Field(min_length=10, max_length=300)

    @model_validator(mode="after")
    def validate_channel_encoding(self) -> PBRChannelContract:
        expected = {
            "base_color": ("srgb", "rgb8"),
            "normal": ("linear", "rgb8"),
            "roughness": ("linear", "gray8"),
            "metallic": ("linear", "gray8"),
            "ambient_occlusion": ("linear", "gray8"),
        }[self.channel]
        if (self.color_space, self.pixel_format) != expected:
            raise ValueError(f"{self.channel} must use {expected[0]} / {expected[1]}")
        return self


class PBRTextureSetContract(StrictModel):
    schema_id: Literal["pbr-texture-set-contract/1"] = "pbr-texture-set-contract/1"
    material_id: str = Field(pattern=MATERIAL_ID_PATTERN)
    width: int = Field(ge=512, le=2048, multiple_of=8)
    height: int = Field(ge=512, le=2048, multiple_of=8)
    tileable: bool
    normal_convention: Literal["directx"] = "directx"
    channels: list[PBRChannelContract] = Field(min_length=5, max_length=5)

    @model_validator(mode="after")
    def require_exact_pbr_channels(self) -> PBRTextureSetContract:
        observed = tuple(item.channel for item in self.channels)
        if len(set(observed)) != len(observed) or set(observed) != set(REQUIRED_PBR_CHANNELS):
            raise ValueError("texture set must define each required PBR channel exactly once")
        return self


class NodeSchemaFingerprint(StrictModel):
    class_type: str = Field(min_length=1, max_length=160)
    schema_sha256: str = Field(pattern=SHA256_PATTERN)
    python_module: str = Field(min_length=1, max_length=300)
    output_types: list[str] = Field(default_factory=list, max_length=32)


class ComfyCapabilitySnapshot(StrictModel):
    schema_id: Literal["comfy-capability-snapshot/1"] = "comfy-capability-snapshot/1"
    snapshot_id: str = Field(pattern=r"^[a-z0-9][a-z0-9._-]{2,119}$")
    captured_at: AwareDatetime
    endpoint: str = Field(pattern=r"^http://127\.0\.0\.1:[0-9]{2,5}$")
    comfyui_version: str = Field(min_length=1)
    python_version: str = Field(min_length=1)
    pytorch_version: str = Field(min_length=1)
    device_name: str = Field(min_length=1)
    observed_node_count: int = Field(ge=1)
    required_nodes: list[NodeSchemaFingerprint] = Field(min_length=1)
    missing_nodes: list[str] = Field(default_factory=list)
    production_nodes_commit: str = Field(pattern=r"^[0-9a-f]{7,40}$")
    production_nodes_license: Literal["MIT"] = "MIT"
    production_nodes_license_sha256: str = Field(pattern=SHA256_PATTERN)
    snapshot_sha256: str = Field(pattern=SHA256_PATTERN)

    @model_validator(mode="after")
    def validate_snapshot(self) -> ComfyCapabilitySnapshot:
        names = [item.class_type for item in self.required_nodes]
        if len(names) != len(set(names)):
            raise ValueError("required node capability names must be unique")
        if self.missing_nodes:
            raise ValueError("supported capability snapshot cannot contain missing nodes")
        if self.snapshot_sha256 != _model_fingerprint(self, excluded={"snapshot_sha256"}):
            raise ValueError("capability snapshot fingerprint does not match its facts")
        return self


class PBRSlotTarget(StrictModel):
    node_id: str = Field(pattern=r"^[0-9]+$")
    input_name: str = Field(pattern=r"^[A-Za-z_][A-Za-z0-9_]*$")


class ReviewedPBRTemplate(StrictModel):
    schema_id: Literal["reviewed-pbr-template/1"] = "reviewed-pbr-template/1"
    template_id: str = Field(pattern=r"^[a-z0-9][a-z0-9._-]{2,119}$")
    version: str = Field(pattern=r"^[0-9]+\.[0-9]+\.[0-9]+$")
    workflow_file: str = Field(pattern=r"^[A-Za-z0-9_.-]+\.json$")
    workflow_sha256: str = Field(pattern=SHA256_PATTERN)
    required_nodes: list[str] = Field(min_length=1)
    required_node_schema_sha256: dict[str, str] = Field(min_length=1)
    required_models: list[str] = Field(min_length=1)
    slot_targets: dict[str, list[PBRSlotTarget]] = Field(min_length=1)

    @model_validator(mode="after")
    def validate_template_surface(self) -> ReviewedPBRTemplate:
        required_slots = {
            "source_image",
            "negative_prompt",
            "seed",
            "denoise",
            "width",
            "height",
            "contract_json",
            "workflow_values_json",
            "receipt_prompt",
            *{f"prompt_{channel}" for channel in REQUIRED_PBR_CHANNELS},
            *{f"output_{channel}" for channel in REQUIRED_PBR_CHANNELS},
        }
        if set(self.slot_targets) != required_slots:
            raise ValueError("reviewed PBR template slot surface is incomplete or contains extras")
        if set(self.required_node_schema_sha256) != set(self.required_nodes):
            raise ValueError("every required node must have one reviewed schema fingerprint")
        if any(
            len(value) != 64 or any(character not in "0123456789abcdef" for character in value)
            for value in self.required_node_schema_sha256.values()
        ):
            raise ValueError("required node schema fingerprints must be lowercase SHA-256")
        targets = [
            (target.node_id, target.input_name)
            for values in self.slot_targets.values()
            for target in values
        ]
        if len(targets) != len(set(targets)):
            raise ValueError("a workflow input cannot be controlled by multiple slots")
        return self


class PBRCompileRequest(StrictModel):
    material_id: str = Field(pattern=MATERIAL_ID_PATTERN)
    source_image: str = Field(pattern=SAFE_COMFY_INPUT_PATTERN)
    source_sha256: str = Field(pattern=SHA256_PATTERN)
    visual_intent: str = Field(min_length=10, max_length=800)
    negative_prompt: str = Field(min_length=1, max_length=500)
    seed: int = Field(ge=0, le=18446744073709551615)
    denoise: float = Field(ge=0.15, le=1.0)
    width: int = Field(ge=512, le=2048, multiple_of=8)
    height: int = Field(ge=512, le=2048, multiple_of=8)
    tileable: bool = True

    @model_validator(mode="after")
    def reject_unsafe_input_identity(self) -> PBRCompileRequest:
        normalized = self.source_image.replace("\\", "/")
        path = PurePosixPath(normalized)
        if PureWindowsPath(self.source_image).is_absolute() or path.is_absolute() or ".." in path.parts:
            raise ValueError("source image must be a compiler-owned ComfyUI input identity")
        return self


class CompiledPBRWorkflow(StrictModel):
    schema_id: Literal["compiled-pbr-workflow/1"] = "compiled-pbr-workflow/1"
    request_id: str = Field(pattern=r"^pbr-[0-9a-f]{24}$")
    template_id: str
    template_version: str
    template_sha256: str = Field(pattern=SHA256_PATTERN)
    capability_snapshot_sha256: str = Field(pattern=SHA256_PATTERN)
    source_sha256: str = Field(pattern=SHA256_PATTERN)
    workflow_sha256: str = Field(pattern=SHA256_PATTERN)
    texture_set: PBRTextureSetContract
    resolved_slots: dict[str, str | int | float]
    workflow: dict[str, Any]

    @model_validator(mode="after")
    def verify_workflow_fingerprint(self) -> CompiledPBRWorkflow:
        if self.workflow_sha256 != canonical_sha256(self.workflow):
            raise ValueError("compiled workflow fingerprint does not match workflow")
        return self


def canonical_sha256(value: object) -> str:
    encoded = json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode()
    return hashlib.sha256(encoded).hexdigest()


def capture_capability_snapshot(
    *,
    endpoint: str,
    system_stats: Mapping[str, Any],
    object_info: Mapping[str, Any],
    required_nodes: list[str],
    production_nodes_commit: str,
    production_nodes_license_sha256: str,
    captured_at: datetime,
) -> ComfyCapabilitySnapshot:
    missing = sorted(set(required_nodes) - set(object_info))
    if missing:
        raise PBRBoundaryError("Missing required ComfyUI nodes: " + ", ".join(missing))
    fingerprints: list[NodeSchemaFingerprint] = []
    for class_type in sorted(required_nodes):
        spec = object_info[class_type]
        if not isinstance(spec, Mapping):
            raise PBRBoundaryError(f"Invalid /object_info schema for {class_type}")
        schema_facts = {
            "input": spec.get("input", {}),
            "output": spec.get("output", []),
            "output_name": spec.get("output_name", []),
            "output_node": bool(spec.get("output_node", False)),
            "python_module": spec.get("python_module", "unknown"),
        }
        fingerprints.append(
            NodeSchemaFingerprint(
                class_type=class_type,
                schema_sha256=canonical_sha256(schema_facts),
                python_module=str(spec.get("python_module") or "unknown"),
                output_types=[str(item) for item in spec.get("output", [])],
            )
        )
    system = system_stats.get("system") or {}
    devices = system_stats.get("devices") or []
    facts: dict[str, Any] = {
        "schema_id": "comfy-capability-snapshot/1",
        "snapshot_id": f"comfy-pbr-{canonical_sha256([endpoint, captured_at.isoformat()])[:24]}",
        "captured_at": captured_at.astimezone(UTC).isoformat().replace("+00:00", "Z"),
        "endpoint": endpoint,
        "comfyui_version": str(system.get("comfyui_version") or "unknown"),
        "python_version": str(system.get("python_version") or "unknown"),
        "pytorch_version": str(system.get("pytorch_version") or "unknown"),
        "device_name": str((devices[0] if devices else {}).get("name") or "unknown"),
        "observed_node_count": len(object_info),
        "required_nodes": [item.model_dump(mode="json") for item in fingerprints],
        "missing_nodes": [],
        "production_nodes_commit": production_nodes_commit,
        "production_nodes_license": "MIT",
        "production_nodes_license_sha256": production_nodes_license_sha256,
    }
    facts["snapshot_sha256"] = _dict_fingerprint(facts, excluded={"snapshot_sha256"})
    return ComfyCapabilitySnapshot.model_validate(facts)


class PBRWorkflowCompiler:
    def __init__(self, template_path: Path, workflow_path: Path) -> None:
        self.template_path = template_path
        self.workflow_path = workflow_path
        self.template = ReviewedPBRTemplate.model_validate_json(
            template_path.read_text(encoding="utf-8")
        )
        if template_path.parent != workflow_path.parent:
            raise PBRBoundaryError("template manifest and workflow must share a reviewed directory")
        if self.template.workflow_file != workflow_path.name:
            raise PBRBoundaryError("template workflow filename does not match manifest")
        self.workflow = json.loads(workflow_path.read_text(encoding="utf-8"))
        if not isinstance(self.workflow, dict):
            raise PBRBoundaryError("reviewed workflow must be an API-format object")
        if canonical_sha256(self.workflow) != self.template.workflow_sha256:
            raise PBRBoundaryError("reviewed workflow hash does not match manifest")
        self._validate_declared_surface()

    def compile(
        self,
        request: PBRCompileRequest,
        snapshot: ComfyCapabilitySnapshot,
    ) -> CompiledPBRWorkflow:
        synthesis_mode = self.template.template_id == "pbr-material-synthesis-v1"
        if synthesis_mode and request.denoise != 1.0:
            raise PBRBoundaryError("synthesis template requires full-noise denoise=1.0")
        if not synthesis_mode and request.denoise > 0.65:
            raise PBRBoundaryError("reference template denoise cannot exceed 0.65")
        snapshot_nodes = {item.class_type for item in snapshot.required_nodes}
        missing = sorted(set(self.template.required_nodes) - snapshot_nodes)
        if missing:
            raise PBRBoundaryError("capability snapshot does not cover: " + ", ".join(missing))
        observed_schemas = {
            item.class_type: item.schema_sha256 for item in snapshot.required_nodes
        }
        drifted = sorted(
            name
            for name, expected in self.template.required_node_schema_sha256.items()
            if observed_schemas.get(name) != expected
        )
        if drifted:
            raise PBRBoundaryError("reviewed ComfyUI node schemas drifted: " + ", ".join(drifted))
        workflow = copy.deepcopy(self.workflow)
        texture_set = default_texture_set(request)
        tile_phrase = "seamless tileable" if request.tileable else "non-tileable unique"
        technical_prefix = (
            "orthographic square material texture filling the entire frame, no scene, no objects, "
            "no horizon, no perspective, "
            if synthesis_mode
            else ""
        )
        prompts = {
            "base_color": f"{technical_prefix}{tile_phrase} PBR base color texture, flat albedo only, no lighting; {request.visual_intent}",
            "normal": f"{technical_prefix}{tile_phrase} DirectX tangent-space normal map, RGB technical texture, dominant blue axis; {request.visual_intent}",
            "roughness": f"{technical_prefix}{tile_phrase} grayscale PBR roughness map, white rough black smooth; {request.visual_intent}",
            "metallic": f"{technical_prefix}{tile_phrase} grayscale PBR metallic mask, white metal black dielectric; {request.visual_intent}",
            "ambient_occlusion": f"{technical_prefix}{tile_phrase} grayscale ambient occlusion map, white exposed black crevice; {request.visual_intent}",
        }
        contract_json = json.dumps(
            {
                "required_slots": ["source_image", "material_id"],
                "parameter_ranges": {
                    "width": {"min": 512, "max": 2048},
                    "height": {"min": 512, "max": 2048},
                    "denoise": {"min": 0.15, "max": 1.0 if synthesis_mode else 0.65},
                },
            },
            ensure_ascii=False,
            sort_keys=True,
        )
        workflow_values_json = json.dumps(
            {
                "slots": {"source_image": request.source_image, "material_id": request.material_id},
                "parameters": {
                    "width": request.width,
                    "height": request.height,
                    "denoise": request.denoise,
                },
            },
            ensure_ascii=False,
            sort_keys=True,
        )
        values: dict[str, str | int | float] = {
            "source_image": request.source_image,
            "negative_prompt": request.negative_prompt,
            "seed": request.seed,
            "denoise": request.denoise,
            "width": request.width,
            "height": request.height,
            "contract_json": contract_json,
            "workflow_values_json": workflow_values_json,
            "receipt_prompt": request.visual_intent,
        }
        for channel, prompt in prompts.items():
            values[f"prompt_{channel}"] = prompt
            values[f"output_{channel}"] = f"ArtFlow/PBR/{request.material_id}/{request.material_id}_{channel}"
        for slot_name, targets in self.template.slot_targets.items():
            value = values[slot_name]
            for target in targets:
                workflow[target.node_id]["inputs"][target.input_name] = value
        workflow_sha256 = canonical_sha256(workflow)
        request_id = f"pbr-{canonical_sha256([request.model_dump(mode='json'), workflow_sha256])[:24]}"
        return CompiledPBRWorkflow(
            request_id=request_id,
            template_id=self.template.template_id,
            template_version=self.template.version,
            template_sha256=canonical_sha256(self.template.model_dump(mode="json")),
            capability_snapshot_sha256=snapshot.snapshot_sha256,
            source_sha256=request.source_sha256,
            workflow_sha256=workflow_sha256,
            texture_set=texture_set,
            resolved_slots=values,
            workflow=workflow,
        )

    def _validate_declared_surface(self) -> None:
        observed_nodes: set[str] = set()
        for node_id, node in self.workflow.items():
            if not isinstance(node_id, str) or not isinstance(node, dict):
                raise PBRBoundaryError("workflow nodes must be string-keyed objects")
            if set(node) != {"class_type", "inputs"} or not isinstance(node["inputs"], dict):
                raise PBRBoundaryError(f"workflow node {node_id} has an unreviewed shape")
            if not isinstance(node["class_type"], str):
                raise PBRBoundaryError(f"workflow node {node_id} has an invalid class_type")
            observed_nodes.add(node["class_type"])
        if observed_nodes != set(self.template.required_nodes):
            raise PBRBoundaryError("workflow node classes differ from reviewed manifest")
        for targets in self.template.slot_targets.values():
            for target in targets:
                try:
                    self.workflow[target.node_id]["inputs"][target.input_name]
                except KeyError as exc:
                    raise PBRBoundaryError(
                        f"declared slot target {target.node_id}.{target.input_name} is missing"
                    ) from exc


def default_texture_set(request: PBRCompileRequest) -> PBRTextureSetContract:
    specs = [
        ("base_color", "basecolor", "srgb", "rgb8", "Lighting-free visible albedo color."),
        ("normal", "normal_dx", "linear", "rgb8", "DirectX tangent-space surface normal."),
        ("roughness", "roughness", "linear", "gray8", "Per-pixel microsurface roughness."),
        ("metallic", "metallic", "linear", "gray8", "Binary or transitional metallic response."),
        ("ambient_occlusion", "ao", "linear", "gray8", "Local ambient occlusion without cast shadows."),
    ]
    return PBRTextureSetContract(
        material_id=request.material_id,
        width=request.width,
        height=request.height,
        tileable=request.tileable,
        channels=[
            PBRChannelContract(
                channel=channel,
                filename_suffix=suffix,
                color_space=color_space,
                pixel_format=pixel_format,
                semantic=semantic,
            )
            for channel, suffix, color_space, pixel_format, semantic in specs
        ],
    )


def _model_fingerprint(model: BaseModel, *, excluded: set[str]) -> str:
    return _dict_fingerprint(model.model_dump(mode="json"), excluded=excluded)


def _dict_fingerprint(value: Mapping[str, Any], *, excluded: set[str]) -> str:
    return canonical_sha256({key: item for key, item in value.items() if key not in excluded})
