"""Semantic validator for the durable Codex goal state.

The JSON Schema documents the wire contract. This validator enforces the
cross-field invariants that make a development continuation trustworthy.
It never executes commands stored in goal-state.json.
"""

from __future__ import annotations

import argparse
import json
import re
from pathlib import Path, PurePosixPath
from typing import Any


SCHEMA = "codex-goal-state@2.0.0"
ROOT_KEYS = {
    "schemaVersion", "stateRevision", "strategyVersion", "goalId", "objective",
    "status", "currentMilestone", "milestones", "nextSlice", "manualTracks",
    "continuationPolicy", "lastCheckpoint", "currentBlocker", "evidenceCeiling",
    "constraints",
}
MILESTONE_KEYS = {"id", "title", "status", "dependsOn", "outcome", "acceptance"}
SLICE_KEYS = {
    "id", "milestone", "title", "outcome", "risk", "evidenceTarget",
    "requiresRealHosts", "allowedPaths", "nonGoals", "acceptance",
    "stopConditions", "environmentRequirements", "validationCommands",
}
SAFE_COMMAND_PREFIXES = (
    "powershell -ExecutionPolicy Bypass -File scripts/",
    "python scripts/",
    "npm --prefix apps/",
    "node apps/",
    "git diff --check",
)


def _duplicates(values: list[str]) -> list[str]:
    return sorted({value for value in values if values.count(value) > 1})


def _safe_relative(value: str) -> bool:
    normalized = value.replace("\\", "/")
    if not normalized or normalized.startswith(("/", "//")) or re.match(r"^[A-Za-z]:", normalized):
        return False
    return ".." not in PurePosixPath(normalized).parts


def validate_state(state: dict[str, Any], repo_root: Path) -> list[str]:
    errors: list[str] = []

    missing = ROOT_KEYS - set(state)
    extra = set(state) - ROOT_KEYS
    if missing:
        errors.append(f"missing root fields: {', '.join(sorted(missing))}")
    if extra:
        errors.append(f"unexpected root fields: {', '.join(sorted(extra))}")
    if state.get("schemaVersion") != SCHEMA:
        errors.append(f"unsupported schemaVersion: {state.get('schemaVersion')!r}")
    if not isinstance(state.get("stateRevision"), int) or state.get("stateRevision", 0) < 1:
        errors.append("stateRevision must be a positive integer")

    milestones = state.get("milestones")
    if not isinstance(milestones, list) or not milestones:
        errors.append("milestones must be a non-empty array")
        milestones = []
    milestone_ids = [item.get("id") for item in milestones if isinstance(item, dict)]
    duplicate_milestones = _duplicates([item for item in milestone_ids if isinstance(item, str)])
    if duplicate_milestones:
        errors.append(f"duplicate milestone ids: {', '.join(duplicate_milestones)}")
    milestone_map = {item.get("id"): item for item in milestones if isinstance(item, dict) and isinstance(item.get("id"), str)}

    for item in milestones:
        if not isinstance(item, dict):
            errors.append("each milestone must be an object")
            continue
        missing_fields = MILESTONE_KEYS - set(item)
        extra_fields = set(item) - MILESTONE_KEYS
        if missing_fields:
            errors.append(f"milestone {item.get('id')!r} missing: {', '.join(sorted(missing_fields))}")
        if extra_fields:
            errors.append(f"milestone {item.get('id')!r} has unexpected fields: {', '.join(sorted(extra_fields))}")
        dependencies = item.get("dependsOn", [])
        if not isinstance(dependencies, list):
            errors.append(f"milestone {item.get('id')!r} dependsOn must be an array")
            continue
        for dependency in dependencies:
            if dependency not in milestone_map:
                errors.append(f"milestone {item.get('id')} depends on unknown milestone {dependency}")
            elif item.get("status") == "completed" and milestone_map[dependency].get("status") != "completed":
                errors.append(f"completed milestone {item.get('id')} depends on incomplete {dependency}")

    visiting: set[str] = set()
    visited: set[str] = set()

    def visit(milestone_id: str) -> None:
        if milestone_id in visiting:
            errors.append(f"milestone dependency cycle includes {milestone_id}")
            return
        if milestone_id in visited or milestone_id not in milestone_map:
            return
        visiting.add(milestone_id)
        for dependency in milestone_map[milestone_id].get("dependsOn", []):
            if isinstance(dependency, str):
                visit(dependency)
        visiting.remove(milestone_id)
        visited.add(milestone_id)

    for milestone_id in milestone_map:
        visit(milestone_id)

    current = state.get("currentMilestone")
    active = [item for item in milestones if isinstance(item, dict) and item.get("status") == "in_progress"]
    if state.get("status") == "active":
        if len(active) != 1:
            errors.append("active goal requires exactly one in-progress milestone")
        elif active[0].get("id") != current:
            errors.append("currentMilestone must identify the in-progress milestone")
        if state.get("currentBlocker") is not None:
            errors.append("active goal cannot have currentBlocker")
    elif state.get("status") == "blocked":
        if not isinstance(state.get("currentBlocker"), dict):
            errors.append("blocked goal requires currentBlocker")
    elif state.get("status") == "complete":
        if any(item.get("status") != "completed" for item in milestones if isinstance(item, dict)):
            errors.append("complete goal cannot contain incomplete milestones")
    else:
        errors.append(f"invalid goal status: {state.get('status')!r}")

    next_slice = state.get("nextSlice")
    if not isinstance(next_slice, dict):
        errors.append("nextSlice must be an object")
        next_slice = {}
    else:
        missing_fields = SLICE_KEYS - set(next_slice)
        extra_fields = set(next_slice) - SLICE_KEYS
        if missing_fields:
            errors.append(f"nextSlice missing: {', '.join(sorted(missing_fields))}")
        if extra_fields:
            errors.append(f"nextSlice has unexpected fields: {', '.join(sorted(extra_fields))}")
    if next_slice.get("milestone") != current:
        errors.append("nextSlice.milestone must equal currentMilestone")
    if isinstance(next_slice.get("id"), str) and not next_slice["id"].startswith(f"{current}-S"):
        errors.append("nextSlice.id must belong to currentMilestone")
    for path in next_slice.get("allowedPaths", []):
        if not isinstance(path, str) or not _safe_relative(path):
            errors.append(f"unsafe allowed path: {path!r}")
    commands = next_slice.get("validationCommands", [])
    if not isinstance(commands, list) or not commands:
        errors.append("nextSlice.validationCommands must be non-empty")
    else:
        for command in commands:
            if not isinstance(command, str) or not command.startswith(SAFE_COMMAND_PREFIXES):
                errors.append(f"validation command is outside the fixed allowlist: {command!r}")

    requirements = next_slice.get("environmentRequirements", [])
    requirement_ids = [item.get("id") for item in requirements if isinstance(item, dict)]
    if _duplicates([item for item in requirement_ids if isinstance(item, str)]):
        errors.append("environment requirement ids must be unique")
    for requirement in requirements:
        if not isinstance(requirement, dict):
            errors.append("environment requirements must be objects")
            continue
        if set(requirement) != {"id", "kind", "value", "required"}:
            errors.append(f"environment requirement {requirement.get('id')!r} has invalid fields")
        if requirement.get("kind") == "sibling_path" and not _safe_relative(str(requirement.get("value", ""))):
            errors.append(f"unsafe sibling path requirement: {requirement.get('value')!r}")

    tracks = state.get("manualTracks")
    if not isinstance(tracks, list):
        errors.append("manualTracks must be an array")
        tracks = []
    track_ids = [item.get("id") for item in tracks if isinstance(item, dict)]
    if _duplicates([item for item in track_ids if isinstance(item, str)]):
        errors.append("manual track ids must be unique")
    for track in tracks:
        if not isinstance(track, dict):
            errors.append("manual tracks must be objects")
            continue
        for evidence in track.get("evidence", []):
            if not isinstance(evidence, str) or not _safe_relative(evidence):
                errors.append(f"unsafe manual-track evidence path: {evidence!r}")
            elif not (repo_root / evidence).is_file():
                errors.append(f"manual-track evidence is missing: {evidence}")

    policy = state.get("continuationPolicy")
    if not isinstance(policy, dict):
        errors.append("continuationPolicy must be an object")
    else:
        if policy.get("maxInProgressMilestones") != 1:
            errors.append("maxInProgressMilestones must remain 1")
        if policy.get("checkpointRequiredBeforeAdvance") is not True:
            errors.append("checkpointRequiredBeforeAdvance must remain true")
        if policy.get("executeValidationCommandsDynamically") is not False:
            errors.append("goal validation commands must never execute dynamically")
        if policy.get("dirtyWorktreePolicy") != "preserve_and_report":
            errors.append("dirtyWorktreePolicy must preserve_and_report")

    checkpoint_ref = state.get("lastCheckpoint")
    if not isinstance(checkpoint_ref, str) or not _safe_relative(checkpoint_ref):
        errors.append("lastCheckpoint must be a safe relative path")
    else:
        checkpoint_path = repo_root / checkpoint_ref
        if not checkpoint_path.is_file():
            errors.append(f"lastCheckpoint is missing: {checkpoint_ref}")
        else:
            try:
                checkpoint = json.loads(checkpoint_path.read_text(encoding="utf-8"))
                if checkpoint.get("goalId") != state.get("goalId"):
                    errors.append("lastCheckpoint goalId differs from goal state")
                if checkpoint.get("status") != "completed":
                    errors.append("lastCheckpoint must describe a completed slice")
            except (OSError, json.JSONDecodeError) as exc:
                errors.append(f"lastCheckpoint cannot be read: {type(exc).__name__}")

    return errors


def load_and_validate(repo_root: Path) -> tuple[dict[str, Any], list[str]]:
    state_path = repo_root / "config" / "goal-state.json"
    try:
        state = json.loads(state_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        return {}, [f"goal state cannot be read: {type(exc).__name__}"]
    if not isinstance(state, dict):
        return {}, ["goal state root must be an object"]
    return state, validate_state(state, repo_root)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--repo-root", type=Path, default=Path(__file__).resolve().parents[1])
    args = parser.parse_args()
    repo_root = args.repo_root.resolve()
    state, errors = load_and_validate(repo_root)
    result = {
        "schema": "codex-goal-audit@1.0.0",
        "status": "failed" if errors else "passed",
        "goalId": state.get("goalId"),
        "stateRevision": state.get("stateRevision"),
        "currentMilestone": state.get("currentMilestone"),
        "nextSlice": state.get("nextSlice", {}).get("id") if isinstance(state.get("nextSlice"), dict) else None,
        "errors": errors,
    }
    print(json.dumps(result, ensure_ascii=False))
    return 1 if errors else 0


if __name__ == "__main__":
    raise SystemExit(main())
