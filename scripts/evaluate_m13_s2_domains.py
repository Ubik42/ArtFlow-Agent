from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path

from PIL import Image, ImageStat

from artflow_agent.pbr import canonical_sha256
from artflow_agent.scene_session import (
    DOMAIN_ORDER,
    SceneCandidateDomainEvaluation,
    SceneCandidatePlan,
    SceneDomainCorrectionPlan,
    SceneDomainFinding,
)


def file_sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def seal_evaluation(payload: dict[str, object]) -> SceneCandidateDomainEvaluation:
    digest = canonical_sha256(payload)
    return SceneCandidateDomainEvaluation(
        evaluation_id=f"domain-evaluation-{digest[:12]}",
        evaluation_sha256=digest,
        **payload,
    )


def main() -> int:
    parser = argparse.ArgumentParser(description="Evaluate M13-S2 scene domains and seal a narrow correction.")
    parser.add_argument("--plan", type=Path, required=True)
    parser.add_argument("--technical", type=Path, required=True)
    parser.add_argument("--candidate-image", type=Path, required=True)
    parser.add_argument("--evaluation", type=Path, required=True)
    parser.add_argument("--correction-plan", type=Path)
    parser.add_argument("--lighting-request", type=Path)
    args = parser.parse_args()

    plan = SceneCandidatePlan.model_validate_json(args.plan.read_text(encoding="utf-8"))
    technical = json.loads(args.technical.read_text(encoding="utf-8"))
    operations = {item.domain: item.model_dump(mode="json") for item in plan.operations}
    checks = technical["checks"]
    luma = round(ImageStat.Stat(Image.open(args.candidate_image).convert("L")).mean[0], 3)
    domain_pass = {
        "image": file_sha256(args.candidate_image) == technical["candidate_beauty_sha256"],
        "material": bool(checks["material_instance_matches"]),
        "asset": bool(checks["project_asset_set_matches"]),
        "pcg": bool(checks["pcg_budget_ok"]) and checks["pcg_instance_count"] == 12,
        "lighting": 4.5 <= float(checks["lighting_intensity"]) <= 8.5
        and 3500 <= float(checks["lighting_temperature_kelvin"]) <= 5200
        and luma >= 125.0,
    }
    reasons = {
        "image": "候选画面与宿主回执逐字节一致",
        "material": "验证过的 PBR 材质实例保持绑定",
        "asset": "项目资产集合与允许清单一致",
        "pcg": "PCG 生成 12 个实例且未越过预算",
        "lighting": (
            f"主光 {checks['lighting_intensity']} / {checks['lighting_temperature_kelvin']}K，"
            f"画面平均亮度 {luma}"
        ),
    }
    findings = []
    for domain in DOMAIN_ORDER:
        evidence = {
            "operation": operations[domain],
            "reason": reasons[domain],
        }
        findings.append(
            SceneDomainFinding(
                domain=domain,
                status="passed" if domain_pass[domain] else "failed",
                reason=reasons[domain],
                evidence_sha256=canonical_sha256(evidence),
            )
        )
    failed = [item.domain for item in findings if item.status == "failed"]
    payload = {
        "plan_sha256": plan.plan_sha256,
        "candidate_scene": plan.candidate_destination,
        "findings": [item.model_dump(mode="json") for item in findings],
        "failed_domains": failed,
        "status": "correction_required" if failed else "accepted",
    }
    evaluation = seal_evaluation(payload)
    args.evaluation.write_text(evaluation.model_dump_json(indent=2) + "\n", encoding="utf-8")

    if failed:
        if failed != ["lighting"] or not args.correction_plan or not args.lighting_request:
            raise SystemExit(f"unexpected or unhandled failed domains: {failed}")
        preserved = {
            item.domain: item.evidence_sha256
            for item in findings
            if item.status == "passed"
        }
        correction_payload = {
            "evaluation_sha256": evaluation.evaluation_sha256,
            "candidate_scene": plan.candidate_destination,
            "failed_domains": ["lighting"],
            "rerun_domains": ["lighting"],
            "preserved_evidence_sha256s": preserved,
            "lighting_intensity": 5.5,
            "lighting_temperature_kelvin": 4200.0,
        }
        correction_digest = canonical_sha256(correction_payload)
        correction = SceneDomainCorrectionPlan(
            correction_id=f"domain-correction-{correction_digest[:12]}",
            correction_sha256=correction_digest,
            **correction_payload,
        )
        args.correction_plan.write_text(correction.model_dump_json(indent=2) + "\n", encoding="utf-8")
        request = {
            "schema_id": "lighting-domain-patch-request/1",
            "request_id": f"lighting-patch-{correction_digest[:12]}",
            "purpose": "仅修正失败的光照域；图像目标、材质、资产和 PCG 证据保持不变",
            "candidate_scene_path": plan.candidate_destination,
            "source_scene_sha256": checks["source_level_sha256"],
            "protected_state_sha256": checks["protected_state_sha256"],
            "expected_material_path": technical["material_instance_path"],
            "expected_instance_count": checks["pcg_instance_count"],
            "intensity": correction.lighting_intensity,
            "temperature_kelvin": correction.lighting_temperature_kelvin,
            "correction_plan_sha256": correction.correction_sha256,
        }
        request["request_sha256"] = canonical_sha256(request)
        args.lighting_request.write_text(
            json.dumps(request, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
        )
    print(evaluation.model_dump_json(indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
