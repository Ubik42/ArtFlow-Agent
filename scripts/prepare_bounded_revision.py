from __future__ import annotations

import json
from pathlib import Path

from artflow_agent.agent_runtime import AgentEventStore
from artflow_agent.bounded_revision import build_revision_request, compile_editable_mask

ROOT = Path(__file__).resolve().parents[1]
RUN_ROOT = ROOT / "artifacts" / "goal" / "m3-s11-local-run"
OUTPUT_ROOT = ROOT / "artifacts" / "goal" / "m4-s3-bounded-revision"
OBJECT_ID = (
    ROOT
    / "artifacts"
    / "goal"
    / "m4-s2-negative-control"
    / "source-package"
    / "passes"
    / "object-id.png"
)
RUN_ID = "local-artflow-ue-7e66ea0f40432643e4ac63a8f39f98c6-130c94284deb"
PROMPT = """Use case: precise-object-edit
Asset type: evidence-selected game-art direction revision
Primary request: Refine only the sphere inside the white editable mask. Strengthen its thin amber equatorial light seam and add restrained wet dark-metal microdetail so it reads more clearly as the focal editable form.
Input images: Image 1 is the adopted parent and edit target; Image 2 is a binary mask where white is the only editable area and black must remain unchanged.
Composition/framing: preserve the exact 16:9 camera, horizon, object positions, object scale and silhouettes.
Lighting/mood: preserve the existing cool storm ambience, warm right-side sunlight and wet reflections.
Constraints: change only pixels represented by the white mask; preserve the left protected monolith, sphere silhouette, ground plane, background, camera and all unmasked pixels; no new objects.
Avoid: characters, logos, text, watermark, geometry redesign, camera shift, crop change, global relighting."""


def main() -> None:
    store = AgentEventStore(RUN_ROOT / "agent-events.sqlite3")
    state = store.load(RUN_ID)
    if state.scene is None or state.adoption_decision is None:
        raise RuntimeError("Scene or adoption evidence is missing")
    adoption = state.adoption_decision
    parent = RUN_ROOT / ".agent-artifacts" / "provider-outputs" / (
        f"{adoption.artifact_sha256}.png"
    )
    editable = next(
        region for region in state.scene.package.regions if region.mode == "editable"
    )
    protected = [
        region.region_id
        for region in state.scene.package.regions
        if region.mode == "protected"
    ]
    mask = compile_editable_mask(
        OBJECT_ID,
        parent,
        OUTPUT_ROOT,
        region_id=editable.region_id,
        object_ids=editable.object_ids,
    )
    request = build_revision_request(
        adoption,
        mask,
        scene_package_sha256=state.scene.archive_sha256,
        prompt=PROMPT,
        protected_regions=protected,
    )
    persisted = store.record_bounded_revision_request(RUN_ID, request)
    OUTPUT_ROOT.mkdir(parents=True, exist_ok=True)
    (OUTPUT_ROOT / "revision-request.json").write_text(
        json.dumps(request.model_dump(mode="json"), indent=2) + "\n",
        encoding="utf-8",
    )
    (OUTPUT_ROOT / "prompt.txt").write_text(PROMPT + "\n", encoding="utf-8")
    print(
        f"EVENTS={persisted.last_sequence} REVISION={request.revision_id} "
        f"MASK={mask.artifact_sha256} COVERAGE={mask.coverage_ratio:.6f}"
    )
    print(f"PARENT={parent}")
    print(f"MASK_PATH={OUTPUT_ROOT / mask.artifact_path}")


if __name__ == "__main__":
    main()
