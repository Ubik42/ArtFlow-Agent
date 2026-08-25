from __future__ import annotations

import uuid
from datetime import UTC, datetime
from pathlib import Path

from .domain import (
    ArtBrief,
    Candidate,
    DirectionRun,
    GenerationReceipt,
    RunEvent,
    RunPlan,
    RunState,
)


class RunStateError(RuntimeError):
    """Raised for invalid or unsafe run-state transitions."""


class RunStore:
    def __init__(self, root: Path) -> None:
        self.root = root

    def create(
        self,
        brief: ArtBrief,
        plan: RunPlan,
        run_id: str | None = None,
        *,
        parent_run_id: str | None = None,
        source_candidate_id: str | None = None,
    ) -> RunState:
        resolved_id = run_id or uuid.uuid4().hex[:12]
        run_dir = self.root / resolved_id
        if run_dir.exists():
            raise RunStateError(f"Run already exists: {resolved_id}")
        run_dir.mkdir(parents=True)
        (run_dir / "receipts").mkdir()
        (run_dir / "artifacts").mkdir()
        state = RunState(
            run_id=resolved_id,
            brief=brief,
            plan=plan,
            status="awaiting_approval" if plan.approval_required else "approved",
            parent_run_id=parent_run_id,
            source_candidate_id=source_candidate_id,
        )
        self._write_state(state)
        self.append_event(
            resolved_id,
            "run_created",
            {
                "approval_required": plan.approval_required,
                "parent_run_id": parent_run_id,
                "source_candidate_id": source_candidate_id,
            },
        )
        return state

    def create_revision(
        self,
        parent_run_id: str,
        brief: ArtBrief,
        plan: RunPlan,
        run_id: str | None = None,
    ) -> RunState:
        """Create a masked-refinement run from a human-selected parent artifact."""
        parent = self.load(parent_run_id)
        if parent.status != "completed" or not parent.selected_candidate_id:
            raise RunStateError("A revision requires a completed run with a human selection")
        if brief.task_type != "masked_refinement":
            raise RunStateError("A revision brief must use task_type masked_refinement")
        if any(
            direction.recipe_id != "masked-refinement-v1" for direction in plan.directions
        ):
            raise RunStateError("A revision plan may only use the masked-refinement recipe")
        selected = next(
            (
                candidate
                for candidate in parent.candidates
                if candidate.candidate_id == parent.selected_candidate_id
            ),
            None,
        )
        parent_root = self._run_dir(parent_run_id).resolve()
        source = Path(selected.image_path).resolve() if selected is not None else None
        if source is None or not source.is_relative_to(parent_root) or not source.is_file():
            raise RunStateError("The selected parent artifact is unavailable")
        revision_brief = brief.model_copy(update={"source_image": str(source)})
        return self.create(
            revision_brief,
            plan,
            run_id,
            parent_run_id=parent_run_id,
            source_candidate_id=parent.selected_candidate_id,
        )

    def list(self) -> list[RunState]:
        if not self.root.exists():
            return []
        states: list[RunState] = []
        for path in self.root.glob("*/state.json"):
            try:
                states.append(RunState.model_validate_json(path.read_text(encoding="utf-8")))
            except (OSError, ValueError):
                continue
        return sorted(states, key=lambda state: state.created_at, reverse=True)

    def load(self, run_id: str) -> RunState:
        path = self._run_dir(run_id) / "state.json"
        try:
            return RunState.model_validate_json(path.read_text(encoding="utf-8"))
        except OSError as exc:
            raise RunStateError(f"Unknown run: {run_id}") from exc

    def approve(self, run_id: str) -> RunState:
        state = self.load(run_id)
        if state.status != "awaiting_approval":
            raise RunStateError(f"Run {run_id} cannot be approved from {state.status}")
        state.status = "approved"
        state.approved_at = datetime.now(UTC)
        self._write_state(state)
        self.append_event(run_id, "plan_approved")
        return state

    def mark_running(self, run_id: str) -> RunState:
        state = self.load(run_id)
        if state.status != "approved":
            raise RunStateError("Generation cannot start before explicit approval")
        state.status = "running"
        self._write_state(state)
        self.append_event(run_id, "generation_started")
        return state

    def save_receipt(self, run_id: str, receipt: GenerationReceipt) -> Path:
        state = self.load(run_id)
        if state.status not in {"running", "review"}:
            raise RunStateError(f"Cannot attach a receipt while run is {state.status}")
        path = self._run_dir(run_id) / "receipts" / f"{receipt.prompt_id}.json"
        _atomic_write(path, receipt.model_dump_json(indent=2))
        self.append_event(run_id, "generation_receipt_saved", {"prompt_id": receipt.prompt_id})
        return path

    def begin_direction(self, run_id: str, direction_name: str) -> RunState:
        state = self.load(run_id)
        if state.status != "running":
            raise RunStateError(f"Cannot execute a direction while run is {state.status}")
        direction = _find_direction(state, direction_name)
        if direction.status == "completed":
            raise RunStateError(f"Direction is already completed: {direction_name}")
        direction.status = "running"
        direction.attempt_count += 1
        direction.error = None
        self._write_state(state)
        self.append_event(
            run_id,
            "direction_started",
            {"direction_name": direction_name, "attempt": direction.attempt_count},
        )
        return state

    def complete_direction(
        self,
        run_id: str,
        direction_name: str,
        receipt: GenerationReceipt,
        receipt_path: Path,
        candidates: list[Candidate],
    ) -> RunState:
        state = self.load(run_id)
        direction = _find_direction(state, direction_name)
        if direction.status != "running":
            raise RunStateError(f"Direction {direction_name} is not running")
        direction.status = "completed"
        direction.prompt_id = receipt.prompt_id
        direction.receipt_path = str(receipt_path.resolve())
        direction.candidates = candidates
        self._write_state(state)
        self.append_event(
            run_id,
            "direction_completed",
            {"direction_name": direction_name, "prompt_id": receipt.prompt_id},
        )
        return state

    def fail_direction(self, run_id: str, direction_name: str, error: str) -> RunState:
        state = self.load(run_id)
        direction = _find_direction(state, direction_name)
        direction.status = "failed"
        direction.error = error
        self._write_state(state)
        self.append_event(
            run_id,
            "direction_failed",
            {"direction_name": direction_name, "error": error},
        )
        return state

    def set_candidates(self, run_id: str, candidates: list[Candidate]) -> RunState:
        state = self.load(run_id)
        if state.status != "running":
            raise RunStateError(f"Cannot add candidates while run is {state.status}")
        if not candidates:
            raise RunStateError("At least one candidate is required")
        ids = [candidate.candidate_id for candidate in candidates]
        if len(ids) != len(set(ids)):
            raise RunStateError("Candidate IDs must be unique")
        state.candidates = candidates
        state.status = "review"
        self._write_state(state)
        self.append_event(run_id, "candidates_ready", {"candidate_ids": ids})
        return state

    def select(self, run_id: str, candidate_id: str) -> RunState:
        state = self.load(run_id)
        if state.status != "review":
            raise RunStateError(f"Cannot select a candidate while run is {state.status}")
        if candidate_id not in {item.candidate_id for item in state.candidates}:
            raise RunStateError(f"Unknown candidate for this run: {candidate_id}")
        state.selected_candidate_id = candidate_id
        state.status = "completed"
        self._write_state(state)
        self.append_event(run_id, "candidate_selected", {"candidate_id": candidate_id})
        return state

    def append_event(
        self, run_id: str, event_type: str, data: dict[str, object] | None = None
    ) -> None:
        event = RunEvent(event_type=event_type, data=data or {})
        path = self._run_dir(run_id) / "events.jsonl"
        with path.open("a", encoding="utf-8") as stream:
            stream.write(event.model_dump_json() + "\n")

    def events(self, run_id: str) -> list[RunEvent]:
        path = self._run_dir(run_id) / "events.jsonl"
        try:
            return [RunEvent.model_validate_json(line) for line in path.read_text().splitlines()]
        except OSError as exc:
            raise RunStateError(f"Unknown run: {run_id}") from exc

    def _run_dir(self, run_id: str) -> Path:
        if not run_id or Path(run_id).name != run_id:
            raise RunStateError("Run ID must be a single safe path segment")
        return self.root / run_id

    def _write_state(self, state: RunState) -> None:
        _atomic_write(self._run_dir(state.run_id) / "state.json", state.model_dump_json(indent=2))


def _atomic_write(path: Path, content: str) -> None:
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(content + "\n", encoding="utf-8")
    temporary.replace(path)


def _find_direction(state: RunState, direction_name: str) -> DirectionRun:
    for direction in state.direction_runs:
        if direction.direction_name == direction_name:
            return direction
    raise RunStateError(f"Unknown direction for this run: {direction_name}")
