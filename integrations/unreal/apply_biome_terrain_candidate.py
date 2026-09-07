from __future__ import annotations

import hashlib
import json
from datetime import UTC, datetime
from pathlib import Path

import unreal


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def canonical(value: object) -> str:
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(",", ":")).encode()).hexdigest()


def fail(message: str) -> None:
    raise RuntimeError(f"ArtFlow biome terrain failed: {message}")


repo = Path(__file__).resolve().parents[2]
evidence = repo / "artifacts/goal/m42-s1-terrain-biome"
request = json.loads((evidence / "terrain-biome-request.json").read_text(encoding="utf-8"))
fields = json.loads((evidence / "comfy-terrain-fields-receipt.json").read_text(encoding="utf-8"))
terrain = json.loads((evidence / "blender-terrain-receipt.json").read_text(encoding="utf-8"))
manifest_path = evidence / next(item["relative_path"] for item in terrain["artifacts"] if item["kind"] == "pcg_manifest")
manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
if fields["request_sha256"] != request["request_sha256"] or terrain["request_sha256"] != request["request_sha256"]:
    fail("receipt chain differs from the registered request")
for item in terrain["artifacts"]:
    if sha256(evidence / item["relative_path"]) != item["sha256"]:
        fail(f"Blender artifact identity drifted: {item['kind']}")

project = Path(unreal.Paths.project_dir()).resolve()
source_level = project / "Content/ArtFlowDemo.umap"
source_candidate = request["source_candidate_scene_path"]
source_candidate_file = project / "Content" / (source_candidate.removeprefix("/Game/") + ".umap")
source_level_before, source_candidate_before = sha256(source_level), sha256(source_candidate_file)
identity = request["request_sha256"][:12]
destination = f"/Game/ArtFlow/Generated/Terrain/TB_{identity}"
glb = evidence / next(item["relative_path"] for item in terrain["artifacts"] if item["kind"] == "glb")
mesh_name = "SM_AF_BiomeTerrain"
mesh_object = f"{destination}/{mesh_name}.{mesh_name}"
mesh = unreal.EditorAssetLibrary.load_asset(mesh_object) if unreal.EditorAssetLibrary.does_asset_exist(mesh_object) else None
if not isinstance(mesh, unreal.StaticMesh) and unreal.EditorAssetLibrary.does_directory_exist(destination):
    for path in unreal.EditorAssetLibrary.list_assets(destination, recursive=True, include_folder=False):
        asset = unreal.EditorAssetLibrary.load_asset(path)
        if isinstance(asset, unreal.StaticMesh):
            mesh = asset
            break
reconciled = isinstance(mesh, unreal.StaticMesh)
if mesh is None:
    task = unreal.AssetImportTask()
    task.set_editor_property("filename", str(glb))
    task.set_editor_property("destination_path", destination)
    task.set_editor_property("destination_name", mesh_name)
    task.set_editor_property("automated", True)
    task.set_editor_property("replace_existing", False)
    task.set_editor_property("save", True)
    unreal.AssetToolsHelpers.get_asset_tools().import_asset_tasks([task])
    mesh = unreal.EditorAssetLibrary.load_asset(mesh_object)
if not isinstance(mesh, unreal.StaticMesh):
    candidates = unreal.EditorAssetLibrary.list_assets(destination, recursive=True, include_folder=False)
    mesh = next((unreal.EditorAssetLibrary.load_asset(path) for path in candidates if isinstance(unreal.EditorAssetLibrary.load_asset(path), unreal.StaticMesh)), None)
if not isinstance(mesh, unreal.StaticMesh):
    fail("could not import the registered GLB terrain")
unreal.EditorAssetLibrary.set_metadata_tag(mesh, "ArtFlow.TerrainRequestSha256", request["request_sha256"])
unreal.EditorAssetLibrary.set_metadata_tag(mesh, "ArtFlow.HeightMapSha256", fields["height_map_sha256"])
unreal.EditorAssetLibrary.set_metadata_tag(mesh, "ArtFlow.BiomeMaskSha256", fields["biome_mask_sha256"])
unreal.EditorAssetLibrary.save_loaded_asset(mesh, only_if_is_dirty=False)

graph_package = f"/Game/ArtFlow/PCG/Generated/PCG_AF_Biome_{identity}"
graph_object = f"{graph_package}.PCG_AF_Biome_{identity}"
graph_exists = unreal.EditorAssetLibrary.does_asset_exist(graph_object)
graph = unreal.EditorAssetLibrary.load_asset(graph_object) if graph_exists else unreal.EditorAssetLibrary.duplicate_asset("/Game/ArtFlow/PCG/PCG_ArtFlowScatter.PCG_ArtFlowScatter", graph_package)
if not isinstance(graph, unreal.PCGGraph):
    fail("could not derive the project PCG biome graph")
if not graph_exists:
    point_settings = next((node.get_settings() for node in graph.get_editor_property("nodes") if isinstance(node.get_settings(), unreal.PCGCreatePointsSettings)), None)
    spawner = next((node.get_settings() for node in graph.get_editor_property("nodes") if isinstance(node.get_settings(), unreal.PCGStaticMeshSpawnerSettings)), None)
    if point_settings is None or spawner is None:
        fail("project PCG template changed")
    points = []
    for item in manifest["points"]:
        point = unreal.PCGPoint()
        point.set_editor_property("transform", unreal.Transform(location=unreal.Vector(*item["location_cm"]), scale=unreal.Vector(0.55, 0.55, 0.55)))
        point.set_editor_property("density", 1.0)
        point.set_editor_property("seed", item["seed"])
        points.append(point)
    point_settings.set_editor_property("points_to_create", points)
    point_settings.set_editor_property("coordinate_space", unreal.PCGCoordinateSpace.WORLD)
    m32 = json.loads((repo / "artifacts/goal/m32-s1-procedural-kit/unreal-procedural-kit-return-receipt.json").read_text(encoding="utf-8"))
    selector = spawner.get_editor_property("mesh_selector_parameters")
    entries = []
    for path in m32["imported_mesh_paths"]:
        descriptor = unreal.PCGSoftISMComponentDescriptor()
        descriptor.set_editor_property("static_mesh", unreal.EditorAssetLibrary.load_asset(path))
        descriptor.set_editor_property("additional_comma_separated_tags", "ArtFlow.Generated,ArtFlow.PCG.Biome")
        entry = unreal.PCGMeshSelectorWeightedEntry(weight=1)
        entry.set_editor_property("descriptor", descriptor)
        entries.append(entry)
    selector.set_editor_property("mesh_entries", entries)
    spawner.set_editor_property("synchronous_load", True)
    unreal.EditorAssetLibrary.set_metadata_tag(graph, "ArtFlow.TerrainRequestSha256", request["request_sha256"])
    unreal.EditorAssetLibrary.save_loaded_asset(graph, only_if_is_dirty=False)

candidate_name = f"Terrain_B_{identity}"
candidate_package = f"/Game/ArtFlow/Sessions/AF_dc31f6ed0f4e/Candidates/{candidate_name}"
candidate_object = f"{candidate_package}.{candidate_name}"
candidate_exists = unreal.EditorAssetLibrary.does_asset_exist(candidate_object)
if not candidate_exists:
    candidate = unreal.EditorAssetLibrary.duplicate_asset(source_candidate, candidate_package)
    if candidate is None:
        fail("could not derive terrain candidate")
    unreal.EditorAssetLibrary.save_loaded_asset(candidate, only_if_is_dirty=False)
    del candidate
    unreal.SystemLibrary.collect_garbage()
world = unreal.EditorLoadingAndSavingUtils.load_map(candidate_package)
subsystem = unreal.get_editor_subsystem(unreal.EditorActorSubsystem)
actors = subsystem.get_all_level_actors()
terrain_actor = next((a for a in actors if a.get_actor_label() == "ArtFlow_BiomeTerrain"), None)
if terrain_actor is None:
    terrain_actor = subsystem.spawn_actor_from_class(unreal.StaticMeshActor, unreal.Vector(0, 0, -5))
    terrain_actor.set_actor_label("ArtFlow_BiomeTerrain")
terrain_actor.static_mesh_component.set_static_mesh(mesh)
target = next((a for a in actors if a.get_actor_label() == "Editable_Form"), None)
if target is None:
    fail("registered PCG target actor is missing")
pcgs = target.get_components_by_class(unreal.PCGComponent)
if len(pcgs) != 1:
    fail("registered target must contain one PCG component")
pcg = pcgs[0]
already_applied = candidate_exists and pcg.get_graph() == graph and int(pcg.get_editor_property("seed")) == request["seed"]
pcg.cleanup_local(True)
pcg.set_graph(graph)
pcg.set_editor_property("seed", request["seed"])
pcg.generate_local(True)

screenshot = evidence / "unreal-biome-terrain-candidate.png"
if screenshot.is_file():
    screenshot.unlink()
camera = next((a for a in actors if a.get_actor_label() == "ArtFlow_Camera"), None)
state = {"ticks": 0, "phase": "generation", "callback": None}


def instance_count() -> int:
    return sum(
        component.get_instance_count()
        for actor in subsystem.get_all_level_actors()
        for component in actor.get_components_by_class(unreal.InstancedStaticMeshComponent)
    )


def finish() -> None:
    unreal.EditorLoadingAndSavingUtils.save_map(world, candidate_package)
    source_level_after, source_candidate_after = sha256(source_level), sha256(source_candidate_file)
    if source_level_after != source_level_before or source_candidate_after != source_candidate_before:
        fail("terrain route changed an upstream level")
    instances = instance_count()
    if instances != len(manifest["points"]):
        fail(f"biome PCG produced {instances} instances instead of {len(manifest['points'])}")
    result = {"schema_id": "artflow-unreal-biome-terrain-receipt/1", "request_sha256": request["request_sha256"],
              "field_receipt_sha256": fields["receipt_sha256"], "blender_receipt_sha256": terrain["receipt_sha256"],
              "status": "reconciled" if reconciled and graph_exists and candidate_exists and already_applied else "generated",
              "engine_version": unreal.SystemLibrary.get_engine_version(), "candidate_scene_path": candidate_package,
              "source_candidate_scene_path": source_candidate, "terrain_mesh_path": mesh.get_path_name(),
              "native_pcg_graph_path": graph.get_path_name(), "biome_instance_count": instances,
              "duplicate_side_effect_count": 0, "source_level_sha256_before": source_level_before,
              "source_level_sha256_after": source_level_after, "source_candidate_sha256_before": source_candidate_before,
              "source_candidate_sha256_after": source_candidate_after, "screenshot_path": screenshot.name,
              "screenshot_sha256": sha256(screenshot) if screenshot.is_file() else None,
              "capture_status": "captured" if screenshot.is_file() else "unavailable",
              "completed_at": datetime.now(UTC).isoformat().replace("+00:00", "Z")}
    result["receipt_sha256"] = canonical(result)
    (evidence / "unreal-biome-terrain-receipt.json").write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8")
    unreal.log(f"ARTFLOW_BIOME_TERRAIN status={result['status']} instances={instances}")
    if state["callback"] is not None:
        unreal.unregister_slate_post_tick_callback(state["callback"])
    unreal.SystemLibrary.quit_editor()


def on_tick(_delta: float) -> None:
    state["ticks"] += 1
    if state["phase"] == "generation":
        if instance_count() != len(manifest["points"]):
            if state["ticks"] > 1800:
                fail("timed out waiting for biome PCG generation")
            return
        state["phase"] = "capture"
        state["ticks"] = 0
        if isinstance(camera, unreal.CameraActor):
            unreal.AutomationLibrary.take_high_res_screenshot(1280, 720, str(screenshot), camera, False, False)
            return
        finish()
    elif screenshot.is_file() or state["ticks"] > 240:
        finish()


unreal.EditorLoadingAndSavingUtils.save_map(world, candidate_package)
state["callback"] = unreal.register_slate_post_tick_callback(on_tick)
unreal.log("ARTFLOW_BIOME_TERRAIN_PENDING waiting for native PCG generation")
