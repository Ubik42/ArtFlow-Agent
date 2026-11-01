"""Bind native publish/review receipts to the existing M61 event database."""
import argparse
import hashlib
import json
from pathlib import Path

from fastapi.testclient import TestClient
from artflow_agent.web_api import create_app

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / 'artifacts/goal/m61-s1-routed-dcc-publish'
RUN = 'unreal-artflow-ue-89ac07a74988b8dd2fca9295e141a6fd-ca79f77b487e'
BASE = f'/api/agent/runs/{RUN}'


def save(name, value):
    (OUT / name).write_text(json.dumps(value, ensure_ascii=False, indent=2), encoding='utf-8')


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('action', choices=['publish', 'review'])
    args = parser.parse_args()
    client = TestClient(create_app(runs_dir=OUT, agent_database=OUT/'agent-events.sqlite3',
                                  project_root=ROOT), client=('127.0.0.1', 56161))
    names = ['publish-created.json', 'publish-reconciled.json'] if args.action == 'publish' else ['review-inspected.json', 'review-reconciled.json']
    for name in names:
        receipt = json.loads((OUT/name).read_text(encoding='utf-8'))
        response = client.post(f'{BASE}/current-variant/{args.action}-receipt', json=receipt)
        response.raise_for_status()
    if args.action == 'publish':
        response = client.get(f'{BASE}/current-variant/review-request')
        response.raise_for_status()
        save('review-request.json', response.json())
    else:
        response = client.get(BASE)
        response.raise_for_status()
        projection = response.json()
        lineage = projection['scene_variant_lineage']
        assert lineage['lineage_kind'] == 'routed_dcc'
        assert lineage['route_id'] == 'cloth_banner'
        assert lineage['review_status'] == 'reconciled'
        assert lineage['duplicate_side_effect_count'] == 0
        content = ROOT/'integrations/unreal/ArtFlowBridgeHost/Content'
        published = content/(lineage['published_scene'].removeprefix('/Game/')+'.umap')
        assert hashlib.sha256(published.read_bytes()).hexdigest() == lineage['published_level_sha256']
        source_hash = hashlib.sha256((content/'ArtFlowDemo.umap').read_bytes()).hexdigest()
        request = json.loads((OUT/'publish-request-candidate-bound.json').read_text(encoding='utf-8'))
        assert source_hash == request['decision']['source_level_sha256']
        save('live-projection.json', projection)
        save('verification.json', dict(status='verified', run_id=RUN, lineage=lineage,
             source_level_sha256=source_hash, observed_instance_count=lineage['generated_instance_count'],
             original_request_instance_count=12, native_candidate_inspection=True,
             host_mode='UE 5.8 commandlet; scene state and saved assets, no new visual recording'))
    print(f'{args.action}: native receipts accepted by current-session API')


if __name__ == '__main__':
    main()
