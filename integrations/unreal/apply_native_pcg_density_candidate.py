from __future__ import annotations

import hashlib
import json
from datetime import UTC, datetime
from pathlib import Path

import unreal


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def canonical(value: object) -> str:
    data = json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode()
    return hashlib.sha256(data).hexdigest()


def fail(message: str) -> None:
    raise RuntimeError(f"ArtFlow native PCG density failed: {message}")


repo = Path(__file__).resolve().parents[2]
evidence = repo / "artifacts/goal/m34-s1-pcg-density"
m32 = repo / "artifacts/goal/m32-s1-procedural-kit"
request = json.loads((evidence / "pcg-density-request.json").read_text(encoding="utf-8"))
receipt = json.loads((evidence / "pcg-density-receipt.json").read_text(encoding="utf-8"))
spatial_path = evidence / receipt["spatial_manifest_path"]
spatial = json.loads(spatial_path.read_text(encoding="utf-8"))
kit_return_path = m32 / "unreal-procedural-kit-return-receipt.json"
kit_return = json.loads(kit_return_path.read_text(encoding="utf-8"))
if receipt.get("request_sha256") != request.get("request_sha256"):
    fail("density receipt does not belong to the request")
if sha256(spatial_path) != receipt.get("spatial_manifest_sha256"):
    fail("density spatial manifest identity drifted")
if kit_return.get("blender_receipt_sha256") != request.get("kit_receipt_sha256"):
    fail("Unreal kit identity differs from density request")
if len(spatial.get("points", [])) != 12:
    fail("native PCG density requires exactly twelve bounded points")

project = Path(unreal.Paths.project_dir()).resolve()
source_level = project / "Content/ArtFlowDemo.umap"
source_level_before = sha256(source_level)
source_candidate_package = request["source_candidate_scene_path"] if "source_candidate_scene_path" in request else kit_return["candidate_scene_path"]
source_candidate_file = project / "Content" / (source_candidate_package.removeprefix("/Game/") + ".umap")
source_candidate_before = sha256(source_candidate_file)
identity = request["request_sha256"][:12]

graph_package = f"/Game/ArtFlow/PCG/Generated/PCG_AF_Density_{identity}"
graph_object = f"{graph_package}.PCG_AF_Density_{identity}"
graph_reconciled = unreal.EditorAssetLibrary.does_asset_exist(graph_object)
if not graph_reconciled:
    graph = unreal.EditorAssetLibrary.duplicate_asset(
        "/Game/ArtFlow/PCG/PCG_ArtFlowScatter.PCG_ArtFlowScatter", graph_package
    )
    if graph is None:
        fail("could not duplicate the project-owned PCG graph template")
else:
    graph = unreal.EditorAssetLibrary.load_asset(graph_object)
if not isinstance(graph, unreal.PCGGraph):
    fail("density graph is not a PCGGraph")

if not graph_reconciled:
    point_settings = None
    spawner_settings = None
    for node in graph.get_editor_property("nodes"):
        settings = node.get_settings()
        if isinstance(settings, unreal.PCGCreatePointsSettings):
            point_settings = settings
        elif isinstance(settings, unreal.PCGStaticMeshSpawnerSettings):
            spawner_settings = settings
    if point_settings is None or spawner_settings is None:
        fail("registered native PCG template has changed")
    points = []
    for item in spatial["points"]:
        point = unreal.PCGPoint()
        location = item["location_cm"]
        scale = item["scale"]
        point.set_editor_property(
            "transform",
            unreal.Transform(
                location=unreal.Vector(*location),
                rotation=unreal.Rotator(0, item["yaw_deg"], 0),
                scale=unreal.Vector(scale, scale, scale),
            ),
        )
        point.set_editor_property("density", item["density"])
        point.set_editor_property("seed", item["seed"])
        points.append(point)
    point_settings.set_editor_property("points_to_create", points)
    point_settings.set_editor_property("coordinate_space", unreal.PCGCoordinateSpace.WORLD)
    selector = spawner_settings.get_editor_property("mesh_selector_parameters")
    entries = []
    for mesh_path in kit_return["imported_mesh_paths"]:
        mesh = unreal.EditorAssetLibrary.load_asset(mesh_path)
        if not isinstance(mesh, unreal.StaticMesh):
            fail(f"registered kit mesh is unavailable: {mesh_path}")
        descriptor = unreal.PCGSoftISMComponentDescriptor()
        descriptor.set_editor_property("static_mesh", mesh)
        descriptor.set_editor_property("additional_comma_separated_tags", "ArtFlow.Generated,ArtFlow.PCG.Density")
        entry = unreal.PCGMeshSelectorWeightedEntry(weight=1)
        entry.set_editor_property("descriptor", descriptor)
        entries.append(entry)
    selector.set_editor_property("mesh_entries", entries)
    spawner_settings.set_editor_property("synchronous_load", True)
    unreal.EditorAssetLibrary.set_metadata_tag(graph, "ArtFlow.PcgDensityRequestSha256", request["request_sha256"])
    unreal.EditorAssetLibrary.set_metadata_tag(graph, "ArtFlow.DensityMaskSha256", receipt["density_mask_sha256"])
    unreal.EditorAssetLibrary.save_loaded_asset(graph, only_if_is_dirty=False)
elif unreal.EditorAssetLibrary.get_metadata_tag(graph, "ArtFlow.PcgDensityRequestSha256") != request["request_sha256"]:
    fail("existing density graph belongs to another request")

candidate_name = f"Density_B_{identity}"
candidate_package = f"/Game/ArtFlow/Sessions/AF_dc31f6ed0f4e/Candidates/{candidate_name}"
candidate_object = f"{candidate_package}.{candidate_name}"
candidate_reconciled = unreal.EditorAssetLibrary.does_asset_exist(candidate_object)
if not candidate_reconciled:
    candidate = unreal.EditorAssetLibrary.duplicate_asset(source_candidate_package, candidate_package)
    if candidate is None:
        fail("could not duplicate the registered kit candidate")
    unreal.EditorAssetLibrary.save_loaded_asset(candidate, only_if_is_dirty=False)
    del candidate
    unreal.SystemLibrary.collect_garbage()
world = unreal.EditorLoadingAndSavingUtils.load_map(candidate_package)
subsystem = unreal.get_editor_subsystem(unreal.EditorActorSubsystem)
actors = subsystem.get_all_level_actors()
removed_materialized_actors = 0
if not candidate_reconciled:
    for actor in list(actors):
        if actor.get_actor_label().startswith("ArtFlow_PCG_kit-point-"):
            subsystem.destroy_actor(actor)
            removed_materialized_actors += 1
    actors = subsystem.get_all_level_actors()
target = next((actor for actor in actors if actor.get_actor_label() == "Editable_Form"), None)
if target is None:
    fail("registered PCG target actor is missing")
components = target.get_components_by_class(unreal.PCGComponent)
if len(components) != 1:
    fail("registered target must contain exactly one PCG component")
pcg = components[0]
already_applied = candidate_reconciled and pcg.get_graph() == graph and int(pcg.get_editor_property("seed")) == request["seed"]
if not already_applied:
    pcg.cleanup_local(True)
    pcg.set_graph(graph)
    pcg.set_editor_property("seed", request["seed"])
    pcg.generate_local(True)

camera = next((actor for actor in actors if actor.get_actor_label() == "ArtFlow_Camera"), None)
screenshot = evidence / "unreal-native-pcg-density-candidate.png"
if screenshot.is_file():
    screenshot.unlink()

state = {"phase": "generation", "ticks": 0, "callback": None}


def collect_instances() -> tuple[int, set[str]]:
    allowed_meshes = set(kit_return["imported_mesh_paths"])
    instance_count = 0
    generated_meshes: set[str] = set()
    for actor in subsystem.get_all_level_actors():
        for component in actor.get_components_by_class(unreal.InstancedStaticMeshComponent):
            mesh = component.get_editor_property("static_mesh")
            if mesh is not None and mesh.get_path_name() in allowed_meshes:
                generated_meshes.add(mesh.get_path_name())
                instance_count += component.get_instance_count()
    return instance_count, generated_meshes


def finish_with_error(message: str) -> None:
    unreal.log_error(f"ARTFLOW_NATIVE_PCG_DENSITY_ERROR {message}")
    if state["callback"] is not None:
        unreal.unregister_slate_post_tick_callback(state["callback"])
    unreal.SystemLibrary.quit_editor()


def finish_receipt() -> None:
    allowed_meshes = set(kit_return["imported_mesh_paths"])
    instance_count, generated_meshes = collect_instances()
    if instance_count != 12 or generated_meshes != allowed_meshes:
        finish_with_error(
            f"native PCG generated unexpected kit instances: {instance_count}/{len(generated_meshes)}"
        )
        return
    unreal.EditorLoadingAndSavingUtils.save_map(world, candidate_package)
    source_level_after = sha256(source_level)
    source_candidate_after = sha256(source_candidate_file)
    if source_level_before != source_level_after or source_candidate_before != source_candidate_after:
        finish_with_error("native PCG execution changed a source level or source candidate")
        return
    result = {
        "schema_id": "artflow-unreal-native-pcg-density-receipt/1",
        "request_id": request["request_id"], "request_sha256": request["request_sha256"],
        "density_receipt_sha256": receipt["receipt_sha256"],
        "spatial_manifest_sha256": receipt["spatial_manifest_sha256"],
        "status": "reconciled" if graph_reconciled and candidate_reconciled and already_applied else "generated",
        "engine_version": unreal.SystemLibrary.get_engine_version(),
        "native_pcg_graph_path": graph.get_path_name(), "candidate_scene_path": candidate_package,
        "source_candidate_scene_path": source_candidate_package,
        "generated_instance_count": instance_count, "generated_mesh_paths": sorted(generated_meshes),
        "removed_materialized_actor_count": removed_materialized_actors,
        "source_level_sha256_before": source_level_before, "source_level_sha256_after": source_level_after,
        "source_candidate_sha256_before": source_candidate_before, "source_candidate_sha256_after": source_candidate_after,
        "duplicate_side_effect_count": 0, "screenshot_path": screenshot.name,
        "screenshot_sha256": sha256(screenshot) if screenshot.is_file() else None,
        "capture_status": "captured" if screenshot.is_file() else "unavailable",
        "completed_at": datetime.now(UTC).isoformat().replace("+00:00", "Z"),
    }
    result["receipt_sha256"] = canonical(result)
    (evidence / "unreal-native-pcg-density-receipt.json").write_text(
        json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    unreal.log(
        f"ARTFLOW_NATIVE_PCG_DENSITY status={result['status']} "
        f"graph={graph.get_path_name()} instances={instance_count}"
    )
    if state["callback"] is not None:
        unreal.unregister_slate_post_tick_callback(state["callback"])
    unreal.SystemLibrary.quit_editor()


def on_tick(_delta_seconds: float) -> None:
    state["ticks"] += 1
    if state["ticks"] > 1800:
        finish_with_error(f"timed out while waiting for {state['phase']}")
        return
    if state["phase"] == "generation":
        instance_count, generated_meshes = collect_instances()
        if instance_count != 12 or len(generated_meshes) != 3:
            return
        state["phase"] = "capture"
        state["ticks"] = 0
        if isinstance(camera, unreal.CameraActor):
            unreal.AutomationLibrary.take_high_res_screenshot(
                1280, 720, str(screenshot), camera, False, False
            )
            return
        finish_receipt()
    elif state["phase"] == "capture" and (screenshot.is_file() or state["ticks"] > 120):
        finish_receipt()


state["callback"] = unreal.register_slate_post_tick_callback(on_tick)
unreal.log("ARTFLOW_NATIVE_PCG_DENSITY_PENDING waiting for native graph generation")
