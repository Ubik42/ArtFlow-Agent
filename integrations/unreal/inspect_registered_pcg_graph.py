from __future__ import annotations

import json
from pathlib import Path

import unreal

repo = Path(__file__).resolve().parents[2]
output = repo / "artifacts/goal/m34-s1-pcg-density"
output.mkdir(parents=True, exist_ok=True)
graph = unreal.EditorAssetLibrary.load_asset("/Game/ArtFlow/PCG/PCG_ArtFlowScatter.PCG_ArtFlowScatter")
if graph is None:
    raise RuntimeError("registered PCG graph is missing")
graph_properties = sorted(name for name in dir(graph) if not name.startswith("_"))
try:
    graph_nodes = graph.get_editor_property("nodes")
except RuntimeError:
    graph_nodes = []
nodes = []
for node in graph_nodes:
    settings = node.get_settings()
    details = {}
    if settings and settings.get_class().get_name() == "PCGCreatePointsSettings":
        points = settings.get_editor_property("points_to_create")
        details["point_count"] = len(points)
        details["point_properties"] = sorted(
            name for name in dir(points[0]) if not name.startswith("_")
        ) if points else []
        details["points"] = [
            {
                "transform": str(point.get_editor_property("transform")),
                "density": point.get_editor_property("density"),
                "seed": point.get_editor_property("seed"),
            }
            for point in points
        ]
    if settings and settings.get_class().get_name() == "PCGStaticMeshSpawnerSettings":
        selector = settings.get_editor_property("mesh_selector_parameters")
        details["selector_class"] = selector.get_class().get_name() if selector else None
        details["selector_properties"] = sorted(
            name for name in dir(selector) if not name.startswith("_")
        ) if selector else []
        if selector and hasattr(selector, "mesh_entries"):
            entries = selector.get_editor_property("mesh_entries")
            details["mesh_entries"] = [
                {
                    "value": str(entry),
                    "properties": sorted(name for name in dir(entry) if not name.startswith("_")),
                    "descriptor": str(entry.get_editor_property("descriptor")),
                    "descriptor_properties": sorted(
                        name
                        for name in dir(entry.get_editor_property("descriptor"))
                        if not name.startswith("_")
                    ),
                    "descriptor_dict": str(entry.get_editor_property("descriptor").to_dict()),
                    "weight": entry.get_editor_property("weight"),
                }
                for entry in entries
            ]
    nodes.append(
        {
            "node_name": node.get_name(),
            "node_class": node.get_class().get_name(),
            "settings_class": settings.get_class().get_name() if settings else None,
            "settings_name": settings.get_name() if settings else None,
            "settings_properties": sorted(
                name for name in dir(settings) if not name.startswith("_")
            ) if settings else [],
            "details": details,
        }
    )
payload = {
    "schema_id": "artflow-pcg-graph-inspection/1",
    "engine_version": unreal.SystemLibrary.get_engine_version(),
    "graph_path": graph.get_path_name(),
    "graph_properties": graph_properties,
    "nodes": nodes,
}
(output / "registered-pcg-graph.json").write_text(
    json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
)
unreal.log(f"ARTFLOW_PCG_GRAPH_INSPECTED nodes={len(nodes)} graph={graph.get_path_name()}")
