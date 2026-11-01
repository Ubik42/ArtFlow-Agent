"""Load native observations bound to the exact adopted candidate bytes."""
import json
from pathlib import Path

from .scene_disposition import canonical_sha256


def load_routed_publish_facts(project_root: Path, decision) -> dict:
    path = (project_root / "integrations/unreal/ArtFlowBridgeHost/Saved/ArtFlowSceneBridge"
            / "RoutedCandidateFacts" / (decision.candidate_level_sha256 + ".json"))
    if not path.is_file():
        raise ValueError("Inspect the exact routed candidate in Unreal before publication")
    facts = json.loads(path.read_text(encoding="utf-8"))
    digest = facts.pop("facts_sha256", None)
    if digest != canonical_sha256(facts):
        raise ValueError("Routed candidate facts fingerprint changed")
    if (facts.get("schema_id") != "artflow-routed-publish-facts/1"
            or facts.get("candidate_scene") != decision.candidate_scene
            or facts.get("candidate_level_sha256") != decision.candidate_level_sha256
            or facts.get("source_level_sha256") != decision.source_level_sha256
            or facts.get("source_save_count") != 0
            or type(facts.get("generated_instance_count")) is not int
            or facts["generated_instance_count"] < 0):
        raise ValueError("Routed candidate facts do not match the adopted scene")
    return facts
