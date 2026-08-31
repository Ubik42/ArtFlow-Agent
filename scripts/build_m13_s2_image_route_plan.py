from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path

from artflow_agent.pbr import canonical_sha256
from artflow_agent.scene_session import (
    SceneCandidateImageTargetToolCall,
    SceneCandidateLightingToolCall,
    SceneCandidatePlan,
)


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main() -> int:
    parser = argparse.ArgumentParser(description="Seal the M13-S2 GPT Image 2 route plan.")
    parser.add_argument("--base-plan", type=Path, required=True)
    parser.add_argument("--visual-receipt", type=Path, required=True)
    parser.add_argument("--base-host-receipt", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--host-receipt", type=Path, required=True)
    parser.add_argument("--lighting-intensity", type=float, default=0.05)
    parser.add_argument("--lighting-temperature", type=float, default=6500.0)
    args = parser.parse_args()
    base = SceneCandidatePlan.model_validate_json(args.base_plan.read_text(encoding="utf-8"))
    visual = json.loads(args.visual_receipt.read_text(encoding="utf-8"))
    if sha256(Path(visual["artifact_path"])) != visual["artifact_sha256"]:
        raise SystemExit("Codex visual-target artifact hash does not match its receipt")
    image = SceneCandidateImageTargetToolCall(
        operation_id="image-target-sunlit-overgrown",
        source_render_sha256=visual["source_render_sha256"],
        artifact_sha256=visual["artifact_sha256"],
        receipt_sha256=sha256(args.visual_receipt),
        preserve=visual["preserve"],
    )
    operations = [image]
    for item in base.operations:
        if isinstance(item, SceneCandidateLightingToolCall):
            operations.append(
                item.model_copy(
                    update={
                        "intensity": args.lighting_intensity,
                        "temperature_kelvin": args.lighting_temperature,
                    }
                )
            )
        else:
            operations.append(item)
    payload = base.model_dump(
        mode="json", exclude={"schema_id", "plan_id", "plan_sha256", "operations"}
    )
    payload["operations"] = [item.model_dump(mode="json") for item in operations]
    digest = canonical_sha256(payload)
    plan = SceneCandidatePlan(
        plan_id=f"candidate-plan-{digest[:12]}", plan_sha256=digest, **payload
    )
    args.output.write_text(plan.model_dump_json(indent=2) + "\n", encoding="utf-8")

    host = json.loads(args.base_host_receipt.read_text(encoding="utf-8"))
    receipt = host["artflow_receipt"]
    receipt["candidate_plan"] = plan.model_dump(mode="json")
    handshake_payload = {
        key: value
        for key, value in receipt.items()
        if key not in {"schema_id", "handshake_id", "handshake_sha256"}
    }
    handshake_digest = canonical_sha256(handshake_payload)
    receipt["handshake_id"] = f"scene-handshake-{handshake_digest[:12]}"
    receipt["handshake_sha256"] = handshake_digest
    args.host_receipt.write_text(json.dumps(host, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(plan.model_dump_json(indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
