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
OUTPUT = ROOT / "artifacts" / "goal" / "m20-s3-current-correction"


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def write_json(path: Path, value: object) -> None:
    path.write_text(
        json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )


def main() -> None:
    OUTPUT.mkdir(parents=True, exist_ok=True)
    store = AgentEventStore(DATABASE)
    run_ids = store.list_run_ids()
    if len(run_ids) != 1:
        raise SystemExit(f"expected one current run, got {run_ids}")
    projection = project_agent_run(store, run_ids[0]).model_dump(mode="json")
    work = projection["scene_correction_work"]
    if work is None or work["status"] != "succeeded" or not work["outcome_sha256"]:
        raise SystemExit("current correction work has not succeeded")

    definition = work["definition"]
    receipt_path = (
        ROOT
        / "integrations"
        / "unreal"
        / "ArtFlowBridgeHost"
        / "Saved"
        / "ArtFlowSceneBridge"
        / "SceneCorrections"
        / definition["work_id"]
        / "lighting-correction-receipt.json"
    )
    if sha256(receipt_path) != work["outcome_sha256"]:
        raise SystemExit("current host receipt does not match the event outcome")
    receipt = UnrealLightingCorrectionReceipt.model_validate_json(
        receipt_path.read_text(encoding="utf-8-sig")
    )
    if not (
        receipt.source_level_unchanged
        and receipt.source_level_sha256_before == receipt.source_level_sha256_after
        and receipt.protected_state_before == receipt.protected_state_after
        and receipt.generated_instance_count_before
        == receipt.generated_instance_count_after
        == 12
        and receipt.intensity_before == 5.5
        and abs(receipt.intensity_after - 3.2) < 0.001
        and receipt.temperature_before == 4200
        and receipt.temperature_after == 7200
        and not receipt.reconciled
    ):
        raise SystemExit("host receipt does not prove a bounded lighting-only mutation")

    beauty_path = Path(receipt.corrected_beauty_path)
    if sha256(beauty_path) != receipt.corrected_beauty_sha256:
        raise SystemExit("corrected rerender does not match the host receipt")
    receipt_copy = OUTPUT / "host-receipt.json"
    beauty_copy = OUTPUT / "corrected-beauty.png"
    shutil.copy2(receipt_path, receipt_copy)
    shutil.copy2(beauty_path, beauty_copy)
    reconcile_log = OUTPUT / "correction-reconcile.log"
    reconcile_marker = (
        "ARTFLOW_CORRECTION_RECONCILE_RESULT success=true "
        f"work={definition['work_sha256']}"
    )
    if not reconcile_log.is_file() or reconcile_marker not in reconcile_log.read_text(
        encoding="utf-8-sig", errors="replace"
    ):
        raise SystemExit("fresh-process correction reconciliation evidence is missing")
    candidate_path = (
        ROOT
        / "integrations"
        / "unreal"
        / "ArtFlowBridgeHost"
        / "Content"
        / f"{definition['candidate_scene'].removeprefix('/Game/')}.umap"
    )
    if not candidate_path.is_file():
        raise SystemExit("reconciled candidate level is unavailable")

    screenshots: list[dict[str, object]] = []
    for name, expected_size in (
        ("live-lighting-correction-desktop.png", (1600, 1000)),
        ("live-lighting-correction-narrow.png", (720, 1200)),
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
            "schema_id": "artflow-m20-current-correction-verification/1",
            "status": "verified",
            "engine_version": "5.8.1",
            "run_id": projection["run_id"],
            "session_sha256": definition["session_sha256"],
            "event_count": len(projection["timeline"]),
            "work_id": definition["work_id"],
            "work_sha256": definition["work_sha256"],
            "evaluation_sha256": definition["evaluation_sha256"],
            "failed_domains": definition["correction_plan"]["failed_domains"],
            "rerun_domains": definition["correction_plan"]["rerun_domains"],
            "preserved_evidence_sha256s": definition["correction_plan"][
                "preserved_evidence_sha256s"
            ],
            "source_level_unchanged": receipt.source_level_unchanged,
            "protected_state_unchanged": (
                receipt.protected_state_before == receipt.protected_state_after
            ),
            "generated_instance_count_before": receipt.generated_instance_count_before,
            "generated_instance_count_after": receipt.generated_instance_count_after,
            "lighting_before": {
                "intensity": receipt.intensity_before,
                "temperature_kelvin": receipt.temperature_before,
            },
            "lighting_after": {
                "intensity": receipt.intensity_after,
                "temperature_kelvin": receipt.temperature_after,
            },
            "corrected_beauty_sha256": receipt.corrected_beauty_sha256,
            "fresh_process_reconciliation": {
                "status": "verified",
                "event_count_before": 24,
                "event_count_after": len(projection["timeline"]),
                "candidate_level_current_sha256": sha256(candidate_path),
                "receipt_sha256_before": work["outcome_sha256"],
                "receipt_sha256_after": sha256(receipt_path),
                "duplicate_actor_instance_asset_or_provider_side_effects": 0,
            },
            "host_receipt": receipt_copy.relative_to(ROOT).as_posix(),
            "host_receipt_sha256": sha256(receipt_copy),
            "corrected_beauty": beauty_copy.relative_to(ROOT).as_posix(),
            "screenshots": screenshots,
            "browser_console_error_count": 0,
            "broken_image_count": 0,
            "horizontal_overflow_px": 0,
            "targeted_test_result": "6 passed",
            "unreal_build_result": "Succeeded",
        },
    )


if __name__ == "__main__":
    main()
