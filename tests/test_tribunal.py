import hashlib
import json
from pathlib import Path

import pytest
from PIL import Image
from pydantic import ValidationError

from artflow_agent.multimodal_critic import MultimodalTribunalReport
from artflow_agent.tribunal import (
    EvaluationDossier,
    TribunalArtifact,
    dossier_id_for,
    evaluate_dossier,
)


def _image(path: Path, color: tuple[int, int, int], *, size: tuple[int, int] = (160, 90)) -> str:
    Image.new("RGB", size, color=color).save(path)
    return hashlib.sha256(path.read_bytes()).hexdigest()


def test_tribunal_keeps_proxy_claims_separate_from_hard_eligibility(tmp_path) -> None:
    source = tmp_path / "source.png"
    local = tmp_path / "local.png"
    codex = tmp_path / "codex.png"
    source_sha = _image(source, (50, 60, 70))
    local_sha = _image(local, (50, 60, 70))
    codex_sha = _image(codex, (20, 100, 160))
    payload = {"source": source_sha, "local": local_sha, "codex": codex_sha}
    dossier = EvaluationDossier(
        dossier_id=dossier_id_for(payload),
        scene_package_id="scene-fixture",
        scene_package_sha256="1" * 64,
        beauty_sha256=source_sha,
        preserve=["camera framing"],
        prohibit=["new characters"],
        artifacts=[
            TribunalArtifact(
                role="source",
                artifact_sha256=source_sha,
                receipt_binding_sha256="1" * 64,
                width=160,
                height=90,
            ),
            TribunalArtifact(
                role="local_comfy",
                artifact_sha256=local_sha,
                receipt_binding_sha256="2" * 64,
                width=160,
                height=90,
            ),
            TribunalArtifact(
                role="codex_image",
                artifact_sha256=codex_sha,
                receipt_binding_sha256="3" * 64,
                width=160,
                height=90,
            ),
        ],
    )

    report = evaluate_dossier(
        dossier,
        {"source": source, "local_comfy": local, "codex_image": codex},
    )

    assert all(result.eligible for result in report.results)
    assert all(len(result.claims) == 3 for result in report.results)
    assert all(
        claim.hard_failure is False
        for result in report.results
        for claim in result.claims
        if claim.metric_name == "coarse_edge_layout_similarity"
    )
    assert report.adoption_status == "unselected"


def test_tribunal_hash_failure_cannot_be_overridden_by_visual_proxy(tmp_path) -> None:
    source = tmp_path / "source.png"
    local = tmp_path / "local.png"
    codex = tmp_path / "codex.png"
    source_sha = _image(source, (50, 60, 70))
    local_sha = _image(local, (50, 60, 70))
    codex_sha = _image(codex, (50, 60, 70))
    dossier = EvaluationDossier(
        dossier_id=dossier_id_for({"case": "tamper"}),
        scene_package_id="scene-fixture",
        scene_package_sha256="1" * 64,
        beauty_sha256=source_sha,
        preserve=["camera framing"],
        prohibit=["new characters"],
        artifacts=[
            TribunalArtifact(role="source", artifact_sha256=source_sha, receipt_binding_sha256="1" * 64, width=160, height=90),
            TribunalArtifact(role="local_comfy", artifact_sha256=local_sha, receipt_binding_sha256="2" * 64, width=160, height=90),
            TribunalArtifact(role="codex_image", artifact_sha256=codex_sha, receipt_binding_sha256="3" * 64, width=160, height=90),
        ],
    )
    _image(codex, (200, 20, 20))

    report = evaluate_dossier(
        dossier,
        {"source": source, "local_comfy": local, "codex_image": codex},
    )
    codex_result = next(item for item in report.results if item.candidate_role == "codex_image")

    assert codex_result.eligible is False
    assert next(
        claim for claim in codex_result.claims if claim.metric_name == "artifact_hash_match"
    ).verdict == "fail"


def test_real_multimodal_report_rejects_attractive_control_and_excludes_reasoning() -> None:
    root = Path(__file__).parents[1]
    path = (
        root
        / "artifacts"
        / "goal"
        / "m4-s2-negative-control"
        / "multimodal-tribunal-report.json"
    )
    payload = json.loads(path.read_text(encoding="utf-8"))
    report = MultimodalTribunalReport.model_validate(payload)

    assert report.negative_control_status == "rejected"
    assert report.production_adoption_status == "unselected"
    assert report.deterministic_negative_result.eligible is False
    assert report.critic.reasoning_capture == "excluded"
    assert any(
        claim.candidate_role == "negative_control"
        and claim.dimension == "aesthetic_coherence"
        and claim.verdict == "pass"
        for claim in report.critic.claims
    )

    payload["deterministic_negative_result"]["eligible"] = True
    with pytest.raises(ValidationError, match="eligibility"):
        MultimodalTribunalReport.model_validate(payload)
