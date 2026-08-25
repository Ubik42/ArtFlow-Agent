from __future__ import annotations

import argparse
import json
from pathlib import Path

from artflow_agent.contracts import ProviderCapabilityManifest, SceneConstraintPackage

ROOT = Path(__file__).resolve().parents[1]
SCHEMAS = {
    "provider-capability-manifest.v1.schema.json": ProviderCapabilityManifest.model_json_schema(),
    "scene-constraint-package.v1.schema.json": SceneConstraintPackage.model_json_schema(),
}


def serialized(schema: dict[str, object]) -> str:
    return json.dumps(schema, indent=2, ensure_ascii=False, sort_keys=True) + "\n"


def main() -> int:
    parser = argparse.ArgumentParser(description="Export ArtFlow cross-language JSON Schemas.")
    parser.add_argument("--check", action="store_true", help="Fail if generated schemas differ.")
    args = parser.parse_args()
    output_dir = ROOT / "contracts"

    stale: list[str] = []
    for name, schema in SCHEMAS.items():
        path = output_dir / name
        expected = serialized(schema)
        if args.check:
            if not path.is_file() or path.read_text(encoding="utf-8") != expected:
                stale.append(name)
        else:
            output_dir.mkdir(parents=True, exist_ok=True)
            path.write_text(expected, encoding="utf-8")

    if stale:
        parser.error("stale generated schemas: " + ", ".join(stale))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

