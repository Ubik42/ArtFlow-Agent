from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
from zipfile import ZipFile

from artflow_agent.contracts import SceneChangePlan, SceneDigitalTwin, SceneDryRunReceipt
from artflow_agent.scene_packages import ScenePackageArchive


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def verify(archive_path: Path, source_map: Path, source_map_sha256_before: str) -> dict[str, object]:
    preview = ScenePackageArchive().inspect(archive_path)
    package = preview.package
    refs = {
        "twin": package.scene_digital_twin,
        "plan": package.scene_change_plan,
        "receipt": package.scene_dry_run_receipt,
    }
    if any(value is None for value in refs.values()):
        raise ValueError("scene package does not reference all M7 dry-run artifacts")

    with ZipFile(archive_path) as archive:
        twin_bytes = archive.read(refs["twin"].path)  # type: ignore[union-attr]
        plan_bytes = archive.read(refs["plan"].path)  # type: ignore[union-attr]
        receipt_bytes = archive.read(refs["receipt"].path)  # type: ignore[union-attr]
    twin = SceneDigitalTwin.model_validate_json(twin_bytes)
    plan = SceneChangePlan.model_validate_json(plan_bytes)
    receipt = SceneDryRunReceipt.model_validate_json(receipt_bytes)

    twin_file_sha256 = hashlib.sha256(twin_bytes).hexdigest()
    plan_file_sha256 = hashlib.sha256(plan_bytes).hexdigest()
    if plan.twin_id != twin.twin_id or plan.twin_sha256 != twin_file_sha256:
        raise ValueError("plan is not bound to the exact Scene Digital Twin artifact")
    if (
        receipt.twin_id != twin.twin_id
        or receipt.twin_sha256 != twin_file_sha256
        or receipt.plan_id != plan.plan_id
        or receipt.plan_sha256 != plan_file_sha256
    ):
        raise ValueError("dry-run receipt is not bound to the exact twin and plan artifacts")

    actors = {actor.actor_id: actor for actor in twin.actors}
    pcg_components = {
        component.component_id: (actor, component)
        for actor in twin.actors
        for component in actor.pcg_components
    }
    for operation in plan.operations:
        for actor_id, expected in operation.expected_source_fingerprints.items():
            actor = actors.get(actor_id)
            if actor is None or actor.source_fingerprint != expected:
                raise ValueError(f"operation source fingerprint mismatch: {operation.operation_id}")
        if operation.operation_type == "set_lighting_rig":
            if any(actors[target].light is None for target in operation.target_light_ids):
                raise ValueError("lighting operation targets a non-light actor")
        else:
            binding = pcg_components.get(operation.component_id)
            if binding is None or binding[1].graph_path != operation.approved_graph_path:
                raise ValueError("PCG operation is not bound to the inspected approved graph")

    protected = {actor.actor_id: actor.source_fingerprint for actor in twin.actors if actor.protected}
    if receipt.protected_invariants != protected:
        raise ValueError("receipt protected invariants differ from the Scene Digital Twin")
    source_map_sha256_after = sha256_file(source_map)
    if source_map_sha256_after != source_map_sha256_before:
        raise ValueError("source Unreal map changed during dry-run")

    return {
        "schema": "artflow-scene-dry-run-verification/1",
        "status": "passed",
        "archive": str(archive_path.resolve()),
        "archive_sha256": preview.archive_sha256,
        "package_id": package.package_id,
        "twin_id": twin.twin_id,
        "twin_sha256": twin_file_sha256,
        "actor_count": len(twin.actors),
        "light_actor_count": sum(actor.light is not None for actor in twin.actors),
        "pcg_component_count": len(pcg_components),
        "protected_actor_count": len(protected),
        "plan_id": plan.plan_id,
        "plan_sha256": plan_file_sha256,
        "operation_types": [operation.operation_type for operation in plan.operations],
        "staging_strategy": receipt.staging_strategy,
        "dry_run": receipt.dry_run,
        "committed_mutation_count": receipt.committed_mutation_count,
        "source_map": str(source_map.resolve()),
        "source_map_sha256_before": source_map_sha256_before,
        "source_map_sha256_after": source_map_sha256_after,
        "source_map_unchanged": True,
        "artifact_count": len(preview.artifacts),
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Verify an ArtFlow M7 Unreal dry-run package.")
    parser.add_argument("archive", type=Path)
    parser.add_argument("--source-map", type=Path, required=True)
    parser.add_argument("--source-map-sha256-before", required=True)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    result = verify(
        args.archive,
        args.source_map,
        args.source_map_sha256_before.lower(),
    )
    rendered = json.dumps(result, ensure_ascii=False, indent=2) + "\n"
    if args.output is not None:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(rendered, encoding="utf-8")
    print(rendered, end="")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
