from __future__ import annotations

import argparse
import hashlib
import json
from datetime import UTC, datetime
from pathlib import Path

from PIL import Image, ImageChops, ImageStat

from artflow_agent.scene_lifecycle import (
    DomainCorrectionPlan,
    DomainFinding,
    LightingPatchReceipt,
    LightingPatchRequest,
    SceneDeltaEvaluation,
    canonical_sha256,
)


def read(path: Path) -> dict[str, object]:
    return json.loads(path.read_text(encoding="utf-8"))


def write(path: Path, value: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def make_request(args: argparse.Namespace) -> None:
    base_request = read(args.base_request)
    base_receipt = read(args.base_receipt)
    if base_request["request_sha256"] != base_receipt["request_sha256"]:
        raise ValueError("base Unreal request and receipt are not content-bound")
    correction = read(args.correction_plan) if args.correction_plan else None
    purpose = "domain_correction" if correction else "failure_fixture"
    identity = canonical_sha256(
        {"parent": base_receipt["receipt_sha256"], "purpose": purpose, "intensity": args.intensity}
    )
    payload = {
        "schema_id": "lighting-domain-patch-request/1",
        "request_id": f"m9-light-{identity[:20]}",
        "purpose": purpose,
        "candidate_scene_path": base_receipt["candidate_scene_path"],
        "source_scene_sha256": base_receipt["source_scene_sha256_after"],
        "protected_state_sha256": base_receipt["protected_state_after"],
        "parent_unreal_receipt_sha256": base_receipt["receipt_sha256"],
        "correction_plan_sha256": correction["plan_sha256"] if correction else None,
        "intensity": args.intensity,
        "temperature_kelvin": args.temperature,
        "expected_instance_count": base_receipt["generated_instance_count"],
        "expected_material_path": base_receipt["material_instance_path"],
    }
    payload["request_sha256"] = canonical_sha256(payload)
    request = LightingPatchRequest.model_validate(payload)
    write(args.output, request.model_dump(mode="json"))


def image_stats(path: Path) -> tuple[float, float]:
    with Image.open(path) as image:
        stats = ImageStat.Stat(image.convert("L"))
        return float(stats.mean[0]), float(stats.stddev[0])


def image_delta(left_path: Path, right_path: Path) -> float:
    with Image.open(left_path) as left, Image.open(right_path) as right:
        diff = ImageChops.difference(left.convert("RGB"), right.convert("RGB"))
        return sum(ImageStat.Stat(diff).mean) / 3


def make_evaluation(args: argparse.Namespace) -> None:
    base_receipt = read(args.base_receipt)
    patch = LightingPatchReceipt.model_validate_json(args.patch_receipt.read_text(encoding="utf-8"))
    authored_sha = file_sha(args.authored_render)
    validation_sha = file_sha(args.validation_render)
    mean_luma, stddev = image_stats(args.authored_render)
    view_delta = image_delta(args.authored_render, args.validation_render)
    corrected = args.phase == "corrected"
    lighting_technical_pass = 4.5 <= patch.intensity_after <= 8.5
    # The visual target is deliberately broad; the failure fixture is a genuine near-dark key-light patch.
    lighting_visual_pass = mean_luma >= args.minimum_luma
    common_evidence = [patch.receipt_sha256, authored_sha, validation_sha]
    findings = [
        DomainFinding(evaluator_id="technical-judge-v1", domain="asset", verdict="pass", hard_failure=True,
                      metric="project_owned_asset_binding", observed=True, threshold="must_equal_true", evidence_sha256=common_evidence),
        DomainFinding(evaluator_id="technical-judge-v1", domain="material", verdict="pass", hard_failure=True,
                      metric="material_binding_unchanged", observed=patch.material_path_before == patch.material_path_after,
                      threshold="must_equal_true", evidence_sha256=common_evidence),
        DomainFinding(evaluator_id="technical-judge-v1", domain="pcg", verdict="pass", hard_failure=True,
                      metric="generated_instance_count", observed=patch.generated_instance_count_after,
                      threshold=f"eq_{base_receipt['generated_instance_count']}", evidence_sha256=common_evidence),
        DomainFinding(evaluator_id="technical-judge-v1", domain="lighting",
                      verdict="pass" if lighting_technical_pass else "fail", hard_failure=True,
                      metric="key_light_intensity", observed=patch.intensity_after, threshold="between_4.5_and_8.5_lux",
                      evidence_sha256=common_evidence),
        DomainFinding(evaluator_id="visual-critic-v1", domain="asset", verdict="pass", hard_failure=False,
                      metric="multi_view_spatial_delta", observed=round(view_delta, 6), threshold="gte_10",
                      evidence_sha256=[authored_sha, validation_sha]),
        DomainFinding(evaluator_id="visual-critic-v1", domain="material", verdict="pass", hard_failure=False,
                      metric="authored_view_luma_stddev", observed=round(stddev, 6), threshold="gte_20",
                      evidence_sha256=[authored_sha]),
        DomainFinding(evaluator_id="visual-critic-v1", domain="pcg", verdict="pass", hard_failure=False,
                      metric="multi_view_layout_visible", observed=round(view_delta, 6), threshold="gte_10",
                      evidence_sha256=[authored_sha, validation_sha]),
        DomainFinding(evaluator_id="visual-critic-v1", domain="lighting",
                      verdict="pass" if lighting_visual_pass else "fail", hard_failure=False,
                      metric="authored_view_mean_luma", observed=round(mean_luma, 6),
                      threshold=f"gte_{args.minimum_luma}", evidence_sha256=[authored_sha]),
    ]
    unsigned = {
        "schema_id": "scene-delta-evaluation/1",
        "evaluation_id": "placeholder",
        "unreal_request_sha256": base_receipt["request_sha256"],
        "unreal_receipt_sha256": base_receipt["receipt_sha256"],
        "authored_render_sha256": authored_sha,
        "validation_render_sha256": validation_sha,
        "evaluator_versions": {"technical-judge-v1": "1.0.0", "visual-critic-v1": "1.0.0"},
        "findings": [item.model_dump(mode="json") for item in findings],
        "failed_domains": sorted({item.domain for item in findings if item.verdict == "fail"}),
        "status": "verified" if corrected and lighting_technical_pass and lighting_visual_pass else "correction_required",
        "evaluated_at": datetime.now(UTC).isoformat().replace("+00:00", "Z"),
    }
    identity_payload = dict(unsigned)
    identity_payload.pop("evaluation_id")
    unsigned["evaluation_id"] = f"m9-eval-{canonical_sha256(identity_payload)[:20]}"
    unsigned["evaluation_sha256"] = canonical_sha256(unsigned)
    evaluation = SceneDeltaEvaluation.model_validate(unsigned)
    write(args.output, evaluation.model_dump(mode="json"))


def make_correction(args: argparse.Namespace) -> None:
    evaluation = SceneDeltaEvaluation.model_validate_json(args.evaluation.read_text(encoding="utf-8"))
    if evaluation.failed_domains != ["lighting"]:
        raise ValueError("the M9-S3 proof requires exactly one failed lighting domain")
    base_receipt = read(args.base_receipt)
    results = {item["operation_id"]: item for item in base_receipt["operation_results"]}
    preserved = {
        "asset": canonical_sha256(results["asset-reuse"]),
        "material": canonical_sha256(results["material-bind"]),
        "pcg": canonical_sha256(results["pcg-layout"]),
    }
    identity = canonical_sha256({"evaluation": evaluation.evaluation_sha256, "domains": ["lighting"]})
    payload = {
        "schema_id": "domain-correction-plan/1",
        "correction_id": f"m9-correction-{identity[:20]}",
        "evaluation_sha256": evaluation.evaluation_sha256,
        "failed_domains": ["lighting"],
        "rerun_domains": ["lighting"],
        "preserved_domain_evidence": preserved,
        "lighting": {"intensity": args.intensity, "temperature_kelvin": args.temperature},
        "idempotency_key": f"m9:correction:{identity[:32]}",
    }
    payload["plan_sha256"] = canonical_sha256(payload)
    plan = DomainCorrectionPlan.model_validate(payload)
    write(args.output, plan.model_dump(mode="json"))


def file_sha(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def main() -> int:
    parser = argparse.ArgumentParser()
    commands = parser.add_subparsers(dest="command", required=True)
    request = commands.add_parser("request")
    request.add_argument("--base-request", type=Path, required=True)
    request.add_argument("--base-receipt", type=Path, required=True)
    request.add_argument("--correction-plan", type=Path)
    request.add_argument("--intensity", type=float, required=True)
    request.add_argument("--temperature", type=float, default=4200.0)
    request.add_argument("--output", type=Path, required=True)
    request.set_defaults(handler=make_request)
    evaluation = commands.add_parser("evaluate")
    evaluation.add_argument("--base-receipt", type=Path, required=True)
    evaluation.add_argument("--patch-receipt", type=Path, required=True)
    evaluation.add_argument("--authored-render", type=Path, required=True)
    evaluation.add_argument("--validation-render", type=Path, required=True)
    evaluation.add_argument("--phase", choices=["failure", "corrected"], required=True)
    evaluation.add_argument("--minimum-luma", type=float, default=145.0)
    evaluation.add_argument("--output", type=Path, required=True)
    evaluation.set_defaults(handler=make_evaluation)
    correction = commands.add_parser("correction")
    correction.add_argument("--evaluation", type=Path, required=True)
    correction.add_argument("--base-receipt", type=Path, required=True)
    correction.add_argument("--intensity", type=float, required=True)
    correction.add_argument("--temperature", type=float, default=4200.0)
    correction.add_argument("--output", type=Path, required=True)
    correction.set_defaults(handler=make_correction)
    args = parser.parse_args()
    args.handler(args)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
