import json
from types import SimpleNamespace

import pytest

from artflow_agent.routed_publish_facts import load_routed_publish_facts
from artflow_agent.scene_disposition import canonical_sha256


def test_native_facts_are_bound_to_candidate_bytes_and_content(tmp_path):
    decision = SimpleNamespace(candidate_scene='/Game/ArtFlow/Sessions/AF_123456789abc/Candidates/Cloth',
                               candidate_level_sha256='a' * 64, source_level_sha256='b' * 64)
    folder = tmp_path / 'integrations/unreal/ArtFlowBridgeHost/Saved/ArtFlowSceneBridge/RoutedCandidateFacts'
    folder.mkdir(parents=True)
    path = folder / (decision.candidate_level_sha256 + '.json')
    facts = dict(schema_id='artflow-routed-publish-facts/1', candidate_scene=decision.candidate_scene,
                 candidate_level_sha256=decision.candidate_level_sha256,
                 source_level_sha256=decision.source_level_sha256, source_save_count=0,
                 generated_instance_count=18)
    facts['facts_sha256'] = canonical_sha256(facts)
    path.write_text(json.dumps(facts), encoding='utf-8')
    assert load_routed_publish_facts(tmp_path, decision)['generated_instance_count'] == 18
    facts['generated_instance_count'] = 12
    path.write_text(json.dumps(facts), encoding='utf-8')
    with pytest.raises(ValueError, match='fingerprint'):
        load_routed_publish_facts(tmp_path, decision)
    facts.pop('facts_sha256')
    facts['source_level_sha256'] = 'c' * 64
    facts['facts_sha256'] = canonical_sha256(facts)
    path.write_text(json.dumps(facts), encoding='utf-8')
    with pytest.raises(ValueError, match='adopted scene'):
        load_routed_publish_facts(tmp_path, decision)
