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
        != "010ccbb85e578ae10dd9d5681201502eb551c83cf304c072714edf3eed439cb6"
        or intake["corrected_beauty_sha256"]
        != "6fb78beba13104136f37a8cdefc61a15d383156faa6975155ebd77eccd19673e"
        or intake["secondary_intensity_before"] != 6.0
        or intake["secondary_intensity_after"] != 0.25
    ):
        raise SystemExit("current multi-light intake no longer matches the inspected result")
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
                    "rationale": "新回渲保持源场景的相机、画幅与主体占位。",
                },
                {
                    "dimension": "protected_structure",
                    "verdict": "passed",
                    "confidence": 0.99,
                    "rationale": "灰盒轮廓、墙体与受保护空间关系没有改变。",
                },
                {
                    "dimension": "spatial_readability",
                    "verdict": "passed",
                    "confidence": 0.92,
                    "rationale": "十二个 PCG 实例仍形成清楚的前景、中景和主体节奏。",
                },
                {
                    "dimension": "lighting_direction",
                    "verdict": "passed",
                    "confidence": 0.88,
                    "rationale": "中性顶光已被压低，冷蓝低角度主光与拉长阴影形成明确的清晨方向。",
                },
                {
                    "dimension": "visual_coherence",
                    "verdict": "passed",
                    "confidence": 0.84,
                    "rationale": "低调冷光统一了地面、主体与墙面高光，同时保留可辨识的空间层次。",
                },
            ],
            "recommended_failed_domains": [],
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
                "candidate_evaluation_appended": result["scene_candidate_evaluation"]
                is not None,
            },
            ensure_ascii=False,
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
