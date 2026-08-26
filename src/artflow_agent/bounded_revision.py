from __future__ import annotations

import hashlib
import io
import json
from collections import deque
from datetime import datetime
from pathlib import Path
from typing import Literal

from PIL import Image, ImageChops, ImageFilter
from pydantic import AwareDatetime, BaseModel, Field, model_validator

from .adoption import CandidateAdoptionDecision


class EditableMaskRecord(BaseModel):
    schema_id: Literal["editable-mask-record/1"] = "editable-mask-record/1"
    mask_id: str = Field(pattern=r"^mask-[a-f0-9]{20}$")
    region_id: str
    object_ids: list[str] = Field(min_length=1)
    source_object_id_sha256: str = Field(pattern=r"^[a-f0-9]{64}$")
    parent_artifact_sha256: str = Field(pattern=r"^[a-f0-9]{64}$")
    compiler_id: Literal["artflow-right-component-eroded-v1"] = (
        "artflow-right-component-eroded-v1"
    )
    artifact_path: str
    artifact_sha256: str = Field(pattern=r"^[a-f0-9]{64}$")
    width: int = Field(gt=0)
    height: int = Field(gt=0)
    editable_pixels: int = Field(gt=0)
    coverage_ratio: float = Field(gt=0, lt=1)
    limitation: str


class BoundedRevisionRequest(BaseModel):
    schema_id: Literal["bounded-revision-request/1"] = "bounded-revision-request/1"
    revision_id: str = Field(pattern=r"^revision-[a-f0-9]{20}$")
    adoption_decision_id: str
    adoption_sha256: str = Field(pattern=r"^[a-f0-9]{64}$")
    parent_candidate_id: str
    parent_artifact_sha256: str = Field(pattern=r"^[a-f0-9]{64}$")
    scene_package_sha256: str = Field(pattern=r"^[a-f0-9]{64}$")
    prompt_sha256: str = Field(pattern=r"^[a-f0-9]{64}$")
    prompt: str = Field(min_length=1, max_length=4000)
    mask: EditableMaskRecord
    editable_region: str
    protected_regions: list[str] = Field(min_length=1)
    sent_input_kinds: list[Literal["adopted_parent", "editable_mask"]] = Field(
        min_length=2, max_length=2
    )
    requested_tool: Literal["codex-builtin-imagegen"] = "codex-builtin-imagegen"
    requested_model_family: Literal["gpt-image-2"] = "gpt-image-2"

    @model_validator(mode="after")
    def verify_binding(self) -> BoundedRevisionRequest:
        if self.parent_artifact_sha256 != self.mask.parent_artifact_sha256:
            raise ValueError("Revision mask does not bind the adopted parent")
        if self.prompt_sha256 != _sha256_bytes(self.prompt.encode("utf-8")):
            raise ValueError("Revision prompt hash does not match")
        if set(self.sent_input_kinds) != {"adopted_parent", "editable_mask"}:
            raise ValueError("Revision must send exactly parent and mask")
        return self

    def fingerprint(self) -> str:
        return _sha256_json(self.model_dump(mode="json"))


class RevisionToolReceipt(BaseModel):
    schema_id: Literal["revision-tool-receipt/1"] = "revision-tool-receipt/1"
    revision_id: str
    tool_id: Literal["codex-builtin-imagegen"] = "codex-builtin-imagegen"
    requested_model_family: Literal["gpt-image-2"] = "gpt-image-2"
    observed_model_id: None = None
    request_binding_sha256: str = Field(pattern=r"^[a-f0-9]{64}$")
    raw_artifact_path: str
    raw_artifact_sha256: str = Field(pattern=r"^[a-f0-9]{64}$")
    raw_width: int = Field(gt=0)
    raw_height: int = Field(gt=0)
    upstream_request_id: None = None
    imported_at: AwareDatetime


class LeakageVerification(BaseModel):
    schema_id: Literal["mask-leakage-verification/1"] = (
        "mask-leakage-verification/1"
    )
    verifier_id: Literal["pixel-exact-mask-guard/1.0.0"] = (
        "pixel-exact-mask-guard/1.0.0"
    )
    parent_sha256: str = Field(pattern=r"^[a-f0-9]{64}$")
    mask_sha256: str = Field(pattern=r"^[a-f0-9]{64}$")
    composite_sha256: str = Field(pattern=r"^[a-f0-9]{64}$")
    outside_pixel_count: int = Field(gt=0)
    outside_changed_pixels: Literal[0] = 0
    inside_pixel_count: int = Field(gt=0)
    inside_changed_pixels: int = Field(ge=0)
    inside_change_ratio: float = Field(ge=0, le=1)
    hard_pass: Literal[True] = True
    limitation: str


class BoundedRevisionResult(BaseModel):
    schema_id: Literal["bounded-revision-result/1"] = "bounded-revision-result/1"
    revision_id: str
    request_sha256: str = Field(pattern=r"^[a-f0-9]{64}$")
    receipt: RevisionToolReceipt
    composite_artifact_path: str
    composite_artifact_sha256: str = Field(pattern=r"^[a-f0-9]{64}$")
    compositor_id: Literal["hard-mask-v1", "feathered-inside-mask-v2"] = (
        "hard-mask-v1"
    )
    attempt: int = Field(default=1, ge=1, le=10)
    width: int = Field(gt=0)
    height: int = Field(gt=0)
    leakage: LeakageVerification
    status: Literal["verified"] = "verified"

    @model_validator(mode="after")
    def verify_result_binding(self) -> BoundedRevisionResult:
        if self.revision_id != self.receipt.revision_id:
            raise ValueError("Revision receipt ID does not match result")
        if self.composite_artifact_sha256 != self.leakage.composite_sha256:
            raise ValueError("Leakage evidence does not match composite")
        return self


def compile_editable_mask(
    object_id_path: Path,
    parent_path: Path,
    output_dir: Path,
    *,
    region_id: str,
    object_ids: list[str],
) -> EditableMaskRecord:
    source_bytes = object_id_path.read_bytes()
    parent_bytes = parent_path.read_bytes()
    with Image.open(object_id_path) as image_file:
        source = image_file.convert("RGB")
    width, height = source.size
    pixels = source.load()
    foreground = bytearray(width * height)
    for y in range(height):
        for x in range(width):
            red, green, blue = pixels[x, y]
            if blue - red < 38 and blue - green < 28:
                foreground[y * width + x] = 1

    components = _components(foreground, width, height)
    candidates = [
        component
        for component in components
        if len(component) >= 200 and sum(index % width for index in component) / len(component) > width / 2
    ]
    if not candidates:
        raise ValueError("Editable right-side component was not found in object-ID evidence")
    selected = max(candidates, key=len)
    mask = Image.new("L", (width, height), 0)
    mask_pixels = mask.load()
    for index in selected:
        mask_pixels[index % width, index // width] = 255
    mask = mask.filter(ImageFilter.MinFilter(7))
    with Image.open(parent_path) as parent_file:
        parent_size = parent_file.size
    mask = mask.resize(parent_size, Image.Resampling.NEAREST)
    editable_pixels = sum(1 for value in mask.getdata() if value == 255)
    if editable_pixels == 0:
        raise ValueError("Compiled editable mask is empty after conservative erosion")
    encoded = io.BytesIO()
    mask.save(encoded, format="PNG", optimize=False)
    payload = encoded.getvalue()
    sha256 = _sha256_bytes(payload)
    relative = Path("masks") / f"{sha256}.png"
    path = output_dir / relative
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.exists() and path.read_bytes() != payload:
        raise ValueError("Existing mask path has different bytes")
    path.write_bytes(payload)
    return EditableMaskRecord(
        mask_id=f"mask-{sha256[:20]}",
        region_id=region_id,
        object_ids=object_ids,
        source_object_id_sha256=_sha256_bytes(source_bytes),
        parent_artifact_sha256=_sha256_bytes(parent_bytes),
        artifact_path=relative.as_posix(),
        artifact_sha256=sha256,
        width=parent_size[0],
        height=parent_size[1],
        editable_pixels=editable_pixels,
        coverage_ratio=editable_pixels / (parent_size[0] * parent_size[1]),
        limitation=(
            "The UE object-ID capture contains shaded grayscale rather than a flat ID LUT. "
            "The compiler selects and erodes the right connected silhouette; pixel-exact outside-mask verification remains authoritative."
        ),
    )


def build_revision_request(
    adoption: CandidateAdoptionDecision,
    mask: EditableMaskRecord,
    *,
    scene_package_sha256: str,
    prompt: str,
    protected_regions: list[str],
) -> BoundedRevisionRequest:
    prompt_sha = _sha256_bytes(prompt.encode("utf-8"))
    payload = {
        "adoption": adoption.fingerprint(),
        "parent": adoption.artifact_sha256,
        "scene": scene_package_sha256,
        "prompt": prompt_sha,
        "mask": mask.artifact_sha256,
    }
    return BoundedRevisionRequest(
        revision_id=f"revision-{_sha256_json(payload)[:20]}",
        adoption_decision_id=adoption.decision_id,
        adoption_sha256=adoption.fingerprint(),
        parent_candidate_id=adoption.selected_candidate_id,
        parent_artifact_sha256=adoption.artifact_sha256,
        scene_package_sha256=scene_package_sha256,
        prompt_sha256=prompt_sha,
        prompt=prompt,
        mask=mask,
        editable_region=mask.region_id,
        protected_regions=protected_regions,
        sent_input_kinds=["adopted_parent", "editable_mask"],
    )


def import_and_composite_revision(
    request: BoundedRevisionRequest,
    raw_output_path: Path,
    parent_path: Path,
    output_dir: Path,
    *,
    imported_at: datetime,
    compositor_id: Literal[
        "hard-mask-v1", "feathered-inside-mask-v2"
    ] = "hard-mask-v1",
    attempt: int = 1,
) -> BoundedRevisionResult:
    if _sha256_bytes(parent_path.read_bytes()) != request.parent_artifact_sha256:
        raise ValueError("Parent bytes do not match the revision request")
    mask_path = output_dir / request.mask.artifact_path
    if _sha256_bytes(mask_path.read_bytes()) != request.mask.artifact_sha256:
        raise ValueError("Mask bytes do not match the revision request")
    raw_bytes = raw_output_path.read_bytes()
    raw_sha = _sha256_bytes(raw_bytes)
    raw_relative = Path("raw") / f"{raw_sha}.png"
    raw_target = output_dir / raw_relative
    raw_target.parent.mkdir(parents=True, exist_ok=True)
    if raw_target.exists() and raw_target.read_bytes() != raw_bytes:
        raise ValueError("Existing raw revision path has different bytes")
    raw_target.write_bytes(raw_bytes)

    with Image.open(parent_path) as parent_file:
        parent = parent_file.convert("RGB")
    with Image.open(raw_output_path) as raw_file:
        raw = raw_file.convert("RGB")
        raw_size = raw.size
    with Image.open(mask_path) as mask_file:
        mask = mask_file.convert("L")
    raw = raw.resize(parent.size, Image.Resampling.LANCZOS)
    blend_mask = mask
    if compositor_id == "feathered-inside-mask-v2":
        core = mask.filter(ImageFilter.MinFilter(15))
        feathered = core.filter(ImageFilter.GaussianBlur(8))
        blend_mask = ImageChops.multiply(mask, feathered)
    composite = Image.composite(raw, parent, blend_mask)
    encoded = io.BytesIO()
    composite.save(encoded, format="PNG", optimize=False)
    composite_bytes = encoded.getvalue()
    composite_sha = _sha256_bytes(composite_bytes)
    composite_relative = Path("composites") / f"{composite_sha}.png"
    composite_path = output_dir / composite_relative
    composite_path.parent.mkdir(parents=True, exist_ok=True)
    if composite_path.exists() and composite_path.read_bytes() != composite_bytes:
        raise ValueError("Existing composite path has different bytes")
    composite_path.write_bytes(composite_bytes)

    difference = ImageChops.difference(parent, composite)
    difference_pixels = difference.load()
    mask_pixels = mask.load()
    inside = outside = inside_changed = outside_changed = 0
    for y in range(parent.height):
        for x in range(parent.width):
            changed = difference_pixels[x, y] != (0, 0, 0)
            if mask_pixels[x, y] > 0:
                inside += 1
                inside_changed += int(changed)
            else:
                outside += 1
                outside_changed += int(changed)
    if outside_changed != 0:
        raise ValueError("Revision leaked outside the persisted editable mask")
    receipt = RevisionToolReceipt(
        revision_id=request.revision_id,
        request_binding_sha256=request.fingerprint(),
        raw_artifact_path=raw_relative.as_posix(),
        raw_artifact_sha256=raw_sha,
        raw_width=raw_size[0],
        raw_height=raw_size[1],
        imported_at=imported_at,
    )
    leakage = LeakageVerification(
        parent_sha256=request.parent_artifact_sha256,
        mask_sha256=request.mask.artifact_sha256,
        composite_sha256=composite_sha,
        outside_pixel_count=outside,
        outside_changed_pixels=0,
        inside_pixel_count=inside,
        inside_changed_pixels=inside_changed,
        inside_change_ratio=inside_changed / inside,
        limitation=(
            "Proves pixel identity outside the persisted mask. It does not prove hidden 3D topology or semantic quality inside the editable region."
        ),
    )
    return BoundedRevisionResult(
        revision_id=request.revision_id,
        request_sha256=request.fingerprint(),
        receipt=receipt,
        composite_artifact_path=composite_relative.as_posix(),
        composite_artifact_sha256=composite_sha,
        compositor_id=compositor_id,
        attempt=attempt,
        width=parent.width,
        height=parent.height,
        leakage=leakage,
    )


def _components(foreground: bytearray, width: int, height: int) -> list[list[int]]:
    visited = bytearray(len(foreground))
    result: list[list[int]] = []
    for start, active in enumerate(foreground):
        if not active or visited[start]:
            continue
        visited[start] = 1
        queue = deque([start])
        component: list[int] = []
        while queue:
            index = queue.popleft()
            component.append(index)
            x, y = index % width, index // width
            for nx, ny in ((x - 1, y), (x + 1, y), (x, y - 1), (x, y + 1)):
                if 0 <= nx < width and 0 <= ny < height:
                    neighbour = ny * width + nx
                    if foreground[neighbour] and not visited[neighbour]:
                        visited[neighbour] = 1
                        queue.append(neighbour)
        result.append(component)
    return result


def _sha256_bytes(payload: bytes) -> str:
    return hashlib.sha256(payload).hexdigest()


def _sha256_json(payload: object) -> str:
    canonical = json.dumps(payload, sort_keys=True, separators=(",", ":")).encode()
    return _sha256_bytes(canonical)
