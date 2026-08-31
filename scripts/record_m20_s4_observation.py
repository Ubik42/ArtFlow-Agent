from __future__ import annotations

import json
import urllib.request

from artflow_agent.current_visual_critic import seal_visual_observation

RUN_ID = "unreal-artflow-ue-89ac07a74988b8dd2fca9295e141a6fd-ca79f77b487e"
ORIGIN = "http://127.0.0.1:8804"


def request_json(path: str, *, payload: dict[str, object] | None = None) -> dict:
    body = None if payload is None else json.dumps(payload).encode("utf-8")
    request = urllib.request.Request(
        ORIGIN + path,
        data=body,
        headers={"Content-Type": "application/json"} if body is not None else {},
        method="POST" if body is not None else "GET",
    )
    with urllib.request.urlopen(request, timeout=10) as response:
        return json.load(response)


def main() -> None:
    projection = request_json(f"/api/agent/runs/{RUN_ID}")
    intake = projection["scene_correction_intake"]["evaluation_input"]
    if (
        intake["input_sha256"]
        != "0fa6b34b2aa6cc7b5e806f2fe67ed685790761754b200c04740fedc6291ccbee"
        or intake["corrected_beauty_sha256"]
        != "9babc1282044ce9148915c647c80aca0ff0840c6357fc7d1d1c27272f0e2b13e"
    ):
        raise SystemExit("current correction intake no longer matches the inspected images")
    observation = seal_visual_observation(
        {
            "input_sha256": intake["input_sha256"],
            "source_beauty_sha256": intake["source_beauty_sha256"],
            "candidate_beauty_sha256": intake["corrected_beauty_sha256"],
            "claims": [
                {
                    "dimension": "camera_composition",
                    "verdict": "passed",
                    "confidence": 0.99,
                    "rationale": "纠正回渲保持源场景的相机、画幅和主体占位。",
                },
                {
                    "dimension": "protected_structure",
                    "verdict": "passed",
                    "confidence": 0.99,
                    "rationale": "受保护灰盒轮廓与原候选一致，没有结构改写。",
                },
                {
                    "dimension": "spatial_readability",
                    "verdict": "passed",
                    "confidence": 0.96,
                    "rationale": "十二个 PCG 实例仍形成可读的前景和中景节奏。",
                },
                {
                    "dimension": "lighting_direction",
                    "verdict": "failed",
                    "confidence": 0.93,
                    "rationale": "画面仍由硬质中性日照主导，冷湿清晨的空气与明暗层次不够明确。",
                },
                {
                    "dimension": "visual_coherence",
                    "verdict": "passed",
                    "confidence": 0.89,
                    "rationale": "灯光调整没有破坏灰盒、墙体和 PCG 布局之间的整体关系。",
                },
            ],
            "recommended_failed_domains": ["lighting"],
        }
    )
    result = request_json(
        f"/api/agent/runs/{RUN_ID}/scene-correction-work/visual-observation",
        payload=observation.model_dump(mode="json"),
    )
    verdict = result["scene_correction_visual_verdict"]["domain_evaluation"]
    print(
        json.dumps(
            {
                "event_count": len(result["timeline"]),
                "observation_sha256": observation.observation_sha256,
                "evaluation_sha256": verdict["evaluation_sha256"],
                "status": verdict["status"],
                "failed_domains": verdict["failed_domains"],
            },
            ensure_ascii=False,
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
