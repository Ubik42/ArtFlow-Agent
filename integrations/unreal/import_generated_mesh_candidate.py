from __future__ import annotations

import hashlib
import json
import os
from datetime import UTC, datetime
from pathlib import Path

import unreal


def canonical_sha256(value: object) -> str:
    return hashlib.sha256(
        json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode()
    ).hexdigest()


def file_sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def fail(message: str) -> None:
    raise RuntimeError(f"ArtFlow generated mesh admission failed closed: {message}")


repo_root = Path(os.environ["ARTFLOW_REPO_ROOT"]).resolve()
request_path = Path(os.environ["ARTFLOW_MESH_ADMISSION_REQUEST"]).resolve()
result_path = Path(os.environ["ARTFLOW_MESH_ADMISSION_RESULT"]).resolve()
if not request_path.is_relative_to(repo_root) or not result_path.is_relative_to(repo_root):
    fail("request or result escaped the repository")
request = json.loads(request_path.read_text(encoding="utf-8"))
if request.get("schema_id") != "unreal-mesh-admission-request/1":
    fail("unsupported request schema")
unsigned = dict(request)
unsigned.pop("request_sha256", None)
if canonical_sha256(unsigned) != request.get("request_sha256"):
    fail("request fingerprint mismatch")
if request.get("authority_scope") != "project_local_unreal_fixture":
    fail("authority scope is not project-local")
destination_root = request.get("destination_root", "")
if not destination_root.startswith("/Game/ArtFlow/Generated/m10_"):
    fail("destination escaped the generated quarantine namespace")
candidate = (repo_root / request["candidate_relative_path"]).resolve()
if not candidate.is_relative_to(repo_root) or candidate.suffix.lower() != ".glb":
    fail("candidate path escaped or is not GLB")
if file_sha256(candidate) != request.get("candidate_sha256"):
    fail("candidate bytes do not match the admitted hash")

project_root = Path(unreal.Paths.project_dir()).resolve()
source_map = project_root / "Content/ArtFlowDemo.umap"
source_before = file_sha256(source_map)
if source_before != request.get("source_scene_sha256"):
    fail("source scene fingerprint changed before import")

asset_name = request["asset_name"]
mesh_path = (
    f"{destination_root}/altar-triposr/StaticMeshes/{asset_name}.{asset_name}"
)
mesh = (
    unreal.EditorAssetLibrary.load_asset(mesh_path)
    if unreal.EditorAssetLibrary.does_asset_exist(mesh_path)
    else None
)
reconciled = mesh is not None
imported_paths: list[str] = []
if mesh is not None:
    recorded_hash = unreal.EditorAssetLibrary.get_metadata_tag(mesh, "ArtFlow.SourceSha256")
    if recorded_hash != request["candidate_sha256"]:
        import_data = mesh.get_editor_property("asset_import_data")
        imported_source = Path(import_data.get_first_filename()).resolve() if import_data else None
        if (
            recorded_hash
            or imported_source is None
            or not imported_source.is_file()
            or file_sha256(imported_source) != request["candidate_sha256"]
        ):
            fail("unrelated asset occupies deterministic generated mesh path")
    imported_paths = [mesh_path]
else:
    task = unreal.AssetImportTask()
    task.set_editor_property("filename", str(candidate))
    task.set_editor_property("destination_path", destination_root)
    task.set_editor_property("destination_name", asset_name)
    task.set_editor_property("automated", True)
    task.set_editor_property("replace_existing", False)
    task.set_editor_property("save", True)
    unreal.AssetToolsHelpers.get_asset_tools().import_asset_tasks([task])
    imported_paths = list(task.get_editor_property("imported_object_paths"))
    mesh = unreal.EditorAssetLibrary.load_asset(mesh_path)
    if mesh is None:
        for object_path in imported_paths:
            candidate_asset = unreal.EditorAssetLibrary.load_asset(object_path)
            if isinstance(candidate_asset, unreal.StaticMesh):
                mesh = candidate_asset
                mesh_path = object_path
                break
if not isinstance(mesh, unreal.StaticMesh):
    fail(f"Interchange created no StaticMesh; imported={imported_paths}")

material_name = "M_AF_GeneratedVertexColor"
material_path = f"{destination_root}/{material_name}.{material_name}"
material = (
    unreal.EditorAssetLibrary.load_asset(material_path)
    if unreal.EditorAssetLibrary.does_asset_exist(material_path)
    else None
)
if material is None:
    material = unreal.AssetToolsHelpers.get_asset_tools().create_asset(
        material_name, destination_root, unreal.Material, unreal.MaterialFactoryNew()
    )
material_source_hash = unreal.EditorAssetLibrary.get_metadata_tag(material, "ArtFlow.SourceSha256")
if material_source_hash not in {"", request["candidate_sha256"]}:
    fail("unrelated material occupies deterministic generated material path")
material_request_hash = unreal.EditorAssetLibrary.get_metadata_tag(material, "ArtFlow.RequestSha256")
if material_source_hash == "" and material_request_hash == "":
    vertex_color = unreal.MaterialEditingLibrary.create_material_expression(
        material, unreal.MaterialExpressionVertexColor, -260, 0
    )
    connected = unreal.MaterialEditingLibrary.connect_material_property(
        vertex_color, "RGB", unreal.MaterialProperty.MP_BASE_COLOR
    ) or unreal.MaterialEditingLibrary.connect_material_property(
        vertex_color, "", unreal.MaterialProperty.MP_BASE_COLOR
    )
    if not connected:
        fail("could not connect vertex color material")
    material.set_editor_property("two_sided", False)
    unreal.EditorAssetLibrary.set_metadata_tag(
        material, "ArtFlow.RequestSha256", request["request_sha256"]
    )
    unreal.MaterialEditingLibrary.recompile_material(material)
if unreal.EditorAssetLibrary.get_metadata_tag(material, "ArtFlow.UnlitVertexColor") != "1":
    unlit_vertex_color = unreal.MaterialEditingLibrary.create_material_expression(
        material, unreal.MaterialExpressionVertexColor, -260, 180
    )
    if not unreal.MaterialEditingLibrary.connect_material_property(
        unlit_vertex_color, "", unreal.MaterialProperty.MP_EMISSIVE_COLOR
    ):
        fail("could not connect unlit vertex color preview")
    material.set_editor_property("shading_model", unreal.MaterialShadingModel.MSM_UNLIT)
    unreal.EditorAssetLibrary.set_metadata_tag(material, "ArtFlow.UnlitVertexColor", "1")
    unreal.MaterialEditingLibrary.recompile_material(material)
unreal.EditorAssetLibrary.set_metadata_tag(
    material, "ArtFlow.SourceSha256", request["candidate_sha256"]
)
unreal.EditorAssetLibrary.set_metadata_tag(
    material, "ArtFlow.RequestSha256", request["request_sha256"]
)
unreal.EditorAssetLibrary.save_loaded_asset(material, only_if_is_dirty=False)
mesh.set_material(0, material)

static_mesh_library = unreal.EditorStaticMeshLibrary
if static_mesh_library.get_convex_collision_count(mesh) == 0:
    static_mesh_library.add_simple_collisions(mesh, unreal.ScriptingCollisionShapeType.NDOP10_X)
unreal.EditorAssetLibrary.set_metadata_tag(mesh, "ArtFlow.SourceSha256", request["candidate_sha256"])
unreal.EditorAssetLibrary.set_metadata_tag(mesh, "ArtFlow.RequestSha256", request["request_sha256"])
unreal.EditorAssetLibrary.set_metadata_tag(mesh, "ArtFlow.Provider", "stabilityai/TripoSR")
unreal.EditorAssetLibrary.save_loaded_asset(mesh, only_if_is_dirty=False)

vertex_count = static_mesh_library.get_number_verts(mesh, 0)
triangle_count = mesh.get_num_triangles(0)
collision_count = static_mesh_library.get_convex_collision_count(mesh)
bounds = mesh.get_bounds()
extent = bounds.box_extent
source_after = file_sha256(source_map)
if source_after != source_before:
    fail("source ArtFlowDemo changed during generated mesh import")
result = {
    "schema_id": "unreal-mesh-admission-receipt/1",
    "request_id": request["request_id"],
    "request_sha256": request["request_sha256"],
    "status": "reconciled" if reconciled else "imported",
    "engine_version": unreal.SystemLibrary.get_engine_version(),
    "static_mesh_path": mesh_path,
    "imported_object_paths": sorted(set(imported_paths + [mesh_path, material_path])),
    "vertex_count": vertex_count,
    "triangle_count": triangle_count,
    "material_slot_count": len(mesh.get_editor_property("static_materials")),
    "simple_collision_count": collision_count,
    "bounds_extent_cm": [extent.x, extent.y, extent.z],
    "source_scene_sha256_before": source_before,
    "source_scene_sha256_after": source_after,
    "duplicate_side_effect_count": 0,
    "completed_at": datetime.now(UTC).isoformat().replace("+00:00", "Z"),
}
result["receipt_sha256"] = canonical_sha256(result)
result_path.parent.mkdir(parents=True, exist_ok=True)
temporary = result_path.with_suffix(result_path.suffix + ".tmp")
temporary.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
temporary.replace(result_path)
unreal.log(f"ARTFLOW_GENERATED_MESH status={result['status']} mesh={mesh_path}")
