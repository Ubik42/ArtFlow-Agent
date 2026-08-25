from __future__ import annotations

from pathlib import Path

from PIL import Image, ImageDraw, ImageOps

from .domain import Candidate, RunState, TrajectoryCheck, TrajectoryEvaluation


def create_contact_sheet(
    candidates: list[Candidate],
    output_path: Path,
    *,
    cell_size: tuple[int, int] = (480, 320),
    columns: int = 3,
) -> Path:
    if not candidates:
        raise ValueError("At least one candidate is required")
    if columns < 1:
        raise ValueError("columns must be positive")
    label_height = 44
    rows = (len(candidates) + columns - 1) // columns
    sheet = Image.new(
        "RGB", (cell_size[0] * columns, (cell_size[1] + label_height) * rows), "#111318"
    )
    draw = ImageDraw.Draw(sheet)
    for index, candidate in enumerate(candidates):
        image = Image.open(candidate.image_path).convert("RGB")
        fitted = ImageOps.contain(image, cell_size)
        column = index % columns
        row = index // columns
        x = column * cell_size[0] + (cell_size[0] - fitted.width) // 2
        y = row * (cell_size[1] + label_height) + (cell_size[1] - fitted.height) // 2
        sheet.paste(fitted, (x, y))
        label_y = row * (cell_size[1] + label_height) + cell_size[1] + 12
        draw.text(
            (column * cell_size[0] + 14, label_y),
            f"{candidate.candidate_id} · {candidate.direction_name}",
            fill="#f4f6fb",
        )
    output_path.parent.mkdir(parents=True, exist_ok=True)
    sheet.save(output_path)
    return output_path


def evaluate_trajectory(
    state: RunState, event_types: list[str], receipt_count: int
) -> TrajectoryEvaluation:
    approval_index = _first_index(event_types, "plan_approved")
    generation_index = _first_index(event_types, "generation_started")
    approval_before_generation = not state.plan.approval_required or (
        approval_index is not None
        and generation_index is not None
        and approval_index < generation_index
    )
    selected_is_candidate = (
        state.status == "completed"
        and state.selected_candidate_id is not None
        and state.selected_candidate_id in {item.candidate_id for item in state.candidates}
    )
    receipts_are_traceable = receipt_count > 0 and all(
        candidate.receipt_path for candidate in state.candidates
    )
    checks = [
        TrajectoryCheck(
            name="approval_before_generation",
            passed=approval_before_generation,
            detail="Explicit approval precedes generation"
            if approval_before_generation
            else "Approval ordering is invalid",
        ),
        TrajectoryCheck(
            name="constraints_preserved",
            passed=(
                state.plan.preserved_constraints == state.brief.preserve
                and state.plan.prohibited_changes == state.brief.avoid
            ),
            detail="Plan carries the user-owned preserve and avoid constraints",
        ),
        TrajectoryCheck(
            name="receipts_recorded",
            passed=receipts_are_traceable,
            detail=f"Found {receipt_count} receipts; every candidate references a receipt",
        ),
        TrajectoryCheck(
            name="human_selection_valid",
            passed=selected_is_candidate,
            detail="Selected candidate belongs to this run",
        ),
    ]
    return TrajectoryEvaluation(
        run_id=state.run_id,
        passed=all(check.passed for check in checks),
        checks=checks,
    )


def _first_index(values: list[str], target: str) -> int | None:
    try:
        return values.index(target)
    except ValueError:
        return None
