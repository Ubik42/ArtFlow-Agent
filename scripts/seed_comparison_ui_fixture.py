from __future__ import annotations

import argparse
from datetime import UTC, datetime
from pathlib import Path

from artflow_agent.agent_runtime import AgentEventStore
from artflow_agent.comparison import (
    ComparisonAuthorizationDecision,
    ComparisonChildPlan,
    ComparisonChildResult,
    ComparisonOperatorPreview,
    ProviderComparisonManifest,
    ProviderComparisonPlan,
)
from artflow_agent.contracts import (
    ProviderExecutionReceipt,
    ReceiptArtifact,
    SceneConstraintPackage,
)
from artflow_agent.scene_packages import ScenePackagePreview, VerifiedSceneArtifact

ROOT = Path(__file__).resolve().parents[1]


def scene_preview() -> ScenePackagePreview:
    package = SceneConstraintPackage.model_validate_json(
        (ROOT / "examples" / "scene-constraint-package.example.json").read_text(
            encoding="utf-8"
        )
    )
    return ScenePackagePreview(
        package=package,
        archive_sha256="a" * 64,
        artifacts=[
            VerifiedSceneArtifact(
                path=item.artifact.path,
                sha256=item.artifact.sha256,
                size_bytes=1,
            )
            for item in package.passes
        ],
    )


def comparison_plan(run_id: str, scene: ScenePackagePreview) -> ProviderComparisonPlan:
    return ProviderComparisonPlan(
        comparison_id=run_id,
        dossier_id=f"{run_id}-dossier",
        dossier_sha256="d" * 64,
        scene_package_id=scene.package.package_id,
        scene_package_sha256=scene.archive_sha256,
        art_intent_sha256="b" * 64,
        children=[
            ComparisonChildPlan(
                role="local",
                action_id="local-comfy-generation",
                run_id=f"{run_id}-local",
                execution_id=f"{run_id}-local-execution",
                idempotency_key=f"comparison:{run_id}:local",
                provider_id="comfy-local",
                model_id="flux-2-klein-base-4b-fp8",
                route_decision_id=f"{run_id}-local-route",
                route_fingerprint="1" * 64,
                attestation_environment_sha256="2" * 64,
                authority_kind="local_gpu",
            ),
            ComparisonChildPlan(
                role="hosted",
                action_id="hosted-openai-edit",
                run_id=f"{run_id}-hosted",
                execution_id=f"{run_id}-hosted-execution",
                idempotency_key=f"comparison:{run_id}:hosted",
                provider_id="openai-images",
                model_id="gpt-image-2-2026-04-21",
                route_decision_id=f"{run_id}-hosted-route",
                route_fingerprint="3" * 64,
                attestation_environment_sha256="4" * 64,
                authority_kind="hosted_privacy_cost",
            ),
        ],
        operator_preview=ComparisonOperatorPreview(
            local_uploads=["beauty"],
            hosted_uploads=["beauty"],
            hosted_endpoint="/v1/images/edits",
            hosted_model="gpt-image-2-2026-04-21",
            output_count_per_provider=1,
            output_size="1280x720",
            estimated_hosted_cost_usd=0.10,
            maximum_hosted_cost_usd=0.25,
            hosted_privacy_class="provider_retained",
            cost_cap_provider_enforced=False,
            unresolved_real_host_facts=[
                "Recorded UI fixture: no real provider request was made.",
                "Real Unreal capture and review-asset return remain unauthorized.",
            ],
        ),
    )


def authorization(plan: ProviderComparisonPlan) -> ComparisonAuthorizationDecision:
    return ComparisonAuthorizationDecision(
        dossier_id=plan.dossier_id,
        dossier_sha256=plan.dossier_sha256,
        comparison_binding_sha256=plan.approval_binding(),
        resolution="approved",
        approved_by="recorded-fixture-owner",
        approved_at=datetime.now(UTC),
        authorized_action_ids=[child.action_id for child in plan.children],
    )


def succeeded_child(child: ComparisonChildPlan) -> ComparisonChildResult:
    now = datetime.now(UTC)
    request_id = f"recorded-{child.role}-request"
    receipt = ProviderExecutionReceipt(
        execution_id=child.execution_id,
        route_decision_id=child.route_decision_id,
        route_fingerprint=child.route_fingerprint,
        provider_id=child.provider_id,
        model_id=child.model_id,
        status="succeeded",
        started_at=now,
        completed_at=now,
        provider_request_id=request_id,
        artifacts=[
            ReceiptArtifact(
                path=f"recorded/{child.role}/result.png",
                sha256=("5" if child.role == "local" else "6") * 64,
                media_type="image/png",
            )
        ],
    )
    return ComparisonChildResult(
        role=child.role,
        run_id=child.run_id,
        execution_id=child.execution_id,
        provider_id=child.provider_id,
        model_id=child.model_id,
        status="succeeded",
        receipt=receipt,
    )


def seed(database: Path) -> None:
    if database.exists():
        raise FileExistsError(f"Refusing to replace existing fixture database: {database}")
    store = AgentEventStore(database)
    scene = scene_preview()
    for run_id, state in (
        ("comparison-awaiting", "awaiting"),
        ("comparison-authorized", "authorized"),
        ("comparison-succeeded", "succeeded"),
        ("comparison-recovery", "recovery"),
    ):
        plan = comparison_plan(run_id, scene)
        store.create_run(run_id)
        store.attach_scene(run_id, scene)
        store.record_comparison_plan(run_id, plan)
        if state == "awaiting":
            continue
        store.record_comparison_authorization(run_id, authorization(plan))
        if state == "authorized":
            continue
        children = [succeeded_child(plan.children[0])]
        if state == "succeeded":
            children.append(succeeded_child(plan.children[1]))
            status = "succeeded"
        else:
            hosted = plan.children[1]
            children.append(
                ComparisonChildResult(
                    role="hosted",
                    run_id=hosted.run_id,
                    execution_id=hosted.execution_id,
                    provider_id=hosted.provider_id,
                    model_id=hosted.model_id,
                    status="completion_unknown",
                )
            )
            status = "needs_human_recovery"
        store.record_comparison_manifest(
            run_id,
            ProviderComparisonManifest(
                comparison_id=run_id,
                comparison_binding_sha256=plan.approval_binding(),
                scene_package_sha256=scene.archive_sha256,
                status=status,
                children=children,
            ),
        )


def main() -> int:
    parser = argparse.ArgumentParser(description="Create recorded Scene Lab comparison states.")
    parser.add_argument("database", type=Path)
    args = parser.parse_args()
    seed(args.database.resolve())
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
