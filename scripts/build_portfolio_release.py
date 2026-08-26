from __future__ import annotations

from pathlib import Path

from artflow_agent.agent_runtime import AgentEventStore
from artflow_agent.portfolio_release import build_release_archive, canonical_json_bytes

ROOT = Path(__file__).resolve().parents[1]
RUN_ROOT = ROOT / "artifacts/goal/m3-s11-local-run"
OUTPUT_ROOT = ROOT / "artifacts/goal/m6-s2-release"
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
        source("docs/portfolio-story.md", "docs/case-study.md", "portfolio_case_study"),
        source("docs/DEMO_GUIDE.md", "docs/demo-guide.md", "demo_guide"),
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
    ]
    delivery = state.verified_delivery
    summary = {
        "schema_id": "artflow-portfolio-summary/1",
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
        },
        "privacy": {
            "prompts_included": False,
            "event_database_included": False,
            "credentials_included": False,
            "hidden_reasoning_included": False,
        },
    }
    verify_doc = """# 独立验证\n\n无需启动 Unreal、ComfyUI 或 Web UI。解压后使用 Python 3.11+：\n\n```powershell\npython tools/verify_release.py <发布包.zip>\n```\n\n验证器重新打开原 ZIP，检查清单内容哈希、每个文件、Run/Event 身份、20/20 Harness、6/6 恢复、6/6 记忆和 9/9 unsigned provenance 边界。退出码 0 表示通过，任何内容篡改返回非零。\n"""
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
            "fixture_external_cost": "$0/20 Harness cases",
        },
        limitations=[
            "The C2PA-compatible JSON sidecar is unsigned; no cryptographic C2PA credential is claimed.",
            "Frozen Harness latency is local fixture latency, not provider production latency.",
            "The release omits prompts, the SQLite event database, credentials and hidden reasoning.",
        ],
    )
    print(
        f"RELEASE={target} MANIFEST={manifest.manifest_sha256} "
        f"FILES={len(manifest.files)}"
    )


if __name__ == "__main__":
    main()
