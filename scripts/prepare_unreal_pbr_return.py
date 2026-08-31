from __future__ import annotations

import argparse
from pathlib import Path

from artflow_agent.pbr_unreal import build_unreal_pbr_request

ROOT = Path(__file__).resolve().parents[1]


def main() -> int:
    parser = argparse.ArgumentParser(description="Seal one typed Unreal PBR material return request.")
    parser.add_argument("--receipt", type=Path, required=True)
    parser.add_argument("--textures", type=Path, required=True)
    parser.add_argument("--source-scene", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--material-id", default="ruin_altar_basalt")
    parser.add_argument("--destination-scene", default="/Game/ArtFlow/Staging/AF_cb2176a7a45bbad1")
    parser.add_argument("--material-instance-name", default="MI_RuinAltarBasalt")
    args = parser.parse_args()
    request = build_unreal_pbr_request(
        receipt_path=args.receipt,
        texture_root=args.textures,
        source_scene=args.source_scene,
        repo_root=ROOT,
        material_id=args.material_id,
        destination_scene_path=args.destination_scene,
        material_instance_name=args.material_instance_name,
    )
    args.output.parent.mkdir(parents=True, exist_ok=True)
    temporary = args.output.with_suffix(args.output.suffix + ".tmp")
    temporary.write_text(request.model_dump_json(indent=2) + "\n", encoding="utf-8")
    temporary.replace(args.output)
    print(request.model_dump_json(indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
