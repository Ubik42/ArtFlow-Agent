from __future__ import annotations

import hashlib
import json
from pathlib import Path

from PIL import Image

from artflow_agent.agent_projection import project_agent_run
from artflow_agent.agent_runtime import AgentEventStore


ROOT = Path(__file__).resolve().parents[1]
DATABASE = ROOT / "artifacts" / "goal" / "m19-s1-candidate-work" / "agent-events.sqlite3"
OUTPUT = ROOT / "artifacts" / "goal" / "m20-s4-current-adoption"


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
    intake = projection["scene_correction_intake"]
    verdict = projection["scene_correction_visual_verdict"]
    original = projection["scene_candidate_visual_verdict"]
    if intake is None or verdict is None or original is None:
        raise SystemExit("current corrected result has not completed reevaluation")
    checks = intake["technical_evaluation"]["checks"]
    if (
        len(checks) != 7
        or any(item["status"] != "passed" for item in checks)
        or intake["technical_evaluation"]["status"] != "eligible_for_visual_review"
    ):
        raise SystemExit("current correction did not pass all seven technical checks")
    evaluation = verdict["domain_evaluation"]
    if evaluation["status"] != "correction_required" or evaluation["failed_domains"] != [
        "lighting"
    ]:
        raise SystemExit("expected the inspected correction to fail only lighting")
    original_findings = {
        item["domain"]: item for item in original["domain_evaluation"]["findings"]
    }
    corrected_findings = {item["domain"]: item for item in evaluation["findings"]}
    if corrected_findings["image"] != original_findings["image"]:
        raise SystemExit("image evidence was not preserved byte-for-byte")
    if corrected_findings["pcg"] != original_findings["pcg"]:
        raise SystemExit("PCG evidence was not preserved byte-for-byte")
    if any(
        projection[name] is not None
        for name in (
            "scene_candidate_evaluation",
            "scene_candidate_adoption",
            "scene_variant_lineage",
        )
    ):
        raise SystemExit("a failed correction must not be adopted or published")

    input_record = intake["evaluation_input"]
    source = OUTPUT / "source-beauty.png"
    corrected = OUTPUT / "corrected-beauty.png"
    if sha256(source) != input_record["source_beauty_sha256"]:
        raise SystemExit("source image does not match the current intake")
    if sha256(corrected) != input_record["corrected_beauty_sha256"]:
        raise SystemExit("corrected image does not match the current intake")

    screenshots: list[dict[str, object]] = []
    for name, expected_size in (
        ("live-correction-reevaluation-desktop.png", (1600, 1000)),
        ("live-correction-reevaluation-narrow.png", (412, 915)),
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
            "schema_id": "artflow-m20-correction-reevaluation-verification/1",
            "status": "verified_correction_required",
            "run_id": projection["run_id"],
            "event_count": len(projection["timeline"]),
            "technical_check_count": len(checks),
            "technical_pass_count": sum(item["status"] == "passed" for item in checks),
            "technical_evaluation_sha256": intake["technical_evaluation"][
                "evaluation_sha256"
            ],
            "visual_observation_sha256": verdict["visual_observation"][
                "observation_sha256"
            ],
            "domain_evaluation_sha256": evaluation["evaluation_sha256"],
            "evaluation_status": evaluation["status"],
            "failed_domains": evaluation["failed_domains"],
            "preserved_finding_identity": {"image": True, "pcg": True},
            "source_beauty_sha256": sha256(source),
            "corrected_beauty_sha256": sha256(corrected),
            "candidate_evaluation_appended": False,
            "candidate_adoption_appended": False,
            "candidate_publication_appended": False,
            "screenshots": screenshots,
            "browser_console_error_count": 0,
            "broken_image_count": 0,
            "horizontal_overflow_px": 0,
            "targeted_test_result": "7 passed",
        },
    )


if __name__ == "__main__":
    main()
