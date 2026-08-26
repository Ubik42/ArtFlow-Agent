from __future__ import annotations

import copy
import json
import sys
import tempfile
import unittest
from pathlib import Path


SCRIPTS = Path(__file__).resolve().parents[1]
REPO_ROOT = SCRIPTS.parent
sys.path.insert(0, str(SCRIPTS))

from validate_goal_state import validate_state  # noqa: E402


class GoalStateValidatorTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.state = json.loads((REPO_ROOT / "config" / "goal-state.json").read_text(encoding="utf-8"))

    def test_current_state_is_valid(self) -> None:
        self.assertEqual(validate_state(copy.deepcopy(self.state), REPO_ROOT), [])

    def test_dependency_cycle_is_rejected(self) -> None:
        state = copy.deepcopy(self.state)
        state["milestones"][0]["dependsOn"] = [state["milestones"][1]["id"]]
        errors = validate_state(state, REPO_ROOT)
        self.assertTrue(any("cycle" in error for error in errors))

    def test_path_traversal_is_rejected(self) -> None:
        state = copy.deepcopy(self.state)
        state["nextSlice"]["allowedPaths"] = ["../outside/**"]
        errors = validate_state(state, REPO_ROOT)
        self.assertTrue(any("unsafe allowed path" in error for error in errors))

    def test_dynamic_validation_command_is_rejected(self) -> None:
        state = copy.deepcopy(self.state)
        state["nextSlice"]["validationCommands"] = ["powershell -Command Invoke-Expression payload"]
        errors = validate_state(state, REPO_ROOT)
        self.assertTrue(any("fixed allowlist" in error for error in errors))

    def test_blocked_state_requires_blocker(self) -> None:
        state = copy.deepcopy(self.state)
        state["status"] = "blocked"
        errors = validate_state(state, REPO_ROOT)
        self.assertTrue(any("requires currentBlocker" in error for error in errors))

    def test_checkpoint_identity_is_checked(self) -> None:
        state = copy.deepcopy(self.state)
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "artifacts" / "goal").mkdir(parents=True)
            checkpoint = {"goalId": "another-goal", "status": "completed"}
            path = root / state["lastCheckpoint"]
            path.write_text(json.dumps(checkpoint), encoding="utf-8")
            errors = validate_state(state, root)
        self.assertTrue(any("goalId differs" in error for error in errors))


if __name__ == "__main__":
    unittest.main()
