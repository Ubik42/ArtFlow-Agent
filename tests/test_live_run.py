import json
from pathlib import Path

import pytest
from pydantic import ValidationError

from artflow_agent.live_run import LiveRunAuthorizationDossier


def _path() -> Path:
    return (
        Path(__file__).parents[1]
        / "artifacts"
        / "goal"
        / "m3-s6-live-run-authorization.json"
    )


def test_live_run_dossier_is_unexecuted_bounded_and_secret_free() -> None:
    dossier = LiveRunAuthorizationDossier.load(_path())

    assert dossier.authorization_state == "awaiting_user"
    assert dossier.scene_evidence_level == "fixture"
    assert dossier.credential_status == "not_inspected"
    assert dossier.allowed_hosted_passes == ["beauty"]
    assert all(not action.authorized for action in dossier.actions)
    serialized = _path().read_text(encoding="utf-8")
    assert "sk-" not in serialized
    assert "depth.exr" not in serialized
    assert dossier.recovery.ambiguous_completion_policy == "do_not_retry_escalate"


def test_dossier_cannot_self_authorize_or_upload_auxiliary_passes() -> None:
    payload = json.loads(_path().read_text(encoding="utf-8"))
    payload["actions"][0]["authorized"] = True
    with pytest.raises(ValidationError):
        LiveRunAuthorizationDossier.model_validate(payload)

    payload = json.loads(_path().read_text(encoding="utf-8"))
    payload["allowed_hosted_passes"] = ["beauty", "depth"]
    with pytest.raises(ValidationError):
        LiveRunAuthorizationDossier.model_validate(payload)
