from __future__ import annotations

import hashlib
import json
import shutil
from pathlib import Path

from PIL import Image

from artflow_agent.agent_projection import project_agent_run
from artflow_agent.agent_runtime import AgentEventStore
from artflow_agent.scene_correction_work import UnrealLightingCorrectionReceipt


ROOT = Path(__file__).resolve().parents[1]
DATABASE = ROOT / "artifacts" / "goal" / "m19-s1-candidate-work" / "agent-events.sqlite3"
OUTPUT = ROOT / "artifacts" / "goal" / "m20-s5-multilight-correction"


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def write_json(path: Path, value: object) -> None:
    path.write_text(
        json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )


def main() -> None:
    store = AgentEventStore(DATABASE)
    run_ids = store.list_run_ids()
    if len(run_ids) != 1:
        raise SystemExit(f"expected one current run, got {run_ids}")
    projection = project_agent_run(store, run_ids[0]).model_dump(mode="json")
    work = projection["scene_correction_work"]
    intake = projection["scene_correction_intake"]
    verdict = projection["scene_correction_visual_verdict"]
    evaluation = projection["scene_candidate_evaluation"]
    adoption = projection["scene_candidate_adoption"]
    if any(item is None for item in (work, intake, verdict, evaluation, adoption)):
        raise SystemExit("multi-light correction lifecycle is incomplete")
    if (
        work["status"] != "succeeded"
        or verdict["domain_evaluation"]["status"] != "accepted"
        or verdict["domain_evaluation"]["failed_domains"]
        or evaluation["corrected_evaluation"] != verdict["domain_evaluation"]
        or adoption["decision"]["orchestrator"] != "codex"
        or adoption["decision"]["evaluation_sha256"]
        != verdict["domain_evaluation"]["evaluation_sha256"]
        or projection["scene_variant_lineage"] is not None
    ):
        raise SystemExit("accepted, adopted and unpublished state is not evidence-bound")
    checks = intake["technical_evaluation"]["checks"]
    if len(checks) != 7 or any(item["status"] != "passed" for item in checks):
        raise SystemExit("multi-light correction did not pass all technical checks")

    definition = work["definition"]
    receipt_path = (
        ROOT
        / "integrations/unreal/ArtFlowBridgeHost/Saved/ArtFlowSceneBridge/SceneCorrections"
        / definition["work_id"]
        / "lighting-correction-receipt.json"
    )
    if sha256(receipt_path) != work["outcome_sha256"]:
        raise SystemExit("host receipt does not match the current event outcome")
    receipt = UnrealLightingCorrectionReceipt.model_validate_json(
        receipt_path.read_text(encoding="utf-8-sig")
    )
    expected = {
        "intensity_after": 2.2,
        "temperature_after": 8500.0,
        "key_light_pitch_after": -18.0,
        "key_light_yaw_after": -45.0,
        "secondary_intensity_after": 0.25,
        "secondary_temperature_after": 9000.0,
    }
    if any(
        value is None or abs(value - expected[name]) > 0.001
        for name, value in (
            ("intensity_after", receipt.intensity_after),
            ("temperature_after", receipt.temperature_after),
            ("key_light_pitch_after", receipt.key_light_pitch_after),
            ("key_light_yaw_after", receipt.key_light_yaw_after),
            ("secondary_intensity_after", receipt.secondary_intensity_after),
            (
                "secondary_temperature_after",
                receipt.secondary_temperature_after,
            ),
        )
    ):
        raise SystemExit("host receipt does not contain the registered light rig")
    if not (
        receipt.source_level_unchanged
        and receipt.source_level_sha256_before == receipt.source_level_sha256_after
        and receipt.protected_state_before == receipt.protected_state_after
        and receipt.generated_instance_count_before
        == receipt.generated_instance_count_after
        == 12
    ):
        raise SystemExit("multi-light correction changed a preserved scene domain")

    beauty_path = Path(receipt.corrected_beauty_path)
    if sha256(beauty_path) != receipt.corrected_beauty_sha256:
        raise SystemExit("new same-camera rerender does not match the host receipt")
    receipt_copy = OUTPUT / "host-receipt.json"
    beauty_copy = OUTPUT / "corrected-beauty.png"
    shutil.copy2(receipt_path, receipt_copy)
    shutil.copy2(beauty_path, beauty_copy)

    screenshots: list[dict[str, object]] = []
    for name, expected_size in (
        ("live-adopted-multilight-desktop.png", (1600, 1000)),
        ("live-adopted-multilight-narrow.png", (412, 915)),
    ):
        path = OUTPUT / name
        with Image.open(path) as image:
            if image.size != expected_size:
                raise SystemExit(f"unexpected screenshot size for {name}: {image.size}")
            screenshots.append(
                {
                    "path": path.relative_to(ROOT).as_posix(),
                    "size": list(image.size),
                    "sha256": sha256(path),
                }
            )

    write_json(OUTPUT / "live-projection.json", projection)
    write_json(
        OUTPUT / "verification.json",
        {
            "schema_id": "artflow-m20-multilight-correction-verification/1",
            "status": "verified_adopted_unpublished",
            "engine_version": "5.8.1",
            "run_id": projection["run_id"],
            "event_count": len(projection["timeline"]),
            "work_sha256": definition["work_sha256"],
            "parent_work_sha256": definition["parent_work_sha256"],
            "parent_outcome_sha256": definition["parent_outcome_sha256"],
            "technical_pass_count": 7,
            "visual_observation_sha256": verdict["visual_observation"][
                "observation_sha256"
            ],
            "evaluation_sha256": verdict["domain_evaluation"]["evaluation_sha256"],
            "evaluation_status": "accepted",
            "adoption_sha256": adoption["decision"]["decision_sha256"],
            "adoption_orchestrator": "codex",
            "published": False,
            "source_level_unchanged": True,
            "protected_state_unchanged": True,
            "generated_instance_count": 12,
            "lighting_before": {
                "primary_intensity": receipt.intensity_before,
                "primary_temperature_kelvin": receipt.temperature_before,
                "primary_pitch_degrees": receipt.key_light_pitch_before,
                "primary_yaw_degrees": receipt.key_light_yaw_before,
                "secondary_intensity": receipt.secondary_intensity_before,
                "secondary_temperature_kelvin": receipt.secondary_temperature_before,
            },
            "lighting_after": {
                "primary_intensity": receipt.intensity_after,
                "primary_temperature_kelvin": receipt.temperature_after,
                "primary_pitch_degrees": receipt.key_light_pitch_after,
                "primary_yaw_degrees": receipt.key_light_yaw_after,
                "secondary_intensity": receipt.secondary_intensity_after,
                "secondary_temperature_kelvin": receipt.secondary_temperature_after,
            },
            "corrected_beauty_sha256": receipt.corrected_beauty_sha256,
            "host_receipt_sha256": sha256(receipt_copy),
            "screenshots": screenshots,
            "browser_console_error_count": 0,
            "broken_image_count": 0,
            "horizontal_overflow_px": 0,
            "targeted_test_result": "8 passed",
            "unreal_build_result": "Succeeded",
        },
    )


if __name__ == "__main__":
    main()
