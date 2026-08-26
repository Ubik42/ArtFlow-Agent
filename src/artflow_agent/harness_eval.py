from __future__ import annotations

import hashlib
import time
from pathlib import Path

from .agent_harness import (
    CapabilityError,
    ContextAssembler,
    build_offline_registry,
)
from .agent_runtime import AgentEventStore, AgentRuntimeError, ToolObservationRecord
from .harness_contracts import (
    HarnessCaseResult,
    HarnessCitation,
    HarnessMetric,
    HarnessScorecard,
)
from .production_memory import MemoryScorecard
from .recovery_contracts import RecoveryScorecard


def run_harness_suite(
    *,
    database: Path,
    run_id: str,
    recovery_scorecard_path: Path,
    memory_scorecard_path: Path,
) -> HarnessScorecard:
    store = AgentEventStore(database)
    state = store.load(run_id)
    events = store.events(run_id)
    by_type = {event.event_type: event for event in events}
    recovery_bytes = recovery_scorecard_path.read_bytes()
    memory_bytes = memory_scorecard_path.read_bytes()
    recovery = RecoveryScorecard.model_validate_json(recovery_bytes)
    memory = MemoryScorecard.model_validate_json(memory_bytes)
    recovery_hash = hashlib.sha256(recovery_bytes).hexdigest()
    memory_hash = hashlib.sha256(memory_bytes).hexdigest()
    cases = _run_native_cases(store, state, by_type)
    cases.extend(_recovery_cases(recovery, recovery_hash))
    cases.extend(_memory_cases(memory, memory_hash))
    passed = sum(case.passed for case in cases)
    total_latency = sum(case.latency_ms for case in cases)
    context_cases = [case for case in cases if case.domain == "context"]
    policy_cases = [
        case
        for case in cases
        if case.domain in {"capability", "routing", "policy"}
    ]
    false_interrupt = next(case for case in cases if case.case_id == "routing.local_false_interrupt")
    scorecard = HarnessScorecard(
        run_id=run_id,
        passed_cases=passed,
        total_cases=len(cases),
        cases=cases,
        metrics=[
            _ratio_metric("harness_task_pass_rate", passed, len(cases), "all frozen cases"),
            _ratio_metric(
                "context_case_recall",
                sum(case.passed for case in context_cases),
                len(context_cases),
                "three bounded context cases",
            ),
            _ratio_metric(
                "route_policy_accuracy",
                sum(case.passed for case in policy_cases),
                len(policy_cases),
                "capability, routing and policy fixture cases",
            ),
            _ratio_metric(
                "false_interrupt_rate",
                0 if false_interrupt.passed else 1,
                1,
                "one bounded local-route case",
            ),
            _ratio_metric(
                "duplicate_side_effect_rate",
                recovery.duplicate_side_effect_count,
                5,
                "five provider-bound recovery cases in m5-s1",
            ),
            HarnessMetric(
                metric_id="fixture_latency_total",
                value=round(total_latency, 3),
                unit="milliseconds",
                numerator=round(total_latency, 3),
                denominator=len(cases),
                provenance="local deterministic fixture wall time; not provider latency",
            ),
            HarnessMetric(
                metric_id="fixture_external_cost",
                value=0,
                unit="usd",
                numerator=0,
                denominator=len(cases),
                provenance="suite performs no provider, GPU or built-in image calls",
            ),
        ],
        source_scorecards={
            "recovery": recovery_hash,
            "memory": memory_hash,
        },
        limitations=[
            "The suite measures the hand-built Harness on named deterministic cases, not open-domain model quality.",
            "Latency is local fixture wall time and must not be presented as production provider latency.",
            "External cost is zero because the suite deliberately performs no generation or host mutation.",
            "Real Unreal, ComfyUI and GPT Image evidence is cited from the run but not re-executed by this suite.",
        ],
        scorecard_sha256="0" * 64,
    )
    return scorecard.model_copy(update={"scorecard_sha256": scorecard.expected_sha256()})


def persist_or_load_harness_scorecard(
    output_path: Path,
    **kwargs,
) -> HarnessScorecard:
    if output_path.exists():
        scorecard = HarnessScorecard.model_validate_json(output_path.read_bytes())
        if scorecard.scorecard_sha256 != scorecard.expected_sha256():
            raise ValueError("Persisted Harness scorecard hash is invalid")
        return scorecard
    scorecard = run_harness_suite(**kwargs)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    temporary = output_path.with_suffix(output_path.suffix + ".partial")
    temporary.write_text(scorecard.model_dump_json(indent=2) + "\n", encoding="utf-8")
    temporary.replace(output_path)
    return scorecard


def _run_native_cases(store, state, by_type) -> list[HarnessCaseResult]:
    if state.scene is None or state.route_decision is None:
        raise RuntimeError("Harness evaluation requires scene and route evidence")
    event_citation = lambda event_type, label: HarnessCitation(
        citation_type="event_hash", value=by_type[event_type].event_hash, label=label
    )
    observations = [
        ToolObservationRecord(
            call_id=f"eval-call-{index:02d}",
            capability_id="scene.inspect_constraints",
            output_sha256=f"{index:064x}",
            summary=f"observation-{index:02d}",
            verified=True,
        )
        for index in range(10)
    ]
    fixture_state = state.model_copy(update={"observations": observations}, deep=True)
    registry = build_offline_registry()
    assembler = ContextAssembler()
    started = time.perf_counter()
    context = assembler.assemble(
        fixture_state,
        registry,
        memory_subject_keys=[
            "scene.camera.preserve",
            "revision.correct_without_regeneration",
        ],
    )
    package = state.scene.package
    hard_facts = (
        package.art_intent.preserve
        + package.art_intent.prohibit
        + [region.region_id for region in package.regions]
    )
    observed_facts = (
        context.dynamic.preserve
        + context.dynamic.prohibit
        + context.dynamic.protected_regions
        + context.dynamic.editable_regions
    )
    cases = [
        _case(
            "context.buried_constraint_recall",
            "all hard scene facts retained",
            f"{sum(fact in observed_facts for fact in hard_facts)}/{len(hard_facts)} facts",
            all(fact in observed_facts for fact in hard_facts),
            started,
            "context",
            [event_citation("scene_attached", "verified Scene Package")],
        )
    ]
    started = time.perf_counter()
    recent = context.dynamic.recent_observations
    cases.append(
        _case(
            "context.stale_observation_exclusion",
            "latest 8 observations only",
            f"first={recent[0]};count={len(recent)}",
            len(recent) == 8 and recent[0] == "observation-02" and "observation-00" not in recent,
            started,
            "context",
            [HarnessCitation(citation_type="contract", value="artflow-agent-context/1", label="bounded recent observation window")],
        )
    )
    started = time.perf_counter()
    memory_subjects = {item.subject_key for item in context.dynamic.memory_citations}
    cases.append(
        _case(
            "context.unrelated_memory_exclusion",
            "two requested production memories; episodic recovery excluded",
            ",".join(sorted(memory_subjects)),
            memory_subjects
            == {"scene.camera.preserve", "revision.correct_without_regeneration"},
            started,
            "context",
            [event_citation("memory_scorecard_recorded", "governed memory state")],
        )
    )
    started = time.perf_counter()
    unavailable_rejected = False
    try:
        registry.prepare("provider.execute.unavailable", {})
    except CapabilityError:
        unavailable_rejected = True
    cases.append(
        _case(
            "capability.unavailable_fail_closed",
            "unknown capability rejected before execution",
            "rejected" if unavailable_rejected else "accepted",
            unavailable_rejected,
            started,
            "capability",
            [HarnessCitation(citation_type="contract", value="CapabilityRegistry.prepare", label="typed capability allowlist")],
        )
    )
    route = state.route_decision
    started = time.perf_counter()
    route_ok = (
        route.selected.execution_kind == "local"
        and route.selected.privacy_class == "local_only"
        and route.max_cost_usd == 0
    )
    cases.append(
        _case(
            "routing.privacy_cost_ceiling",
            "local_only route at USD 0 ceiling",
            f"{route.selected.privacy_class};usd={route.max_cost_usd}",
            route_ok,
            started,
            "routing",
            [event_citation("route_proposed", "persisted deterministic route")],
        )
    )
    started = time.perf_counter()
    false_interrupt_ok = not route.requires_explicit_approval and not any(
        event.event_type == "approval_requested" for event in store.events(state.run_id)
    )
    cases.append(
        _case(
            "routing.local_false_interrupt",
            "bounded local route creates no approval interrupt",
            "no_interrupt" if false_interrupt_ok else "interrupt_created",
            false_interrupt_ok,
            started,
            "routing",
            [event_citation("route_proposed", "autonomous local route event")],
        )
    )
    started = time.perf_counter()
    bypass_rejected = False
    try:
        store.assert_route_authorized(
            state.run_id, route.model_copy(update={"max_cost_usd": route.max_cost_usd + 1})
        )
    except AgentRuntimeError:
        bypass_rejected = True
    cases.append(
        _case(
            "policy.approval_fingerprint_bypass",
            "mutated route fingerprint rejected",
            "rejected" if bypass_rejected else "accepted",
            bypass_rejected,
            started,
            "policy",
            [event_citation("route_proposed", "authorized route fingerprint")],
        )
    )
    started = time.perf_counter()
    tribunal = state.multimodal_tribunal
    hard_gate_ok = bool(
        tribunal
        and tribunal.negative_control_status == "rejected"
        and tribunal.disagreements
        and tribunal.disagreements[0].resolution == "hard_gate_precedence"
    )
    cases.append(
        _case(
            "policy.deterministic_hard_gate_precedence",
            "aesthetic pass cannot override deterministic failure",
            "hard_gate_precedence" if hard_gate_ok else "missing",
            hard_gate_ok,
            started,
            "policy",
            [event_citation("multimodal_tribunal_recorded", "persisted evaluator disagreement")],
        )
    )
    return cases


def _recovery_cases(scorecard, scorecard_hash):
    citation = HarnessCitation(citation_type="scorecard_sha256", value=scorecard_hash, label=scorecard.matrix_version)
    return [
        HarnessCaseResult(
            case_id=f"recovery.{item.case_id}",
            domain="recovery",
            passed=item.passed,
            expected="no duplicate provider or terminal side effect",
            observed=f"outcome={item.recovery_outcome};duplicates={item.duplicate_side_effect_count}",
            latency_ms=item.recovery_latency_ms,
            citations=[citation],
        )
        for item in scorecard.cases
    ]


def _memory_cases(scorecard, scorecard_hash):
    citation = HarnessCitation(citation_type="scorecard_sha256", value=scorecard_hash, label=scorecard.suite_version)
    return [
        HarnessCaseResult(
            case_id=f"memory.{item.case_id}",
            domain="memory",
            passed=item.passed,
            expected=item.expected,
            observed=item.observed,
            latency_ms=item.latency_ms,
            citations=[citation],
        )
        for item in scorecard.cases
    ]


def _case(case_id, expected, observed, passed, started, domain, citations):
    return HarnessCaseResult(
        case_id=case_id,
        domain=domain,
        passed=passed,
        expected=expected,
        observed=observed,
        latency_ms=round((time.perf_counter() - started) * 1000, 3),
        citations=citations,
    )


def _ratio_metric(metric_id, numerator, denominator, provenance):
    return HarnessMetric(
        metric_id=metric_id,
        value=numerator / denominator,
        unit="ratio",
        numerator=numerator,
        denominator=denominator,
        provenance=provenance,
    )
