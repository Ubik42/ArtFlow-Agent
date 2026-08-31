from __future__ import annotations

from pathlib import Path

from artflow_agent.agent_runtime import AgentEventStore
from artflow_agent.portfolio_release import build_release_archive, canonical_json_bytes

ROOT = Path(__file__).resolve().parents[1]
RUN_ROOT = ROOT / "artifacts/goal/m3-s11-local-run"
OUTPUT_ROOT = ROOT / "artifacts/goal/m14-s1-release"
RUN_ID = "local-artflow-ue-7e66ea0f40432643e4ac63a8f39f98c6-130c94284deb"


def source(relative: str, archive_path: str, role: str) -> tuple[Path, str, str]:
    path = (ROOT / relative).resolve()
    if not path.is_relative_to(ROOT):
        raise RuntimeError(f"Release source escaped repository: {relative}")
    return path, archive_path, role


def main() -> None:
    store = AgentEventStore(RUN_ROOT / "agent-events.sqlite3")
    state = store.load(RUN_ID)
    events = store.events(RUN_ID)
    if state.verified_delivery is None or state.harness_scorecard is None:
        raise RuntimeError("Portfolio release requires verified delivery and Harness evidence")
    local = state.provider_executions[0].receipt
    codex = state.codex_image_candidates[0].receipt
    negative = state.negative_controls[0].receipt
    if local is None:
        raise RuntimeError("Local provider receipt is missing")
    provider_root = "artifacts/goal/m3-s11-local-run/.agent-artifacts/provider-outputs"
    sources = [
        source("README.md", "docs/README.md", "product_readme"),
        source("PRODUCT.md", "docs/PRODUCT.md", "product_definition"),
        source("DESIGN.md", "docs/DESIGN.md", "design_system"),
        source("docs/portfolio-story.md", "docs/case-study.md", "portfolio_case_study"),
        source("docs/DEMO_GUIDE.md", "docs/demo-guide.md", "demo_guide"),
        source(
            "integrations/unreal/README.md",
            "docs/unreal-integration.md",
            "unreal_integration_guide",
        ),
        source(
            "docs/evidence/M13_S1_RAIN_WET_CROSS_PIPELINE_2026-08-30.md",
            "docs/evidence/m13-rain-wet-cross-pipeline.md",
            "m13_case_evidence",
        ),
        source(
            "docs/evidence/M13_S2_SUNLIT_IMAGE_ROUTE_CORRECTION_2026-08-30.md",
            "docs/evidence/m13-sunlit-domain-correction.md",
            "m13_case_evidence",
        ),
        source(
            "scripts/verify_portfolio_release_standalone.py",
            "tools/verify_release.py",
            "independent_verifier",
        ),
        source(
            "artifacts/goal/m5-s3-harness/harness-scorecard.json",
            "evidence/harness-scorecard.json",
            "harness_scorecard",
        ),
        source(
            "artifacts/goal/m5-s1-recovery/recovery-scorecard.json",
            "evidence/recovery-scorecard.json",
            "recovery_scorecard",
        ),
        source(
            "artifacts/goal/m5-s2-memory/memory-scorecard.json",
            "evidence/memory-scorecard.json",
            "memory_scorecard",
        ),
        source(
            "artifacts/goal/m6-s1-unreal-return/verified-delivery.json",
            "evidence/verified-delivery.json",
            "verified_delivery",
        ),
        source(
            "artifacts/goal/m6-s1-unreal-return/independent-verification.json",
            "evidence/provenance-verification.json",
            "provenance_verification",
        ),
        source(
            "artifacts/goal/m4-s3-bounded-revision/adoption-decision.json",
            "evidence/adoption-decision.json",
            "adoption_decision",
        ),
        source(
            "artifacts/goal/m4-s1-tribunal/tribunal-report.json",
            "evidence/tribunal-report.json",
            "deterministic_tribunal",
        ),
        source(
            "artifacts/goal/m4-s2-negative-control/multimodal-tribunal-report.json",
            "evidence/multimodal-tribunal-report.json",
            "multimodal_tribunal",
        ),
        source(
            "artifacts/goal/m8-s2-pbr-material/independent-verification.json",
            "evidence/m8-pbr-verification.json",
            "pbr_unreal_verification",
        ),
        source(
            "artifacts/goal/m9-s2-unreal-multi-domain/verification.json",
            "evidence/m9-multi-domain-verification.json",
            "multi_domain_verification",
        ),
        source(
            "artifacts/goal/m9-s3-correction-release/verification.json",
            "evidence/m9-correction-publish-verification.json",
            "correction_publish_verification",
        ),
        source(
            "artifacts/goal/m10-s1-mcp-facade/boundary-audit.json",
            "evidence/m10-mcp-boundary-audit.json",
            "mcp_boundary_audit",
        ),
        source(
            "artifacts/goal/m10-s2-image-to-3d/verification.json",
            "evidence/m10-image-to-3d-verification.json",
            "image_to_3d_verification",
        ),
        source(
            "artifacts/goal/m13-s1-rain-wet-courtyard/candidate-execution-receipt-reconciled.json",
            "evidence/m13-rain-candidate-reconcile.json",
            "m13_unreal_receipt",
        ),
        source(
            "artifacts/goal/m13-s1-rain-wet-courtyard/technical-evaluation.json",
            "evidence/m13-rain-technical-evaluation.json",
            "m13_domain_evaluation",
        ),
        source(
            "artifacts/goal/m13-s2-sunlit-overgrown/codex-image-target-receipt.json",
            "evidence/m13-sunlit-image-target.json",
            "m13_image_target_receipt",
        ),
        source(
            "artifacts/goal/m13-s2-sunlit-overgrown/failure-domain-evaluation.json",
            "evidence/m13-sunlit-failure-evaluation.json",
            "m13_domain_evaluation",
        ),
        source(
            "artifacts/goal/m13-s2-sunlit-overgrown/lighting-correction-plan.json",
            "evidence/m13-sunlit-correction-plan.json",
            "m13_correction_plan",
        ),
        source(
            "artifacts/goal/m13-s2-sunlit-overgrown/corrected-execution-receipt.json",
            "evidence/m13-sunlit-corrected-reconcile.json",
            "m13_unreal_receipt",
        ),
        source(
            "artifacts/goal/m13-s2-sunlit-overgrown/corrected-domain-evaluation.json",
            "evidence/m13-sunlit-corrected-evaluation.json",
            "m13_domain_evaluation",
        ),
        source(
            "artifacts/goal/m3-s10-cross-language/passes/beauty.png",
            "media/01-unreal-scene.png",
            "real_unreal_scene",
        ),
        source(
            f"{provider_root}/{local.artifacts[0].sha256}.png",
            "media/02-local-comfy-candidate.png",
            "local_comfy_candidate",
        ),
        source(
            f"{provider_root}/{codex.artifact.sha256}.png",
            "media/03-codex-image-candidate.png",
            "codex_image_candidate",
        ),
        source(
            f"{provider_root}/{negative.artifact.sha256}.png",
            "media/04-attractive-invalid-control.png",
            "attractive_invalid_control",
        ),
        source(
            "artifacts/goal/m4-s3-bounded-revision/composites/97b697f3a8bfa8bf3c489ed12866d9330942fe495287c0fc088d62eef73d72e3.png",
            "media/05-verified-bounded-revision.png",
            "verified_bounded_revision",
        ),
        source(
            "artifacts/goal/m6-s1-unreal-return/unreal-return-visible.png",
            "media/06-unreal-return.png",
            "real_unreal_return",
        ),
        source(
            "artifacts/goal/m6-s2-release/delivery-panel-wide.png",
            "media/07-evidence-console-wide.png",
            "evidence_console",
        ),
        source(
            "artifacts/goal/m6-s2-release/delivery-panel-narrow.png",
            "media/08-evidence-console-narrow.png",
            "responsive_evidence_console",
        ),
        source(
            "artifacts/goal/m4-s2-negative-control/scene-lab-full.png",
            "media/09-attractive-invalid-ui.png",
            "negative_control_ui",
        ),
        source(
            "artifacts/goal/m5-s1-recovery/recovery-panel-wide.png",
            "media/10-recovery-ui.png",
            "recovery_ui",
        ),
        source(
            "artifacts/goal/m10-s3-scene-lab/case-01-image-to-3d.png",
            "media/11-case-image-to-3d.png",
            "scene_lab_case_image_to_3d",
        ),
        source(
            "artifacts/goal/m10-s3-scene-lab/case-02-pbr-return.png",
            "media/12-case-pbr-return.png",
            "scene_lab_case_pbr_return",
        ),
        source(
            "artifacts/goal/m10-s3-scene-lab/case-03-multi-domain.png",
            "media/13-case-multi-domain.png",
            "scene_lab_case_multi_domain",
        ),
        source(
            "artifacts/goal/m10-s3-scene-lab/case-04-targeted-correction.png",
            "media/14-case-targeted-correction.png",
            "scene_lab_case_targeted_correction",
        ),
        source(
            "artifacts/goal/m10-s3-scene-lab/narrow-cases.png",
            "media/15-scene-lab-narrow.png",
            "responsive_scene_lab",
        ),
        source(
            "docs/assets/showcase/m13-scene-lab-rain.png",
            "media/16-m13-rain-cross-pipeline.png",
            "current_scene_lab_case",
        ),
        source(
            "docs/assets/showcase/m13-scene-lab-sunlit-correction.png",
            "media/17-m13-sunlit-correction.png",
            "current_scene_lab_case",
        ),
        source(
            "artifacts/goal/m13-s2-sunlit-overgrown/ui-narrow-sunlit-correction.png",
            "media/18-m13-sunlit-correction-narrow.png",
            "responsive_scene_lab",
        ),
    ]
    delivery = state.verified_delivery
    summary = {
        "schema_id": "artflow-portfolio-summary/2",
        "product": "ArtFlow Agent",
        "run_id": RUN_ID,
        "event_count": state.last_sequence,
        "event_head_sha256": events[-1].event_hash,
        "scene_package_id": state.scene.package.package_id if state.scene else None,
        "scene_package_sha256": state.scene.archive_sha256 if state.scene else None,
        "provider_candidates": {
            "local_comfy_sha256": local.artifacts[0].sha256,
            "codex_image_sha256": codex.artifact.sha256,
            "attractive_invalid_sha256": negative.artifact.sha256,
        },
        "selected_candidate_id": state.adoption_decision.selected_candidate_id,
        "verified_revision_sha256": state.bounded_revision_result.composite_artifact_sha256,
        "verified_delivery_sha256": delivery.delivery_sha256,
        "metrics": {
            "harness": "20/20 frozen cases",
            "recovery": "6/6 cases; 0 duplicate side effects",
            "memory": "6/6 governance cases",
            "provenance": "9/9 file bindings; unsigned sidecar",
            "pbr": "5/5 channels; 2 invalid attempts rejected",
            "scene_delta": "4 domains; 12 PCG instances; 0 protected incursions",
            "correction": "lighting only; 0 external resubmissions",
            "mcp": "3 resources; 4 tools; 4 hostile inputs rejected",
            "image_to_3d": "1 GLB; 4,817 UE triangles; 1 material; 1 collision",
            "m13_cross_pipeline": "2 routes; ComfyUI PBR and GPT Image 2 visual target",
            "m13_correction": "lighting only; 4/4 successful-domain evidence hashes preserved",
            "m13_unreal_reconcile": "12 PCG instances; 0 repeated external submissions; source unchanged",
        },
        "privacy": {
            "prompts_included": False,
            "event_database_included": False,
            "credentials_included": False,
            "hidden_reasoning_included": False,
        },
    }
    verify_doc = """# 独立验证\n\n无需启动 Unreal、ComfyUI 或 Web UI。使用 Python 3.11+：\n\n```powershell\npython tools/verify_release.py <发布包.zip>\n```\n\n验证器重新打开原 ZIP，检查清单与每个文件哈希，并复核二维闭环、PBR、四域 Scene Delta、灯光单域纠正、MCP 边界和图生 3D 接纳证据。M13 的两条当前生产案例同时以计划、评价、UE 回执和截图进入同一内容清单。退出码 0 表示通过，任何已声明内容被修改都会返回非零。\n"""
    target, manifest = build_release_archive(
        output_root=OUTPUT_ROOT,
        release_id=f"artflow-agent-{delivery.delivery_sha256[:20]}",
        run_id=RUN_ID,
        event_count=state.last_sequence,
        sources=sources,
        generated_files={
            "evidence/portfolio-summary.json": canonical_json_bytes(summary),
            "VERIFY.md": verify_doc.encode("utf-8"),
        },
        identities={
            "event_head_sha256": events[-1].event_hash,
            "harness_scorecard_sha256": state.harness_scorecard.scorecard_sha256,
            "verified_delivery_sha256": delivery.delivery_sha256,
            "provenance_manifest_sha256": delivery.provenance_manifest_sha256,
        },
        metrics={
            "harness_task_pass_rate": "20/20 frozen cases",
            "recovery_success": "6/6 frozen cases",
            "duplicate_side_effects": "0/5 side-effect cases",
            "memory_governance": "6/6 frozen cases",
            "provenance_bindings": "9/9 local files",
            "pbr_channels": "5/5 verified channels",
            "multi_domain_scene_delta": "4/4 reconciled domains",
            "pcg_protected_incursions": "0/12 instances",
            "correction_rerun_scope": "1/4 domains (lighting only)",
            "mcp_hostile_inputs": "4/4 rejected",
            "image_to_3d_triangle_negative_control": "1/1 rejected",
            "fixture_external_cost": "$0/20 Harness cases",
            "m13_production_routes": "2/2 frozen real-host cases",
            "m13_preserved_success_domains": "4/4 content hashes unchanged",
            "m13_repeated_external_submissions": "0",
        },
        limitations=[
            "The C2PA-compatible JSON sidecar is unsigned; no cryptographic C2PA credential is claimed.",
            "Frozen Harness latency is local fixture latency, not provider production latency.",
            "The release omits prompts, the SQLite event database, credentials and hidden reasoning.",
            "The TripoSR candidate is experimental geometry with vertex color, not a final production PBR asset.",
            "The M13 candidates remain isolated Unreal candidate levels and are not presented as published source-level changes.",
        ],
    )
    print(
        f"RELEASE={target} MANIFEST={manifest.manifest_sha256} "
        f"FILES={len(manifest.files)}"
    )


if __name__ == "__main__":
    main()
