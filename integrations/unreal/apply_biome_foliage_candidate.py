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
    raise RuntimeError(f"ArtFlow foliage return failed: {message}")


repo = Path(__file__).resolve().parents[2]
evidence = repo / "artifacts/goal/m45-s1-foliage-kit"
request = json.loads((evidence / "foliage-kit-request.json").read_text(encoding="utf-8"))
blender = json.loads((evidence / "blender-foliage-kit-receipt.json").read_text(encoding="utf-8"))
manifest_path = evidence / next(item["relative_path"] for item in blender["artifacts"] if item["kind"] == "manifest")
manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
if blender["request_sha256"] != request["request_sha256"] or manifest["request_sha256"] != request["request_sha256"]:
    fail("typed receipt chain differs from the request")
for item in blender["artifacts"]:
    if sha256(evidence / item["relative_path"]) != item["sha256"]:
        fail(f"Blender artifact identity drifted: {item['relative_path']}")

project = Path(unreal.Paths.project_dir()).resolve()
source_file = project / "Content" / (request["source_candidate_scene_path"].removeprefix("/Game/") + ".umap")
source_before = sha256(source_file)
if source_before != request["source_candidate_sha256"]:
    fail("terrain candidate changed after foliage request compilation")
identity = request["request_sha256"][:12]

# Import three fixed variants and their deterministic LODs.
destination = f"/Game/ArtFlow/Generated/Blender/Foliage/F_{identity}"
meshes = {}
lod_counts = {}
collision_counts = {}
assets_reconciled = True
for variant in blender["variants"]:
    mesh = None
    for path in unreal.EditorAssetLibrary.list_assets(destination, recursive=True, include_folder=False):
        candidate = unreal.EditorAssetLibrary.load_asset(path)
        if (isinstance(candidate, unreal.StaticMesh)
                and unreal.EditorAssetLibrary.get_metadata_tag(candidate, "ArtFlow.FoliageRequestSha256") == request["request_sha256"]
                and unreal.EditorAssetLibrary.get_metadata_tag(candidate, "ArtFlow.SpeciesId") == variant["species_id"]):
            mesh = candidate
            break
    if mesh is None:
        assets_reconciled = False
        task = unreal.AssetImportTask()
        task.set_editor_property("filename", str(evidence / variant["base_glb"]))
        task.set_editor_property("destination_path", destination)
        task.set_editor_property("destination_name", variant["object_name"])
        task.set_editor_property("automated", True)
        task.set_editor_property("replace_existing", False)
        task.set_editor_property("save", True)
        unreal.AssetToolsHelpers.get_asset_tools().import_asset_tasks([task])
        mesh = next((unreal.EditorAssetLibrary.load_asset(path) for path in task.get_editor_property("imported_object_paths")
                     if isinstance(unreal.EditorAssetLibrary.load_asset(path), unreal.StaticMesh)), None)
    if not isinstance(mesh, unreal.StaticMesh):
        fail(f"Interchange did not produce {variant['species_id']}")
    unreal.EditorAssetLibrary.set_metadata_tag(mesh, "ArtFlow.FoliageRequestSha256", request["request_sha256"])
    unreal.EditorAssetLibrary.set_metadata_tag(mesh, "ArtFlow.SpeciesId", variant["species_id"])
    unreal.EditorAssetLibrary.set_metadata_tag(mesh, "ArtFlow.LOD1Sha256", variant["lod1_sha256"])
    if (unreal.EditorStaticMeshLibrary.get_lod_count(mesh) < 2
            and unreal.EditorStaticMeshLibrary.import_lod(mesh, 1, str(evidence / variant["lod1_glb"])) != 1):
        fail(f"could not attach LOD1 for {variant['species_id']}")
    if unreal.EditorStaticMeshLibrary.get_convex_collision_count(mesh) == 0:
        unreal.EditorStaticMeshLibrary.add_simple_collisions(mesh, unreal.ScriptingCollisionShapeType.BOX)
    unreal.EditorAssetLibrary.save_loaded_asset(mesh, only_if_is_dirty=False)
    meshes[variant["species_id"]] = mesh
    lod_counts[variant["species_id"]] = unreal.EditorStaticMeshLibrary.get_lod_count(mesh)
    collision_counts[variant["species_id"]] = unreal.EditorStaticMeshLibrary.get_convex_collision_count(mesh)

# One project-owned WPO master with only three exposed, bounded parameters.
material_package = f"/Game/ArtFlow/Generated/Materials/Foliage/M_AF_FoliageWind_{identity}"
material_name = material_package.rsplit("/", 1)[-1]
material = unreal.EditorAssetLibrary.load_asset(f"{material_package}.{material_name}")
material_reconciled = isinstance(material, unreal.Material)
if material is None:
    factory = unreal.MaterialFactoryNew()
    material = unreal.AssetToolsHelpers.get_asset_tools().create_asset(material_name, material_package.rsplit("/", 1)[0], unreal.Material, factory)
    base = unreal.MaterialEditingLibrary.create_material_expression(material, unreal.MaterialExpressionVectorParameter, -560, -80)
    base.set_editor_property("parameter_name", "FoliageTint")
    base.set_editor_property("default_value", unreal.LinearColor(0.12, 0.38, 0.17, 1.0))
    rough = unreal.MaterialEditingLibrary.create_material_expression(material, unreal.MaterialExpressionScalarParameter, -560, 80)
    rough.set_editor_property("parameter_name", "Roughness")
    rough.set_editor_property("default_value", 0.72)
    strength = unreal.MaterialEditingLibrary.create_material_expression(material, unreal.MaterialExpressionScalarParameter, -560, 220)
    strength.set_editor_property("parameter_name", "WindStrength")
    strength.set_editor_property("default_value", 0.24)
    speed = unreal.MaterialEditingLibrary.create_material_expression(material, unreal.MaterialExpressionScalarParameter, -560, 330)
    speed.set_editor_property("parameter_name", "WindSpeed")
    speed.set_editor_property("default_value", 0.75)
    clock = unreal.MaterialEditingLibrary.create_material_expression(material, unreal.MaterialExpressionTime, -560, 440)
    phase = unreal.MaterialEditingLibrary.create_material_expression(material, unreal.MaterialExpressionMultiply, -360, 380)
    wave = unreal.MaterialEditingLibrary.create_material_expression(material, unreal.MaterialExpressionSine, -170, 380)
    offset = unreal.MaterialEditingLibrary.create_material_expression(material, unreal.MaterialExpressionMultiply, 20, 380)
    zero = unreal.MaterialEditingLibrary.create_material_expression(material, unreal.MaterialExpressionConstant, -170, 520)
    zero.set_editor_property("r", 0.0)
    xy = unreal.MaterialEditingLibrary.create_material_expression(material, unreal.MaterialExpressionAppendVector, 200, 390)
    xyz = unreal.MaterialEditingLibrary.create_material_expression(material, unreal.MaterialExpressionAppendVector, 390, 390)
    unreal.MaterialEditingLibrary.connect_material_expressions(clock, "", phase, "A")
    unreal.MaterialEditingLibrary.connect_material_expressions(speed, "", phase, "B")
    unreal.MaterialEditingLibrary.connect_material_expressions(phase, "", wave, "")
    unreal.MaterialEditingLibrary.connect_material_expressions(wave, "", offset, "A")
    unreal.MaterialEditingLibrary.connect_material_expressions(strength, "", offset, "B")
    unreal.MaterialEditingLibrary.connect_material_expressions(offset, "", xy, "A")
    unreal.MaterialEditingLibrary.connect_material_expressions(zero, "", xy, "B")
    unreal.MaterialEditingLibrary.connect_material_expressions(xy, "", xyz, "A")
    unreal.MaterialEditingLibrary.connect_material_expressions(zero, "", xyz, "B")
    unreal.MaterialEditingLibrary.connect_material_property(base, "", unreal.MaterialProperty.MP_BASE_COLOR)
    unreal.MaterialEditingLibrary.connect_material_property(rough, "", unreal.MaterialProperty.MP_ROUGHNESS)
    unreal.MaterialEditingLibrary.connect_material_property(xyz, "", unreal.MaterialProperty.MP_WORLD_POSITION_OFFSET)
    unreal.MaterialEditingLibrary.recompile_material(material)
    unreal.EditorAssetLibrary.set_metadata_tag(material, "ArtFlow.FoliageRequestSha256", request["request_sha256"])
    unreal.EditorAssetLibrary.save_loaded_asset(material, only_if_is_dirty=False)

instance_paths = {}
tints = {"reed": unreal.LinearColor(0.08, 0.34, 0.20, 1), "fern": unreal.LinearColor(0.16, 0.46, 0.18, 1),
         "broadleaf": unreal.LinearColor(0.30, 0.42, 0.11, 1)}
spec_by_id = {item["species_id"]: item for item in request["species"]}
for species, mesh in meshes.items():
    package = f"/Game/ArtFlow/Generated/Materials/Foliage/MI_AF_{species.title()}_{identity}"
    name = package.rsplit("/", 1)[-1]
    instance = unreal.EditorAssetLibrary.load_asset(f"{package}.{name}")
    if instance is None:
        instance = unreal.AssetToolsHelpers.get_asset_tools().create_asset(name, package.rsplit("/", 1)[0], unreal.MaterialInstanceConstant, unreal.MaterialInstanceConstantFactoryNew())
        unreal.MaterialEditingLibrary.set_material_instance_parent(instance, material)
        unreal.MaterialEditingLibrary.set_material_instance_vector_parameter_value(instance, "FoliageTint", tints[species])
        unreal.MaterialEditingLibrary.set_material_instance_scalar_parameter_value(instance, "WindStrength", spec_by_id[species]["wind_strength"])
        unreal.MaterialEditingLibrary.set_material_instance_scalar_parameter_value(instance, "WindSpeed", spec_by_id[species]["wind_speed"])
        unreal.EditorAssetLibrary.set_metadata_tag(instance, "ArtFlow.FoliageRequestSha256", request["request_sha256"])
        unreal.EditorAssetLibrary.save_loaded_asset(instance, only_if_is_dirty=False)
    mesh.set_material(0, instance)
    unreal.EditorAssetLibrary.save_loaded_asset(mesh, only_if_is_dirty=False)
    instance_paths[species] = instance.get_path_name()

graph_package = f"/Game/ArtFlow/PCG/Generated/PCG_AF_Foliage_{identity}"
graph_name = graph_package.rsplit("/", 1)[-1]
graph = unreal.EditorAssetLibrary.load_asset(f"{graph_package}.{graph_name}")
graph_reconciled = isinstance(graph, unreal.PCGGraph)
if graph is None:
    graph = unreal.EditorAssetLibrary.duplicate_asset("/Game/ArtFlow/PCG/PCG_ArtFlowScatter.PCG_ArtFlowScatter", graph_package)
    if not isinstance(graph, unreal.PCGGraph):
        fail("could not derive project PCG graph")
    point_settings = next((node.get_settings() for node in graph.get_editor_property("nodes") if isinstance(node.get_settings(), unreal.PCGCreatePointsSettings)), None)
    spawner = next((node.get_settings() for node in graph.get_editor_property("nodes") if isinstance(node.get_settings(), unreal.PCGStaticMeshSpawnerSettings)), None)
    if point_settings is None or spawner is None:
        fail("project PCG template changed")
    points = []
    for item in manifest["placements"]:
        point = unreal.PCGPoint()
        point.set_editor_property("transform", unreal.Transform(
            location=unreal.Vector(*item["location_cm"]), rotation=unreal.Rotator(0, item["yaw_deg"], 0),
            scale=unreal.Vector(item["scale"], item["scale"], item["scale"])))
        point.set_editor_property("density", 1.0)
        point.set_editor_property("seed", item["seed"])
        points.append(point)
    point_settings.set_editor_property("points_to_create", points)
    point_settings.set_editor_property("coordinate_space", unreal.PCGCoordinateSpace.WORLD)
    entries = []
    for species in ("reed", "fern", "broadleaf"):
        descriptor = unreal.PCGSoftISMComponentDescriptor()
        descriptor.set_editor_property("static_mesh", meshes[species])
        descriptor.set_editor_property("additional_comma_separated_tags", f"ArtFlow.Generated,ArtFlow.Foliage.{species}")
        entry = unreal.PCGMeshSelectorWeightedEntry(weight=1)
        entry.set_editor_property("descriptor", descriptor)
        entries.append(entry)
    selector = spawner.get_editor_property("mesh_selector_parameters")
    selector.set_editor_property("mesh_entries", entries)
    spawner.set_editor_property("synchronous_load", True)
    unreal.EditorAssetLibrary.set_metadata_tag(graph, "ArtFlow.FoliageRequestSha256", request["request_sha256"])
    unreal.EditorAssetLibrary.save_loaded_asset(graph, only_if_is_dirty=False)

candidate_name = f"Foliage_B_{identity}"
candidate_package = f"/Game/ArtFlow/Sessions/AF_dc31f6ed0f4e/Candidates/{candidate_name}"
candidate_object = f"{candidate_package}.{candidate_name}"
candidate_reconciled = unreal.EditorAssetLibrary.does_asset_exist(candidate_object)
if not candidate_reconciled:
    candidate = unreal.EditorAssetLibrary.duplicate_asset(request["source_candidate_scene_path"], candidate_package)
    if candidate is None:
        fail("could not derive foliage candidate")
    unreal.EditorAssetLibrary.save_loaded_asset(candidate, only_if_is_dirty=False)
    del candidate
    unreal.SystemLibrary.collect_garbage()
world = unreal.EditorLoadingAndSavingUtils.load_map(candidate_package)
subsystem = unreal.get_editor_subsystem(unreal.EditorActorSubsystem)
actors = subsystem.get_all_level_actors()
target = next((actor for actor in actors if actor.get_actor_label() == "Editable_Form"), None)
if target is None:
    fail("registered PCG target actor is missing")
pcgs = target.get_components_by_class(unreal.PCGComponent)
if len(pcgs) != 1:
    fail("registered target must contain one PCG component")
pcg = pcgs[0]
already_applied = candidate_reconciled and pcg.get_graph() == graph and int(pcg.get_editor_property("seed")) == request["seed"]
pcg.cleanup_local(True)
pcg.set_graph(graph)
pcg.set_editor_property("seed", request["seed"])
pcg.generate_local(True)

screenshot = evidence / "unreal-biome-foliage-candidate.png"
if screenshot.is_file():
    screenshot.unlink()
camera = next((actor for actor in actors if actor.get_actor_label() == "ArtFlow_Camera"), None)
state = {"ticks": 0, "phase": "generation", "callback": None}


def instance_count():
    return sum(component.get_instance_count() for actor in subsystem.get_all_level_actors()
               for component in actor.get_components_by_class(unreal.InstancedStaticMeshComponent))


def finish():
    unreal.EditorLoadingAndSavingUtils.save_map(world, candidate_package)
    source_after = sha256(source_file)
    if source_after != source_before:
        fail("foliage route changed the upstream terrain candidate")
    count = instance_count()
    if count != request["instance_budget"]:
        fail(f"foliage PCG produced {count} instances instead of {request['instance_budget']}")
    result = {"schema_id": "artflow-unreal-biome-foliage-receipt/1", "request_sha256": request["request_sha256"],
              "blender_receipt_sha256": blender["receipt_sha256"], "status": "reconciled" if assets_reconciled and material_reconciled and graph_reconciled and candidate_reconciled and already_applied else "generated",
              "engine_version": unreal.SystemLibrary.get_engine_version(), "source_candidate_scene_path": request["source_candidate_scene_path"],
              "candidate_scene_path": candidate_package, "mesh_paths": {key: value.get_path_name() for key, value in meshes.items()},
              "lod_counts": lod_counts, "collision_counts": collision_counts, "wind_master_material_path": material.get_path_name(),
              "wind_material_instance_paths": instance_paths, "native_pcg_graph_path": graph.get_path_name(),
              "foliage_instance_count": count, "duplicate_side_effect_count": 0,
              "source_candidate_sha256_before": source_before, "source_candidate_sha256_after": source_after,
              "screenshot_path": screenshot.name, "screenshot_sha256": sha256(screenshot) if screenshot.is_file() else None,
              "capture_status": "captured" if screenshot.is_file() else "unavailable",
              "completed_at": datetime.now(UTC).isoformat().replace("+00:00", "Z")}
    result["receipt_sha256"] = canonical(result)
    (evidence / "unreal-biome-foliage-receipt.json").write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8")
    unreal.log(f"ARTFLOW_FOLIAGE_RETURN status={result['status']} instances={count}")
    if state["callback"] is not None:
        unreal.unregister_slate_post_tick_callback(state["callback"])
    unreal.SystemLibrary.quit_editor()


def on_tick(_delta):
    state["ticks"] += 1
    if state["phase"] == "generation":
        if instance_count() != request["instance_budget"]:
            if state["ticks"] > 1800:
                fail("timed out waiting for foliage PCG")
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
unreal.log("ARTFLOW_FOLIAGE_PENDING waiting for native PCG generation")
