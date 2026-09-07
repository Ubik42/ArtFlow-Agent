import {
  Activity,
  Aperture,
  ArrowRight,
  ArrowUpRight,
  BadgeCheck,
  Box,
  BrainCircuit,
  Check,
  ChevronRight,
  CircleAlert,
  Cloud,
  Copy,
  Cpu,
  Database,
  Eye,
  Fingerprint,
  Gauge,
  HardDrive,
  Layers3,
  LockKeyhole,
  Play,
  RefreshCw,
  Route,
  ScanLine,
  ShieldCheck,
  Sparkles,
  Upload,
  Workflow,
  Zap,
} from "lucide-react";
import {
  Fragment,
  type ChangeEvent,
  useCallback,
  useEffect,
  useRef,
  useState,
} from "react";

type AgentRunSummary = {
  run_id: string;
  stage: string;
  scene_package_id: string | null;
  last_sequence: number;
  occurred_at: string;
  pending_decision_count: number;
};
type ComparisonChild = {
  role: "local" | "hosted";
  action_id: string;
  run_id: string;
  execution_id: string;
  idempotency_key: string;
  provider_id: string;
  model_id: string;
  route_decision_id: string;
  route_fingerprint: string;
  attestation_environment_sha256: string;
  authority_kind: "bounded_local_compute" | "hosted_privacy_cost";
};
type ComparisonPlan = {
  schema_id: "provider-comparison-plan/1";
  comparison_id: string;
  dossier_id: string;
  dossier_sha256: string;
  scene_package_id: string;
  scene_package_sha256: string;
  art_intent_sha256: string;
  children: ComparisonChild[];
  operator_preview: {
    local_uploads: string[];
    hosted_uploads: string[];
    hosted_endpoint: string;
    hosted_model: string;
    output_count_per_provider: number;
    output_size: string;
    estimated_hosted_cost_usd: number;
    maximum_hosted_cost_usd: number;
    hosted_privacy_class: string;
    cost_cap_provider_enforced: false;
    unresolved_real_host_facts: string[];
  };
};
type ComparisonManifest = {
  schema_id: "provider-comparison-manifest/1";
  comparison_id: string;
  comparison_binding_sha256: string;
  scene_package_sha256: string;
  status:
    "not_started" | "partial" | "succeeded" | "failed" | "needs_human_recovery";
  children: Array<{
    role: "local" | "hosted";
    run_id: string;
    execution_id: string;
    provider_id: string;
    model_id: string;
    status: string;
    receipt: null | {
      provider_request_id: string | null;
      artifacts: Array<{ path: string; sha256: string; media_type: string }>;
    };
  }>;
  human_selected_candidate_id: null;
};
type ProviderExecution = {
  execution_id: string;
  provider_id: string;
  model_id: string;
  status:
    | "reserved"
    | "submitted"
    | "completion_unknown"
    | "succeeded"
    | "failed"
    | "cancelled";
  provider_request_id: string | null;
  unknown_reason: string | null;
  receipt: null | {
    provider_request_id: string | null;
    artifacts: Array<{ path: string; sha256: string; media_type: string }>;
  };
};
type CodexImageCandidate = {
  request: {
    scene_package_sha256: string;
    beauty_sha256: string;
    prompt_sha256: string;
    sent_input_kinds: ["beauty"];
    withheld_input_kinds: string[];
  };
  receipt: {
    candidate_id: string;
    tool_id: "codex-builtin-imagegen";
    requested_model_family: "gpt-image-2";
    observed_model_id: null;
    request_binding_sha256: string;
    artifact: { path: string; sha256: string; media_type: "image/png" };
    width: number;
    height: number;
    upstream_request_id: null;
    adoption_status: "unselected";
  };
};
type TribunalClaim = {
  claim_id: string;
  evaluator_id: "integrity_guard" | "composition_guard";
  candidate_role: "local_comfy" | "codex_image" | "negative_control";
  claim: string;
  method: string;
  metric_name: string;
  observed: number;
  threshold: number;
  comparator: "eq" | "lte" | "gte";
  verdict: "pass" | "fail";
  hard_failure: boolean;
  limitation: string;
};
type TribunalReport = {
  dossier_sha256: string;
  evaluator_versions: Record<string, string>;
  results: Array<{
    candidate_role: "local_comfy" | "codex_image";
    artifact_sha256: string;
    eligible: boolean;
    claims: TribunalClaim[];
  }>;
  adoption_status: "unselected";
};
type NegativeControl = {
  request: { intended_violations: string[]; prompt_sha256: string };
  receipt: {
    control_id: string;
    purpose: "attractive_invalid_control";
    request_binding_sha256: string;
    artifact: { path: string; sha256: string; media_type: "image/png" };
    width: number;
    height: number;
  };
};
type CriticClaim = {
  claim_id: string;
  candidate_role: "local_comfy" | "codex_image" | "negative_control";
  dimension: string;
  verdict: "pass" | "fail" | "uncertain";
  confidence: number;
  observation: string;
  limitation: string;
};
type MultimodalTribunal = {
  report_id: string;
  base_tribunal_sha256: string;
  negative_control: NegativeControl;
  deterministic_negative_result: {
    candidate_role: "negative_control";
    artifact_sha256: string;
    eligible: false;
    claims: TribunalClaim[];
  };
  critic: {
    critic_id: string;
    rubric_sha256: string;
    claims: CriticClaim[];
    reasoning_capture: "excluded";
  };
  disagreements: Array<{
    subject: string;
    deterministic_verdict: "fail";
    critic_verdict: "pass";
    resolution: "hard_gate_precedence";
  }>;
  negative_control_status: "rejected";
  production_adoption_status: "unselected";
};
type AdoptionDecision = {
  decision_id: string;
  selected_role: "local_comfy" | "codex_image";
  selected_candidate_id: string;
  artifact_sha256: string;
  status: "adopted";
  decided_by: "codex-orchestrator";
  selection_policy: string;
  evidence: {
    base_tribunal_sha256: string;
    multimodal_tribunal_sha256: string;
    deterministic_eligible: true;
    aesthetic_verdict: "pass" | "uncertain";
    aesthetic_confidence: number;
  };
  decision_basis: string[];
  dissent_retained: string[];
  reasoning_capture: "excluded";
};
type BoundedRevisionRequest = {
  revision_id: string;
  parent_artifact_sha256: string;
  prompt_sha256: string;
  editable_region: string;
  protected_regions: string[];
  mask: {
    mask_id: string;
    artifact_path: string;
    artifact_sha256: string;
    editable_pixels: number;
    coverage_ratio: number;
    compiler_id: string;
    limitation: string;
  };
};
type BoundedRevisionResult = {
  revision_id: string;
  composite_artifact_path: string;
  composite_artifact_sha256: string;
  compositor_id: "hard-mask-v1" | "feathered-inside-mask-v2";
  attempt: number;
  width: number;
  height: number;
  status: "verified";
  leakage: {
    verifier_id: string;
    outside_pixel_count: number;
    outside_changed_pixels: 0;
    inside_pixel_count: number;
    inside_changed_pixels: number;
    inside_change_ratio: number;
    hard_pass: true;
    limitation: string;
  };
  receipt: {
    tool_id: "codex-builtin-imagegen";
    raw_artifact_sha256: string;
    request_binding_sha256: string;
  };
};
type RecoveryCase = {
  case_id: string;
  passed: boolean;
  recovery_outcome: string;
  provider_side_effect_count: number;
  adoption_side_effect_count: number;
  revision_side_effect_count: number;
  terminal_event_count: number;
  duplicate_side_effect_count: number;
  recovery_latency_ms: number;
  trace_path: string | null;
  final_event_sequence: number;
  evidence_event_hashes: string[];
  limitation: string | null;
};
type RecoveryScorecard = {
  schema_id: "artflow-recovery-scorecard/1";
  matrix_version: string;
  generated_at: string;
  passed_cases: number;
  total_cases: number;
  duplicate_side_effect_count: number;
  recovery_latency_ms_total: number;
  cases: RecoveryCase[];
  limitations: string[];
};
type MemoryRecord = {
  proposal: {
    memory_id: string;
    kind: "episodic" | "semantic" | "procedural";
    project_id: string;
    subject_key: string;
    value: string;
    tags: string[];
    version: number;
    source_event_hashes: string[];
    target_scope: "project" | "shared";
    content_sha256: string;
  };
  status: "proposed" | "active" | "rejected" | "superseded";
  policy_decision: null | {
    decision_id: string;
    verdict: "activate" | "reject";
    reason_codes: string[];
    policy_id: string;
  };
  superseded_by_memory_id: string | null;
};
type MemoryScorecard = {
  schema_id: "artflow-memory-scorecard/1";
  suite_version: string;
  passed_cases: number;
  total_cases: number;
  retrieval_precision: number;
  conflict_rejection_rate: number;
  total_latency_ms: number;
  cases: Array<{
    case_id: string;
    passed: boolean;
    expected: string;
    observed: string;
    latency_ms: number;
    evidence_memory_ids: string[];
  }>;
  limitations: string[];
};
type HarnessScorecard = {
  schema_id: "artflow-harness-scorecard/1";
  suite_version: string;
  run_id: string;
  passed_cases: number;
  total_cases: number;
  cases: Array<{
    case_id: string;
    domain:
      "context" | "capability" | "routing" | "policy" | "recovery" | "memory";
    passed: boolean;
    expected: string;
    observed: string;
    latency_ms: number;
    fixture_cost_usd: number;
    citations: Array<{
      citation_type: string;
      value: string;
      label: string;
    }>;
  }>;
  metrics: Array<{
    metric_id: string;
    value: number;
    unit: "ratio" | "count" | "milliseconds" | "usd";
    numerator: number;
    denominator: number;
    provenance: string;
  }>;
  source_scorecards: Record<string, string>;
  limitations: string[];
  scorecard_sha256: string;
};
type VerifiedDelivery = {
  schema_id: "artflow-verified-delivery/1";
  run_id: string;
  return_receipt: {
    import_id: string;
    request_sha256: string;
    status: "imported";
    source_sha256: string;
    imported_asset_path: string;
    bound_scene_path: string;
    binding_actor_label: string;
    engine_version: string;
    metadata: Record<string, string>;
    completed_at: string;
    receipt_sha256: string;
  };
  provenance_manifest_sha256: string;
  verification_report_sha256: string;
  visible_evidence_sha256: string;
  status: "verified_with_declared_c2pa_limitation";
  delivery_sha256: string;
};
type AgentProjection = {
  schema_id: "agent-run-projection/1";
  run_id: string;
  status: {
    stage: string;
    scene_package_id: string | null;
    approval: string;
    pending_decision_count: number;
    pending_tool_call_count: number;
    failure_count: number;
    budgets: {
      max_iterations: number;
      used_iterations: number;
      max_tool_calls: number;
      used_tool_calls: number;
    };
    artifact_ids: string[];
  };
  scene: null | {
    package_id: string;
    source_application: string;
    source_application_version: string;
    source_scene: string;
    archive_sha256: string;
    artifact_count: number;
    evidence_class: "real_unreal_capture" | "verified_scene_archive";
    art_goal: string;
    preserve: string[];
    prohibit: string[];
    protected_regions: string[];
    editable_regions: string[];
    pass_kinds: string[];
    camera_resolution: [number, number];
  };
  pending_decisions: Array<{
    decision_id: string;
    kind: "route_approval" | "comparison_authorization";
    summary: string;
    fingerprint: string | null;
  }>;
  timeline: Array<{
    sequence: number;
    event_id: string;
    event_type: string;
    occurred_at: string;
    label: string;
    detail: string;
    tone: "neutral" | "active" | "success" | "warning" | "danger";
  }>;
  capabilities: Array<{
    capability_id: string;
    risk: string;
    availability: string;
    authority: {
      reads: string[];
      writes: string[];
      external_side_effects: boolean;
    };
    verification_signal: string;
  }>;
  route: null | {
    decision_id: string;
    fingerprint: string;
    provider_id: string;
    model_id: string;
    execution_kind: string;
    privacy_class: string;
    cost_class: string;
    privacy_ceiling: string;
    max_cost_usd: number;
    required_controls: string[];
    rejected_alternatives: Array<{
      provider_id: string;
      model_id: string;
      reasons: string[];
    }>;
  };
  capability_attestations: Array<{
    attestation_id: string;
    status: "supported" | "unsupported" | "unknown";
    environment_sha256: string;
    comfyui_version: string | null;
    device_name: string | null;
    vram_mb: number | null;
    observed_node_count: number;
    observed_model_count: number;
    verified_nodes: string[];
    verified_models: string[];
    missing_nodes: string[];
    missing_models: string[];
  }>;
  provider_executions: ProviderExecution[];
  codex_image_candidates: CodexImageCandidate[];
  tribunal_report: TribunalReport | null;
  negative_controls: NegativeControl[];
  multimodal_tribunal: MultimodalTribunal | null;
  adoption_decision: AdoptionDecision | null;
  bounded_revision_request: BoundedRevisionRequest | null;
  bounded_revision_result: BoundedRevisionResult | null;
  bounded_revision_attempts: BoundedRevisionResult[];
  recovery_scorecard: RecoveryScorecard | null;
  memory_records: MemoryRecord[];
  memory_scorecard: MemoryScorecard | null;
  harness_scorecard: HarnessScorecard | null;
  verified_delivery: VerifiedDelivery | null;
  comparison_plan: ComparisonPlan | null;
  comparison_authorization: null | {
    approved_by: string;
    approved_at: string;
    comparison_binding_sha256: string;
    authorized_action_ids: string[];
  };
  comparison_manifest: ComparisonManifest | null;
  scene_session: SceneSession | null;
  scene_candidate_work: SceneCandidateWorkState | null;
  scene_dcc_work: SceneDccWorkState | null;
  scene_candidate_intake: CurrentCandidateEvaluationRecord | null;
  scene_candidate_visual_verdict: CurrentCandidateDomainVerdictRecord | null;
  scene_correction_work: SceneCorrectionWorkState | null;
  scene_correction_intake: CurrentCorrectionEvaluationRecord | null;
  scene_correction_visual_verdict: CurrentCandidateDomainVerdictRecord | null;
  scene_candidate_evaluation: { corrected_evaluation: CurrentCandidateDomainVerdictRecord["domain_evaluation"] } | null;
  scene_candidate_adoption: { decision: { decision_sha256: string; orchestrator: "codex"; published_scene: string } } | null;
  scene_variant_lineage: SceneVariantLineage | null;
};
type SceneDomain = "image" | "material" | "asset" | "pcg" | "lighting";
type SceneSpectrumNode = {
  domain: SceneDomain;
  label: string;
  readiness: "ready" | "guarded" | "experimental";
  action: string;
  reason: string;
  verification: string;
  depends_on: SceneDomain[];
};
type SceneSessionDraft = {
  schema_id: "artflow-scene-session-draft/1";
  draft_id: string;
  draft_sha256: string;
  run_id: string;
  basis_sequence: number;
  source_scene: string;
  scene_package_sha256: string;
  capability_environment_sha256s: string[];
  intent: string;
  preserve: string[];
  prohibit: string[];
  nodes: SceneSpectrumNode[];
  ready_domain_count: number;
  guarded_domain_count: number;
  experimental_domain_count: number;
  can_stage: boolean;
  next_action: string;
};
type SceneSession = {
  schema_id: "artflow-scene-session/1";
  session_id: string;
  session_sha256: string;
  strategy_version: "scene-session-strategy/1";
  run_id: string;
  source_scene: string;
  scene_package_sha256: string;
  start_action_id: string;
  supersedes_session_id: string | null;
  draft: SceneSessionDraft;
};
type SceneStageRequest = {
  schema_id: "artflow-scene-stage-request/1";
  request_id: string;
  request_sha256: string;
  idempotency_key: string;
  run_id: string;
  basis_sequence: number;
  session_id: string;
  session_sha256: string;
  draft_sha256: string;
  scene_package_sha256: string;
  strategy_version: "scene-session-strategy/1";
  source_scene: string;
  candidate_destination: string;
  operations: Array<{
    domain: SceneDomain;
    readiness: "ready" | "experimental";
    action: string;
    verification: string;
    depends_on: SceneDomain[];
  }>;
};
type SceneCandidateWorkState = {
  definition: {
    schema_id: "artflow-scene-candidate-work/1";
    work_id: string;
    work_sha256: string;
    run_id: string;
    session_sha256: string;
    stage_request: SceneStageRequest;
    candidate_plan: {
      plan_id: string;
      plan_sha256: string;
      operations: Array<{ kind: string; operation_id: string }>;
    };
  };
  status: "queued" | "claimed" | "executing" | "reconciling" | "succeeded" | "failed";
  worker_id: string | null;
  outcome_sha256: string | null;
  message: string | null;
};
type SceneDccWorkState = {
  definition: {
    schema_id: "artflow-scene-dcc-work/1";
    work_id: string;
    work_sha256: string;
    capability_ids: string[];
    modeling_request_sha256: string;
    pbr_request_sha256: string;
    candidate_scene_path: string;
    conditioning_request_sha256?: string;
    conditioning_receipt_sha256?: string;
    accepted_visual_target_sha256?: string;
    lookdev_request_sha256?: string;
    lookdev_receipt_sha256?: string;
    unreal_lookdev_return_receipt_sha256?: string;
    surface_request_sha256?: string;
    surface_receipt_sha256?: string;
    unreal_surface_return_receipt_sha256?: string;
    set_dressing_request_sha256?: string;
    set_dressing_receipt_sha256?: string;
    set_dressing_manifest_sha256?: string;
    unreal_set_dressing_return_receipt_sha256?: string;
    surface_detail_request_sha256?: string;
    comfy_surface_detail_receipt_sha256?: string;
    blender_surface_detail_receipt_sha256?: string;
    unreal_surface_detail_return_receipt_sha256?: string;
    procedural_kit_request_sha256?: string;
    procedural_kit_receipt_sha256?: string;
    procedural_kit_manifest_sha256?: string;
    unreal_procedural_kit_return_receipt_sha256?: string;
    pcg_density_request_sha256?: string;
    pcg_density_receipt_sha256?: string;
    pcg_density_spatial_manifest_sha256?: string;
    unreal_native_pcg_density_receipt_sha256?: string;
    native_pcg_graph_path?: string;
    shot_package_request_sha256?: string;
    unreal_shot_package_receipt_sha256?: string;
    level_sequence_path?: string;
    camera_move_request_sha256?: string;
    blender_camera_move_receipt_sha256?: string;
    unreal_camera_move_receipt_sha256?: string;
    camera_move_sequence_path?: string;
    material_variation_request_sha256?: string;
    blender_material_variation_receipt_sha256?: string;
    unreal_material_variation_receipt_sha256?: string;
    simulation_cache_request_sha256?: string;
    blender_simulation_cache_receipt_sha256?: string;
    unreal_simulation_cache_receipt_sha256?: string;
    foliage_kit_request_sha256?: string;
    blender_foliage_kit_receipt_sha256?: string;
    unreal_foliage_kit_receipt_sha256?: string;
    modular_environment_request_sha256?: string;
    comfy_module_zone_receipt_sha256?: string;
    blender_modular_environment_receipt_sha256?: string;
    unreal_modular_environment_receipt_sha256?: string;
    spline_infrastructure_request_sha256?: string;
    comfy_route_corridor_receipt_sha256?: string;
    blender_spline_infrastructure_receipt_sha256?: string;
    unreal_spline_infrastructure_receipt_sha256?: string;
  };
  status: "queued" | "claimed" | "executing" | "reconciling" | "succeeded" | "failed";
  worker_id: string | null;
  outcome_sha256: string | null;
  message: string | null;
};
type CurrentCandidateEvaluationRecord = {
  evaluation_input: {
    input_sha256: string;
    candidate_scene: string;
    generated_instance_count: number;
    maximum_generated_instances: number;
    candidate_width: number;
    candidate_height: number;
  };
  technical_evaluation: {
    evaluation_id: string;
    evaluation_sha256: string;
    status: "eligible_for_visual_review" | "rejected";
    failed_domains: SceneDomain[];
    checks: Array<{
      check_id: string;
      domain: SceneDomain;
      status: "passed" | "failed";
      reason: string;
    }>;
  };
};
type CurrentCandidateDomainVerdictRecord = {
  technical_intake_sha256: string;
  visual_observation: {
    observation_id: string;
    observation_sha256: string;
    claims: Array<{
      dimension: string;
      verdict: "passed" | "failed" | "uncertain";
      confidence: number;
      rationale: string;
    }>;
  };
  domain_evaluation: {
    evaluation_id: string;
    evaluation_sha256: string;
    status: "accepted" | "correction_required";
    failed_domains: SceneDomain[];
    findings: Array<{
      domain: SceneDomain;
      status: "passed" | "failed";
      reason: string;
    }>;
  };
};
type SceneCorrectionWorkState = {
  definition: {
    work_id: string;
    work_sha256: string;
    session_sha256: string;
    correction_plan: {
      correction_sha256: string;
      failed_domains: SceneDomain[];
      rerun_domains: SceneDomain[];
      preserved_evidence_sha256s: Partial<Record<SceneDomain, string>>;
      lighting_intensity: number;
      lighting_temperature_kelvin: number;
      key_light_pitch_degrees?: number;
      key_light_yaw_degrees?: number;
      secondary_light_intensity?: number;
      secondary_light_temperature_kelvin?: number;
    };
  };
  status: "queued" | "claimed" | "executing" | "reconciling" | "succeeded" | "failed";
  worker_id: string | null;
  outcome_sha256: string | null;
  message: string | null;
};
type CurrentCorrectionEvaluationRecord = {
  evaluation_input: {
    input_sha256: string;
    corrected_beauty_sha256: string;
    generated_instance_count_before: number;
    generated_instance_count_after: number;
    intensity_before: number;
    intensity_after: number;
    temperature_before: number;
    temperature_after: number;
    key_light_pitch_before?: number;
    key_light_pitch_after?: number;
    key_light_yaw_before?: number;
    key_light_yaw_after?: number;
    secondary_intensity_before?: number;
    secondary_intensity_after?: number;
    secondary_temperature_before?: number;
    secondary_temperature_after?: number;
  };
  technical_evaluation: {
    evaluation_id: string;
    evaluation_sha256: string;
    status: "eligible_for_visual_review" | "rejected";
    failed_domains: SceneDomain[];
    checks: Array<{
      check_id: string;
      domain: SceneDomain;
      status: "passed" | "failed";
      reason: string;
    }>;
  };
};
type SceneVariantLineage = {
  schema_id: "artflow-scene-variant-lineage/1";
  case_id: "sunlit-overgrown" | "current-session";
  status: "published";
  source_scene: string;
  candidate_scene: string;
  published_scene: string;
  content_identity_sha256: string;
  published_level_sha256: string;
  correction_domain: SceneDomain;
  retained_domains: SceneDomain[];
  generated_instance_count: number;
  duplicate_side_effect_count: 0;
  source_level_unchanged: true;
  review_status: "inspected" | "reconciled";
  review_id: string;
  steps: Array<{
    index: number;
    kind: "target" | "candidate" | "correction" | "adoption" | "publish" | "review";
    label: string;
    state: "retained" | "failed" | "corrected" | "adopted" | "published" | "inspected";
    detail: string;
    identity: string;
  }>;
};
type LegacyRun = {
  run_id: string;
  status:
    | "awaiting_approval"
    | "approved"
    | "running"
    | "review"
    | "completed"
    | "failed";
  selected_candidate_id: string | null;
  brief: {
    project_name: string;
    task_type: string;
    intent: string;
    preserve: string[];
    avoid: string[];
  };
  plan: {
    directions: Array<{
      name: string;
      visual_goal: string;
      prompt_delta: string;
      recipe_id: string;
    }>;
  };
  direction_runs: Array<{ direction_name: string; status: string }>;
  candidates: Array<{ candidate_id: string; direction_name: string }>;
};
type Health = {
  reachable: boolean;
  vram_mb: number | null;
  node_count: number;
};
type Selection = { kind: "agent" | "legacy"; id: string };

async function request<T>(url: string, init?: RequestInit): Promise<T> {
  const response = await fetch(url, init);
  if (!response.ok) {
    const payload = await response
      .json()
      .catch(() => ({ detail: response.statusText }));
    throw new Error(payload.detail ?? "请求失败");
  }
  return response.json();
}
const UI_TRANSLATIONS: Record<string, string> = {
  local_only: "仅本地",
  available: "可用",
  unavailable: "不可用",
  integrity_guard: "完整性检查",
  composition_guard: "构图检查",
  artifact_hash_match: "制品哈希匹配",
  aspect_ratio_drift: "画幅比例漂移",
  coarse_edge_layout_similarity: "粗粒度边缘布局相似度",
  protected_geometry_redesign: "重做受保护几何",
  sphere_relocation: "球体位置变化",
  camera_framing_change: "相机构图变化",
  ground_plane_composition_change: "地面构图变化",
  source_constraint_compliance: "来源约束符合度",
  protected_geometry_preservation: "受保护几何保持度",
  camera_composition_preservation: "相机构图保持度",
};
const pretty = (value: string) =>
  UI_TRANSLATIONS[value.toLowerCase()] ?? value.replaceAll("_", " ");
const evidenceText = (value: string) =>
  ({
    "Authenticates bytes and binding only; it does not judge visual quality.":
      "仅验证文件字节与身份绑定，不评价视觉质量。",
    "Detects framing-ratio drift, not camera-pose or object-geometry changes.":
      "仅检测画幅比例漂移，不能证明相机姿态或物体几何未变化。",
    "A low-resolution appearance proxy; it cannot prove semantic geometry preservation.":
      "这是低分辨率外观代理指标，不能证明语义几何得到保持。",
    "Output must exactly match the event-reduced scene package.":
      "输出必须与事件归约后的场景包完全一致。",
    "The image visibly replaces the two-object graybox arrangement with a portal complex and centered floating sphere.":
      "画面将双物体灰盒布局明显替换为传送门组合与居中的悬浮球体。",
    "The protected rectangular block silhouette is replaced by curved rings and tall asymmetric fins.":
      "受保护矩形块轮廓被弧形环与高耸不对称结构替换。",
    "The wide eye-level view becomes a portrait low-angle close shot; the sphere moves to the central upper field.":
      "宽幅平视镜头变为纵向低角度近景，球体移动到画面上方中央。",
  })[value] ?? value;
const timelineText = (value: string) =>
  ({
    "Agent run created": "Agent 运行已创建",
    "Durable event stream opened": "持久事件流已开启",
    "Scene package verified": "场景包已验证",
    "Content hashes and constraints bound": "内容哈希与场景约束已绑定",
    "Scene Session started": "场景任务已启动",
    "Intent, selected domains and scene identity entered the durable ledger": "美术意图、选定领域与场景身份已进入持久账本",
    "Local route accepted": "本地路线已接纳",
    "Bounded local compute passed policy without an approval interrupt": "有界本地计算通过策略检查，无需人工批准",
    "Runtime attested": "运行时已实测",
    "Observed capability facts were content-bound": "实测能力事实已按内容哈希绑定",
    "Execution reserved": "执行身份已预留",
    "Idempotency and the fingerprinted route were persisted before submission": "提交前已持久化幂等键与路线指纹",
    "Provider accepted request": "生成服务已接收请求",
    "The external request identity was bound to the durable ledger": "外部请求身份已绑定持久账本",
    "Provider receipt verified": "生成回执已验证",
    "Identity, route fingerprint, and artifact hashes were independently checked": "身份、路线指纹和制品哈希已独立检查",
    "Codex candidate normalized": "Codex 候选已标准化",
    "Built-in image output was source-bound, hashed and persisted without an approval interrupt": "内置生图结果已绑定来源、计算哈希并直接持久化",
    "Independent tribunal recorded": "独立评价已记录",
    "Typed integrity and composition claims were replayably aggregated without adoption": "类型化完整性与构图结论已聚合，尚未触发采用",
    "Attractive-invalid control captured": "高吸引力无效对照已捕获",
    "A real built-in image was isolated as test evidence, never a production candidate": "真实内置生图结果被隔离为测试证据，不进入生产候选",
    "Multimodal critic reconciled": "多模态评价已对账",
    "Aesthetic appeal and constraint failures were persisted with hard-gate precedence": "审美吸引力与约束失败均已持久化，硬门禁优先",
    "Production candidate adopted": "生产候选已自动采用",
    "Codex selected one eligible artifact from persisted tribunal evidence without an interrupt": "Codex 依据持久评价证据自动选中唯一合格制品",
    "Bounded revision sealed": "有界修订请求已封存",
    "Parent, prompt, editable mask and protected regions were persisted before generation": "生成前已持久化父图、意图、可编辑遮罩和保护区域",
    "Bounded revision verified": "有界修订已验证",
    "The real image edit was composited with zero changed pixels outside the mask": "真实图像修订完成合成，遮罩外变化为零像素",
    "Revision seam corrected": "修订接缝已纠正",
    "The first hard-edge composite was preserved and superseded by an inside-mask feathered result": "首个硬边结果已保留，并由遮罩内羽化结果替代",
    "Exactly-once recovery verified": "Exactly-once 恢复已验证",
    "The frozen failure matrix passed with no duplicate side effects": "冻结故障矩阵通过，重复副作用为零",
    "Production memory proposed": "生产记忆已提出",
    "A typed project memory cited durable source events before policy review": "类型化项目记忆在策略复核前引用了持久来源事件",
    "Production memory activated": "生产记忆已激活",
    "Deterministic scope, source, version and conflict checks passed": "作用域、来源、版本与冲突确定性检查通过",
    "Memory governance verified": "记忆治理已验证",
    "The frozen conflict and retrieval suite passed with exact citations": "冻结冲突与检索套件通过，引用精确可追溯",
    "Agent Harness evaluation verified": "Agent Harness 评估已验证",
    "Context, routing, policy, recovery and memory cases were aggregated with frozen denominators": "上下文、路由、策略、恢复与记忆案例已按冻结分母聚合",
    "Verified Unreal delivery recorded": "Unreal 可验证交付已记录",
    "Return receipt and provenance hash chain persisted": "回流回执与来源哈希链已持久化",
  })[value] ?? value;
const stageLabel = (value: string) =>
  ({
    execution_succeeded: "执行完成",
    route_ready: "路线就绪",
    approved: "已确认",
    review: "待复检",
    awaiting_approval: "等待外部确认",
    failed: "执行失败",
  })[value] ?? pretty(value);
const constraintLabel = (value: string) =>
  ({
    "camera framing": "相机构图",
    "protected blockout silhouette": "受保护灰盒轮廓",
    "ground-plane composition": "地面构图",
    "new characters": "新增角色",
    logos: "品牌标识",
    "protected geometry redesign": "重做受保护几何",
  })[value] ?? value;
const shortId = (value: string) =>
  value.length > 18 ? `${value.slice(0, 8)}…${value.slice(-6)}` : value;

export default function App() {
  const [agentRuns, setAgentRuns] = useState<AgentRunSummary[]>([]);
  const [legacyRuns, setLegacyRuns] = useState<LegacyRun[]>([]);
  const [selection, setSelection] = useState<Selection | null>(null);
  const [agent, setAgent] = useState<AgentProjection | null>(null);
  const [legacy, setLegacy] = useState<LegacyRun | null>(null);
  const [health, setHealth] = useState<Health | null>(null);
  const [loading, setLoading] = useState(true);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const sceneImportRef = useRef<HTMLInputElement>(null);

  const open = useCallback(async (next: Selection) => {
    setSelection(next);
    setError(null);
    if (next.kind === "agent") {
      setAgent(await request<AgentProjection>(`/api/agent/runs/${next.id}`));
      setLegacy(null);
    } else {
      setLegacy(await request<LegacyRun>(`/api/runs/${next.id}`));
      setAgent(null);
    }
  }, []);
  const refresh = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const [nextAgents, nextLegacy, nextHealth] = await Promise.all([
        request<AgentRunSummary[]>("/api/agent/runs"),
        request<LegacyRun[]>("/api/runs"),
        request<Health>("/api/health").catch(() => null),
      ]);
      setAgentRuns(nextAgents);
      setLegacyRuns(nextLegacy);
      setHealth(nextHealth);
      const available = [
        ...nextAgents.map((item): Selection => ({
          kind: "agent",
          id: item.run_id,
        })),
        ...nextLegacy.map((item): Selection => ({
          kind: "legacy",
          id: item.run_id,
        })),
      ];
      const retained =
        selection &&
        available.some(
          (item) => item.kind === selection.kind && item.id === selection.id,
        );
      const next = retained ? selection : (available[0] ?? null);
      if (next) await open(next);
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : String(reason));
    } finally {
      setLoading(false);
    }
  }, [open, selection]);
  useEffect(() => {
    void refresh();
  }, []); // The initial refresh deliberately selects the newest durable run.
  useEffect(() => {
    if (selection?.kind !== "agent" || !agent || agent.run_id !== selection.id)
      return;
    const source = new EventSource(
      `/api/agent/runs/${selection.id}/stream?after=${agent.timeline.length}`,
    );
    let refreshTimer: number | undefined;
    const update = () => {
      window.clearTimeout(refreshTimer);
      refreshTimer = window.setTimeout(
        () => void open({ kind: "agent", id: selection.id }),
        120,
      );
    };
    source.addEventListener("run.event", update);
    source.addEventListener("run_snapshot", update);
    source.addEventListener("interrupt", update);
    return () => {
      window.clearTimeout(refreshTimer);
      source.close();
    };
  }, [agent?.run_id, open, selection?.id, selection?.kind]);

  const runLegacyAction = async () => {
    if (!legacy) return;
    setBusy(true);
    setError(null);
    try {
      if (legacy.status === "awaiting_approval")
        await request(`/api/runs/${legacy.run_id}/approve`, { method: "POST" });
      else if (["approved", "running"].includes(legacy.status))
        await request(`/api/runs/${legacy.run_id}/execute`, {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: "{}",
        });
      else if (legacy.status === "review")
        await request(`/api/runs/${legacy.run_id}/contact-sheet`, {
          method: "POST",
        });
      await open({ kind: "legacy", id: legacy.run_id });
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : String(reason));
    } finally {
      setBusy(false);
    }
  };
  const importScenePackage = async (event: ChangeEvent<HTMLInputElement>) => {
    const file = event.target.files?.[0];
    event.target.value = "";
    if (!file) return;
    setBusy(true);
    setError(null);
    try {
      const next = await request<AgentProjection>(
        "/api/agent/scene-packages/import",
        {
          method: "POST",
          headers: { "Content-Type": "application/zip" },
          body: file,
        },
      );
      setAgent(next);
      setLegacy(null);
      setSelection({ kind: "agent", id: next.run_id });
      setAgentRuns(await request<AgentRunSummary[]>("/api/agent/runs"));
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : String(reason));
    } finally {
      setBusy(false);
    }
  };
  const context = agent?.scene
    ? {
        title: agent.scene.source_scene,
        subtitle: "在保持相机与受保护灰盒轮廓的前提下，探索灯光、材质与场景氛围。",
        stage: agent.status.stage,
      }
    : legacy
      ? {
          title: legacy.brief.project_name,
          subtitle: legacy.brief.intent,
          stage: legacy.status,
        }
      : {
          title: "尚未附加场景",
          subtitle:
            "导入已校验的 Scene Package，开始一条持久 Agent 运行。",
          stage: "empty",
        };
  const actionLabel =
    legacy?.status === "awaiting_approval"
      ? "记录既定方案"
      : legacy?.status === "approved" || legacy?.status === "running"
        ? "执行既定方向"
        : legacy?.status === "review"
          ? "生成候选联系表"
          : null;

  return (
    <div className="scene-lab">
      <header className="masthead">
        <div className="brand-lockup">
          <div className="brand-glyph">
            <Aperture size={19} />
          </div>
          <div>
            <strong>ARTFLOW</strong>
            <span>三维场景导演台</span>
          </div>
        </div>
        <div className="mast-context">
          <span className="context-index">01</span>
          <div>
            <small>当前场景</small>
            <strong>{context.title}</strong>
          </div>
        </div>
        <div className="runtime-cluster">
          <button
            className="scene-import-command"
            disabled={busy}
            onClick={() => sceneImportRef.current?.click()}
          >
            <Upload size={14} />
            {busy ? "正在校验…" : "导入场景包"}
          </button>
          <input
            ref={sceneImportRef}
            className="visually-hidden"
            type="file"
            accept=".zip,application/zip"
            onChange={(event) => void importScenePackage(event)}
          />
          <span
            className={`runtime-light ${health?.reachable ? "online" : ""}`}
          />
          <Cpu size={14} />
          <span>
            {health?.reachable
              ? `${Math.round((health.vram_mb ?? 0) / 1024)} GB 显存 · ${health.node_count} 个节点`
              : "生成运行时未连接"}
          </span>
          <button
            className="square-button"
            onClick={() => void refresh()}
            aria-label="刷新场景导演台"
          >
            <RefreshCw size={15} />
          </button>
        </div>
      </header>
      <aside className="session-dock">
        <div className="dock-label">
          <span>运行记录</span>
          <strong>{agentRuns.length + legacyRuns.length}</strong>
        </div>
        <div className="session-list">
          {agentRuns.map((item, index) => (
            <button
              key={item.run_id}
              className={`session-card ${selection?.kind === "agent" && selection.id === item.run_id ? "selected" : ""}`}
              onClick={() => void open({ kind: "agent", id: item.run_id })}
            >
              <span className="session-number">
                {String(index + 1).padStart(2, "0")}
              </span>
              <span className="session-copy">
                <small>持久运行 · {item.last_sequence} 个事件</small>
                <strong>{item.scene_package_id ?? "等待场景"}</strong>
                <em>{stageLabel(item.stage)}</em>
              </span>
              <ChevronRight size={15} />
            </button>
          ))}
          {legacyRuns.map((item, index) => (
            <button
              key={item.run_id}
              className={`session-card legacy ${selection?.kind === "legacy" && selection.id === item.run_id ? "selected" : ""}`}
              onClick={() => void open({ kind: "legacy", id: item.run_id })}
            >
              <span className="session-number">
                L{String(index + 1).padStart(2, "0")}
              </span>
              <span className="session-copy">
                <small>历史运行</small>
                <strong>{item.brief.project_name}</strong>
                <em>{pretty(item.status)}</em>
              </span>
              <ChevronRight size={15} />
            </button>
          ))}
        </div>
        <div className="dock-foot">
          <Database size={13} />
          <span>SQLite 持久重放</span>
          <i />
        </div>
      </aside>
      <main className="stage-space">
        <section className="scene-heading">
          <div>
            <span className="kicker">
              <ScanLine size={13} /> UE 场景生产上下文
            </span>
            <h1>{context.title}</h1>
            <p>{context.subtitle}</p>
          </div>
          <div className={`stage-badge stage-${context.stage}`}>
            <Activity size={14} />
            {stageLabel(context.stage)}
          </div>
        </section>
        {agent && <SceneChangeSpectrum agent={agent} onAgentChange={setAgent} />}
        {agent && <ScenePipelineOverview agent={agent} />}
        {loading ? (
          <LoadingStage />
        ) : error && !agent && !legacy ? (
          <ErrorStage message={error} />
        ) : agent ? (
          <AgentCanvas agent={agent} />
        ) : legacy ? (
          <LegacyCanvas run={legacy} />
        ) : (
          <EmptyStage />
        )}
      </main>
      <aside className="evidence-inspector">
        <div className="inspector-head">
          <span>场景检查器</span>
          <Fingerprint size={16} />
        </div>
        {agent ? (
          <AgentInspector agent={agent} />
        ) : legacy ? (
          <LegacyInspector run={legacy} health={health} />
        ) : (
          <div className="inspector-empty">
            <Eye size={24} />
            <p>
              选择一条持久运行，查看场景约束、工具边界和可复核结果。
            </p>
          </div>
        )}
        {error && (agent || legacy) && (
          <div className="inline-error">
            <CircleAlert size={15} />
            {error}
          </div>
        )}
      </aside>
      <footer
        className={`command-deck ${agent?.verified_delivery ? "delivery-complete" : ""}`}
      >
        <div className="command-status">
          <span className="pulse-ring">
            <i />
          </span>
          <div>
            <strong>
              {agent
                ? "场景运行已同步"
                : legacy
                  ? "历史工作流仍可读取"
                  : "Scene Lab 已就绪"}
            </strong>
            <span>
              {agent
                ? `${agent.timeline.length} 个执行事件 · ${agent.status.artifact_ids.length} 个关联制品`
                : "选择场景后开始编排。"}
            </span>
          </div>
        </div>
        {agent ? (
          <div className="budget-readout">
            <span>
              迭代{" "}
              <b>
                {agent.status.budgets.used_iterations}/
                {agent.status.budgets.max_iterations}
              </b>
            </span>
            <span>
              工具{" "}
              <b>
                {agent.status.budgets.used_tool_calls}/
                {agent.status.budgets.max_tool_calls}
              </b>
            </span>
            <span className="run-readiness">
              <ShieldCheck size={15} />
              {agent.pending_decisions.length
                ? "待处理条件已记录，不阻塞浏览"
                : "等待下一项类型化动作"}
            </span>
          </div>
        ) : actionLabel ? (
          <button
            className="primary-command"
            disabled={busy}
            onClick={() => void runLegacyAction()}
          >
            {legacy?.status === "awaiting_approval" ? (
              <ShieldCheck size={16} />
            ) : (
              <Play size={16} />
            )}
            {busy ? "正在处理…" : actionLabel}
            <ArrowUpRight size={14} />
          </button>
        ) : null}
      </footer>
    </div>
  );
}

const SCENE_DOMAIN_OPTIONS: Array<{
  domain: SceneDomain;
  label: string;
  index: string;
}> = [
  { domain: "image", label: "视觉参考", index: "01" },
  { domain: "material", label: "材质", index: "02" },
  { domain: "asset", label: "三维资产", index: "03" },
  { domain: "pcg", label: "空间布局", index: "04" },
  { domain: "lighting", label: "灯光", index: "05" },
];

function SceneChangeSpectrum({
  agent,
  onAgentChange,
}: {
  agent: AgentProjection;
  onAgentChange: (next: AgentProjection) => void;
}) {
  const persistedDraft = agent.scene_session?.draft ?? null;
  const initialIntent = persistedDraft?.intent ?? agent.scene?.art_goal ?? "";
  const initialDomains = persistedDraft
    ? persistedDraft.nodes.map((node) => node.domain)
    : SCENE_DOMAIN_OPTIONS.map((item) => item.domain);
  const [intent, setIntent] = useState(initialIntent);
  const [domains, setDomains] = useState<SceneDomain[]>(initialDomains);
  const [draft, setDraft] = useState<SceneSessionDraft | null>(persistedDraft);
  const [stageRequest, setStageRequest] = useState<SceneStageRequest | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const startActionRef = useRef<string | null>(null);

  const compileDraft = useCallback(async () => {
    if (intent.trim().length < 10 || domains.length === 0) return;
    setBusy(true);
    setError(null);
    try {
      const next = await request<SceneSessionDraft>(
        `/api/agent/runs/${agent.run_id}/scene-session/draft`,
        {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ intent: intent.trim(), domains }),
        },
      );
      setDraft(next);
      setStageRequest(null);
      startActionRef.current = null;
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : String(reason));
    } finally {
      setBusy(false);
    }
  }, [agent.run_id, domains, intent]);

  useEffect(() => {
    setIntent(initialIntent);
    setDomains(
      persistedDraft
        ? persistedDraft.nodes.map((node) => node.domain)
        : SCENE_DOMAIN_OPTIONS.map((item) => item.domain),
    );
    setDraft(persistedDraft);
    setStageRequest(null);
    startActionRef.current = null;
    setError(null);
  }, [agent.run_id, agent.scene_session?.session_sha256, initialIntent]);

  const toggleDomain = (domain: SceneDomain) => {
    setDraft(null);
    setStageRequest(null);
    startActionRef.current = null;
    setDomains((current) =>
      current.includes(domain)
        ? current.filter((item) => item !== domain)
        : SCENE_DOMAIN_OPTIONS.filter(
            (item) => item.domain === domain || current.includes(item.domain),
          ).map((item) => item.domain),
    );
  };
  const nodes = new Map(draft?.nodes.map((node) => [node.domain, node]));
  const isPersisted = Boolean(
    draft && agent.scene_session?.draft.draft_sha256 === draft.draft_sha256,
  );

  const startSession = useCallback(async () => {
    if (!draft) return;
    setBusy(true);
    setError(null);
    startActionRef.current ??= `scene-ui-${crypto.randomUUID()}`;
    try {
      const next = await request<AgentProjection>(
        `/api/agent/runs/${agent.run_id}/scene-session/start`,
        {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({
            action_id: startActionRef.current,
            expected_draft_sha256: draft.draft_sha256,
            intent: draft.intent,
            domains: draft.nodes.map((node) => node.domain),
          }),
        },
      );
      onAgentChange(next);
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : String(reason));
    } finally {
      setBusy(false);
    }
  }, [agent.run_id, draft, onAgentChange]);

  const createStageRequest = useCallback(async () => {
    if (!draft || !isPersisted) return;
    setBusy(true);
    setError(null);
    try {
      setStageRequest(
        await request<SceneStageRequest>(
          `/api/agent/runs/${agent.run_id}/scene-session/stage-request`,
          {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ expected_draft_sha256: draft.draft_sha256 }),
          },
        ),
      );
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : String(reason));
    } finally {
      setBusy(false);
    }
  }, [agent.run_id, draft, isPersisted]);

  const queueCandidateWork = useCallback(async () => {
    if (!stageRequest) return;
    setBusy(true);
    setError(null);
    try {
      const next = await request<AgentProjection>(
        `/api/agent/runs/${agent.run_id}/scene-candidate-work/queue`,
        { method: "POST" },
      );
      onAgentChange(next);
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : String(reason));
    } finally {
      setBusy(false);
    }
  }, [agent.run_id, onAgentChange, stageRequest]);

  const evaluateCandidateWork = useCallback(async () => {
    setBusy(true);
    setError(null);
    try {
      const next = await request<AgentProjection>(
        `/api/agent/runs/${agent.run_id}/scene-candidate-work/evaluate`,
        { method: "POST" },
      );
      onAgentChange(next);
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : String(reason));
    } finally {
      setBusy(false);
    }
  }, [agent.run_id, onAgentChange]);

  const queueCorrectionWork = useCallback(async () => {
    setBusy(true);
    setError(null);
    try {
      const next = await request<AgentProjection>(
        `/api/agent/runs/${agent.run_id}/scene-correction-work/queue`,
        { method: "POST" },
      );
      onAgentChange(next);
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : String(reason));
    } finally {
      setBusy(false);
    }
  }, [agent.run_id, onAgentChange]);

  const queueDccWork = useCallback(async () => {
    setBusy(true);
    setError(null);
    try {
      const next = await request<AgentProjection>(
        `/api/agent/runs/${agent.run_id}/scene-dcc-work/queue`,
        { method: "POST" },
      );
      onAgentChange(next);
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : String(reason));
    } finally {
      setBusy(false);
    }
  }, [agent.run_id, onAgentChange]);

  const startDccWork = useCallback(async () => {
    setBusy(true);
    setError(null);
    try {
      const next = await request<AgentProjection>(
        `/api/agent/runs/${agent.run_id}/scene-dcc-work/start`,
        { method: "POST" },
      );
      onAgentChange(next);
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : String(reason));
    } finally {
      setBusy(false);
    }
  }, [agent.run_id, onAgentChange]);

  const work = agent.scene_candidate_work;
  const dccWork = agent.scene_dcc_work;
  const intake = agent.scene_candidate_intake;
  const visualVerdict = agent.scene_candidate_visual_verdict;
  const correctionWork = agent.scene_correction_work;
  const correctionIntake = agent.scene_correction_intake;
  const correctionVerdict = agent.scene_correction_visual_verdict;
  const currentAdoption = agent.scene_candidate_adoption;
  const currentLineage = agent.scene_variant_lineage;
  const workLabels: Record<SceneCandidateWorkState["status"], string> = {
    queued: "等待 Unreal 领取",
    claimed: "Unreal 已领取",
    executing: "候选关卡正在生成",
    reconciling: "正在核对引擎结果",
    succeeded: "候选关卡已经就绪",
    failed: "执行停止，可按提示恢复",
  };

  return (
    <section className="scene-spectrum" aria-label="场景变更谱">
      <header className="spectrum-head">
        <div>
          <span><Aperture size={14} /> 场景变更谱</span>
          <h2>先定变化范围，再进入候选关卡</h2>
        </div>
        <button
          type="button"
          disabled={busy || intent.trim().length < 10 || domains.length === 0}
          onClick={() => void compileDraft()}
        >
          <ScanLine size={15} />
          {busy ? "正在编译…" : draft ? "重新编译" : "编译场景草案"}
        </button>
      </header>
      <div className="spectrum-intent">
        <label>
          <span>本轮美术意图</span>
          <textarea
            value={intent}
            maxLength={600}
            onChange={(event) => {
              setIntent(event.target.value);
              setDraft(null);
              setStageRequest(null);
              startActionRef.current = null;
            }}
            aria-label="本轮美术意图"
          />
        </label>
        <div className="spectrum-constraints">
          <span>保持</span>
          <strong>{agent.scene?.preserve.slice(0, 2).join(" · ") || "按场景包约束"}</strong>
          <small>{intent.trim().length} / 600 字</small>
        </div>
      </div>
      <div className="spectrum-track" role="list" aria-label="可编排场景领域">
        {SCENE_DOMAIN_OPTIONS.map((option, index) => {
          const selected = domains.includes(option.domain);
          const node = nodes.get(option.domain);
          const readiness = node?.readiness ?? "uncompiled";
          return (
            <button
              type="button"
              role="listitem"
              key={option.domain}
              className={`spectrum-node ${selected ? "selected" : ""} state-${readiness}`}
              onClick={() => toggleDomain(option.domain)}
              aria-pressed={selected}
            >
              <span className="spectrum-index">{option.index}</span>
              <i style={{ height: `${30 + index * 7}px` }} />
              <strong>{option.label}</strong>
              <small>
                {!selected
                  ? "本轮不修改"
                  : node?.readiness === "ready"
                    ? "可以进入计划"
                    : node?.readiness === "experimental"
                      ? "实验候选"
                      : node?.readiness === "guarded"
                        ? "需要补齐事实"
                        : "等待编译"}
              </small>
            </button>
          );
        })}
      </div>
      <footer className={`spectrum-result ${draft ? "visible" : ""}`}>
        {error ? (
          <span className="spectrum-error"><CircleAlert size={14} /> {error}</span>
        ) : draft ? (
          <>
            <div>
              <span>{isPersisted ? <Check size={14} /> : draft.can_stage ? <ArrowUpRight size={14} /> : <LockKeyhole size={14} />}</span>
              <strong>
                {correctionWork
                  ? currentLineage
                    ? "当前版本已发布并完成 Unreal 审阅"
                  : currentAdoption
                    ? "当前纠正候选已由 Codex 采用，等待发布"
                    : correctionVerdict?.domain_evaluation.status === "correction_required"
                      ? "单灯纠正未通过复评，只需继续修正 lighting"
                      : correctionVerdict?.domain_evaluation.status === "accepted"
                        ? "当前纠正候选已通过独立复评"
                    : correctionIntake
                      ? correctionIntake.technical_evaluation.status === "eligible_for_visual_review"
                        ? "灯光纠正已通过七项技术复检，等待视觉复评"
                        : "灯光纠正未通过技术复检"
                    : correctionWork.status === "succeeded"
                      ? "灯光纠正完成，等待同机位复评"
                    : `灯光纠正：${workLabels[correctionWork.status]}`
                  : visualVerdict
                  ? visualVerdict.domain_evaluation.status === "accepted"
                    ? "当前候选已通过技术与视觉评价"
                    : `只需修正：${visualVerdict.domain_evaluation.failed_domains.join("、")}`
                  : intake
                  ? intake.technical_evaluation.status === "eligible_for_visual_review"
                    ? "当前候选已通过六项技术审查"
                    : `技术审查拒绝：${intake.technical_evaluation.failed_domains.join("、")}`
                  : work
                  ? workLabels[work.status]
                  : stageRequest
                  ? "候选关卡请求已封存，尚未交给 Unreal 执行"
                  : isPersisted
                    ? "Scene Session 已进入持久账本"
                    : draft.next_action}
              </strong>
            </div>
            <div className="spectrum-counts">
              <span>{draft.ready_domain_count} 项可执行</span>
              <span>{draft.guarded_domain_count} 项待补齐</span>
              <span>{draft.experimental_domain_count} 项实验能力</span>
            </div>
            {dccWork ? (
              <div className={`candidate-work-pulse state-${dccWork.status}`}>
                <span />
                <b>
                  Blender DCC · {dccWork.status === "succeeded" ? "已回流" : workLabels[dccWork.status]}
                </b>
                <small>
                  {dccWork.definition.material_variation_request_sha256
                    ? "ComfyUI 场景目标 → Blender 材质 / Bake → Unreal 原生 PCG"
                    : dccWork.definition.camera_move_request_sha256
                    ? "视觉目标 → Blender 三关键帧 → Unreal Sequencer 镜头动画"
                    : dccWork.definition.shot_package_request_sha256
                    ? "视觉目标 → Blender 镜头预演 → 原生 PCG → Level Sequence"
                    : dccWork.definition.pcg_density_request_sha256
                    ? "Unreal 空间证据 → ComfyUI 密度 → Blender 套件 → 原生 PCG"
                    : dccWork.definition.procedural_kit_request_sha256
                    ? "场景目标 → Blender 程序化套件 → PCG 装配 → Unreal"
                    : dccWork.definition.surface_detail_request_sha256
                    ? "Unreal 取样 → ComfyUI → Blender 投射 / Bake → Unreal"
                    : dccWork.definition.set_dressing_request_sha256
                    ? "Surface → Blender 物理解算 → Unreal 布景"
                    : dccWork.definition.surface_request_sha256
                    ? "Lookdev → Blender UV / Bake → Unreal"
                    : dccWork.definition.lookdev_request_sha256
                    ? "ComfyUI 场景目标 → Blender Lookdev → Unreal"
                    : "ComfyUI PBR → Blender → Unreal"}
                  {" · "}{shortId(dccWork.definition.work_sha256)}
                </small>
              </div>
            ) : null}
            <code title={work?.definition.work_id ?? stageRequest?.candidate_destination}>
              {shortId(work?.definition.work_sha256 ?? stageRequest?.request_sha256 ?? draft.draft_sha256)}
            </code>
            <div className="spectrum-actions">
              {dccWork?.status === "queued" ? (
                <button type="button" disabled={busy} onClick={() => void startDccWork()}>
                  <Play size={13} /> 启动本地 DCC Worker
                </button>
              ) : null}
              {work?.status === "succeeded" && !dccWork ? (
                <button type="button" disabled={busy} onClick={() => void queueDccWork()}>
                  <Layers3 size={13} /> 派发 Blender DCC
                </button>
              ) : null}
              {work ? (
                correctionWork ? (
                  correctionVerdict?.domain_evaluation.status === "correction_required" ? (
                    <button type="button" disabled={busy} onClick={() => void queueCorrectionWork()}>
                      <ScanLine size={13} /> 封存灯光组补丁
                    </button>
                  ) : (
                    <div className={`candidate-work-pulse state-${currentLineage || currentAdoption || correctionVerdict?.domain_evaluation.status === "accepted" ? "succeeded" : correctionVerdict ? "failed" : correctionWork.status}`}>
                      <span />
                      <b>
                        {currentLineage
                          ? "Published 版本已复核"
                          : currentAdoption
                          ? "内容身份已采用"
                          : correctionVerdict?.domain_evaluation.status === "accepted"
                            ? "纠正候选复评通过"
                            : correctionIntake
                              ? "七项技术复检通过"
                              : correctionWork.status === "succeeded"
                                ? "灯光纠正回渲已就绪"
                                : `只重做 lighting · ${workLabels[correctionWork.status]}`}
                      </b>
                      <small>{currentLineage ? `Unreal · ${shortId(currentLineage.published_level_sha256)}` : currentAdoption ? `Codex · ${shortId(currentAdoption.decision.decision_sha256)}` : correctionWork.worker_id ? `写入者 ${correctionWork.worker_id}` : `保留 ${Object.keys(correctionWork.definition.correction_plan.preserved_evidence_sha256s).join("、")}`}</small>
                    </div>
                  )
                ) : visualVerdict?.domain_evaluation.status === "correction_required" ? (
                  <button type="button" disabled={busy} onClick={() => void queueCorrectionWork()}>
                    <ScanLine size={13} /> 封存灯光补丁
                  </button>
                ) : visualVerdict ? (
                  <div className={`candidate-work-pulse state-${visualVerdict.domain_evaluation.status === "accepted" ? "succeeded" : "failed"}`}>
                    <span />
                    <b>{visualVerdict.domain_evaluation.status === "accepted" ? "候选评价通过" : "视觉方向需要单域修正"}</b>
                    <small>
                      {visualVerdict.domain_evaluation.findings.filter((finding) => finding.status === "passed").length}
                      /{visualVerdict.domain_evaluation.findings.length} 域通过
                      {visualVerdict.domain_evaluation.failed_domains.length > 0
                        ? ` · ${visualVerdict.domain_evaluation.failed_domains.join("、")}`
                        : ""}
                    </small>
                  </div>
                ) : intake ? (
                  <div className={`candidate-work-pulse state-${intake.technical_evaluation.status === "eligible_for_visual_review" ? "succeeded" : "failed"}`}>
                    <span />
                    <b>{intake.technical_evaluation.status === "eligible_for_visual_review" ? "技术审查通过，等待视觉评价" : "技术审查未通过"}</b>
                    <small>{intake.technical_evaluation.checks.filter((check) => check.status === "passed").length}/6 项 · PCG {intake.evaluation_input.generated_instance_count}/{intake.evaluation_input.maximum_generated_instances}</small>
                  </div>
                ) : work.status === "succeeded" ? (
                  <button type="button" disabled={busy} onClick={() => void evaluateCandidateWork()}>
                    <ScanLine size={13} /> 校验当前候选
                  </button>
                ) : (
                  <div className={`candidate-work-pulse state-${work.status}`}>
                    <span />
                    <b>{workLabels[work.status]}</b>
                    <small>{work.worker_id ? `写入者 ${work.worker_id}` : "已锁定当前 Session 与候选计划"}</small>
                  </div>
                )
              ) : !isPersisted ? (
                <button type="button" disabled={busy} onClick={() => void startSession()}>
                  <ArrowUpRight size={13} /> 启动场景任务
                </button>
              ) : draft.can_stage && !stageRequest ? (
                <button type="button" disabled={busy} onClick={() => void createStageRequest()}>
                  <Layers3 size={13} /> 生成候选请求
                </button>
              ) : stageRequest && !work ? (
                <button type="button" disabled={busy} onClick={() => void queueCandidateWork()}>
                  <Layers3 size={13} /> 交给 Unreal 执行
                </button>
              ) : null}
            </div>
          </>
        ) : (
          <span>选择本轮会改变的领域，编译后查看执行准备度与依赖。</span>
        )}
      </footer>
    </section>
  );
}

function ScenePipelineOverview({ agent }: { agent: AgentProjection }) {
  const liveLineage = agent.scene_variant_lineage;
  const hasCurrentLifecycle = Boolean(
    agent.scene_candidate_work ||
    agent.scene_candidate_intake ||
    agent.scene_candidate_visual_verdict,
  );
  const [fallbackLineage, setFallbackLineage] = useState<SceneVariantLineage | null>(null);
  useEffect(() => {
    if (liveLineage || hasCurrentLifecycle) {
      setFallbackLineage(null);
      return;
    }
    let active = true;
    void request<SceneVariantLineage>("/api/showcase/scene-variant-lineage")
      .then((next) => {
        if (active) setFallbackLineage(next);
      })
      .catch(() => {
        if (active) setFallbackLineage(null);
      });
    return () => {
      active = false;
    };
  }, [hasCurrentLifecycle, liveLineage]);
  const lineage = liveLineage ?? fallbackLineage;
  const lineageSource = liveLineage ? "当前 Scene Session" : "作品演示数据";
  const currentVerdict = (
    agent.scene_correction_visual_verdict ?? agent.scene_candidate_visual_verdict
  )?.domain_evaluation;
  const correctionSucceeded = agent.scene_correction_work?.status === "succeeded";
  const correctionAccepted =
    agent.scene_correction_visual_verdict?.domain_evaluation.status === "accepted";
  const currentAdopted = Boolean(agent.scene_candidate_adoption);
  const currentPublished = Boolean(liveLineage);
  const correctionNeedsAnotherPass =
    agent.scene_correction_visual_verdict?.domain_evaluation.status === "correction_required";
  const currentDomains = currentVerdict
    ? currentVerdict.findings.map((finding) => {
        const label: Record<SceneDomain, string> = {
          image: "图像",
          material: "材质",
          asset: "资产",
          pcg: "PCG",
          lighting: "灯光",
        };
        if (finding.domain === "lighting" && currentPublished) {
          return "灯光·已发布";
        }
        if (finding.domain === "lighting" && currentAdopted) {
          return "灯光·已采用";
        }
        if (finding.domain === "lighting" && correctionAccepted) {
          return "灯光·复评通过";
        }
        if (correctionSucceeded && finding.domain === "lighting") {
          return "灯光·已纠正待复评";
        }
        return `${label[finding.domain]}·${finding.status === "passed" ? (correctionSucceeded ? "保留" : "通过") : "待修正"}`;
      })
    : ["图像·待评价", "PCG·已执行", "灯光·待评价"];
  const currentInput = agent.scene_candidate_intake?.evaluation_input;
  const currentCorrection = agent.scene_correction_intake?.evaluation_input;
  const hasMultiLightReceipt = currentCorrection?.secondary_intensity_after !== undefined;
  const hasSceneLookdev = Boolean(agent.scene_dcc_work?.definition.lookdev_request_sha256);
  const hasSurfaceBake = Boolean(agent.scene_dcc_work?.definition.surface_request_sha256);
  const hasSetDressing = Boolean(agent.scene_dcc_work?.definition.set_dressing_request_sha256);
  const hasSurfaceDetail = Boolean(agent.scene_dcc_work?.definition.surface_detail_request_sha256);
  const hasProceduralKit = Boolean(agent.scene_dcc_work?.definition.procedural_kit_request_sha256);
  const hasNativePcgDensity = Boolean(agent.scene_dcc_work?.definition.pcg_density_request_sha256);
  const hasShotPackage = Boolean(agent.scene_dcc_work?.definition.shot_package_request_sha256);
  const hasCameraMove = Boolean(agent.scene_dcc_work?.definition.camera_move_request_sha256);
  const hasMaterialVariation = Boolean(agent.scene_dcc_work?.definition.material_variation_request_sha256);
  const hasSimulationCache = Boolean(agent.scene_dcc_work?.definition.simulation_cache_request_sha256);
  const hasFoliageKit = Boolean(agent.scene_dcc_work?.definition.foliage_kit_request_sha256);
  const hasModularEnvironment = Boolean(agent.scene_dcc_work?.definition.modular_environment_request_sha256);
  const hasSplineInfrastructure = Boolean(agent.scene_dcc_work?.definition.spline_infrastructure_request_sha256);
  const cases = [
    ...(hasSplineInfrastructure
      ? [{
          id: "spline-infrastructure-roundtrip",
          tab: "当前 Session · 样条设施",
          title: "让二维空间走廊成为引擎里可继续编辑的管线系统",
          description: "Agent 从当前深度、保护区和模块候选中编译两条有限路线。ComfyUI 计算无泄漏走廊，Blender 以 Curve 与 Geometry Nodes 保留电缆、管线和支架，Unreal 重建真实 SplineComponent 与可见线路段。",
          frames: [
            { src: "/api/showcase/production/m49-route-corridor", alt: "ComfyUI 计算的样条路线走廊", label: "空间走廊", title: "13.3179% 覆盖 · 0 泄漏" },
            { src: "/api/showcase/production/m49-spline-blender", alt: "Blender 中可编辑的曲线与 Geometry Nodes 线路", label: "曲线加工", title: "2 条路线 · 14 个控制点" },
            { src: "/api/showcase/production/m49-spline-unreal", alt: "Unreal 中重建的样条基础设施候选", label: "引擎样条", title: "12 段线路 · 8 个支架" },
          ],
          transition: "空间条件编译为可编辑样条拓扑",
          metricA: "2 / 14",
          metricALabel: "Spline / 控制点",
          metricB: "0",
          metricBLabel: "重放新增 Actor",
          note: `样条请求 ${shortId(agent.scene_dcc_work?.definition.spline_infrastructure_request_sha256 ?? "")} 已恢复为候选 ${agent.scene_dcc_work?.definition.candidate_scene_path}；源模块候选保持字节不变。`,
          domains: ["场景·已绑定", "走廊·已生成", "曲线·可编辑", "Spline·已重建", "重放·已对账"],
        }]
      : hasModularEnvironment
      ? [{
          id: "modular-environment-roundtrip",
          tab: "当前 Session · 模块装配",
          title: "从场景空间条件生成可编辑的模块化环境骨架",
          description: "Agent 将当前深度、保护区和视觉目标编译为固定空间子图与有限模块目录。ComfyUI 产生区域场，Blender 保留三类 Geometry Nodes 模块和布局，Unreal 以稳定 Actor 身份重建，同时保留已有 PCG 植被层。",
          frames: [
            { src: "/api/showcase/production/m47-module-zones", alt: "ComfyUI 模块区域空间场", label: "空间区域", title: "24.829% 覆盖 · 0 泄漏" },
            { src: "/api/showcase/production/m47-modular-blender", alt: "Blender 三类模块与可编辑布局", label: "DCC 装配", title: "3 类模块 · 12 个位置" },
            { src: "/api/showcase/production/m47-modular-unreal", alt: "Unreal 重建的模块化环境候选", label: "引擎骨架", title: "12 个 Actor · PCG 层保留" },
          ],
          transition: "空间场编译为稳定模块身份",
          metricA: "3 / 12",
          metricALabel: "模块类 / Actor",
          metricB: "0",
          metricBLabel: "保护区泄漏",
          note: `装配请求 ${shortId(agent.scene_dcc_work?.definition.modular_environment_request_sha256 ?? "")} 已恢复为候选 ${agent.scene_dcc_work?.definition.candidate_scene_path}；重放未新增 Actor。`,
          domains: ["条件·已绑定", "区域·已生成", "模块·可编辑", "Actor·已重建", "重放·已对账"],
        }]
      : hasFoliageKit
      ? [{
          id: "biome-foliage-roundtrip",
          tab: "当前 Session · 生物群落",
          title: "把二维群落分区变成可继续制作的三维植被层",
          description: "Agent 绑定 ComfyUI 生物群落蒙版与地形候选，将有限物种和预算编译给 Blender；三种可编辑植被携带 UV、LOD 与碰撞回到 Unreal，由项目 PCG 布置并使用受限风材质。",
          frames: [
            { src: "/api/showcase/production/m45-biome-field", alt: "ComfyUI 生成的生物群落空间分区", label: "空间条件", title: "Biome Mask · 27.63% 覆盖" },
            { src: "/api/showcase/production/m45-foliage-blender", alt: "Blender 生成的三种可编辑植被", label: "DCC 植被", title: "3 物种 · UV / LOD1 / 碰撞" },
            { src: "/api/showcase/production/m45-foliage-unreal", alt: "Unreal PCG 布置的植被候选", label: "引擎环境层", title: "18 实例 · WPO 风材质" },
          ],
          transition: "群落空间场驱动的类型化资产",
          metricA: "3 / 18",
          metricALabel: "物种 / PCG 实例",
          metricB: "0",
          metricBLabel: "重复副作用",
          note: `植被请求 ${shortId(agent.scene_dcc_work?.definition.foliage_kit_request_sha256 ?? "")} 已恢复为候选 ${agent.scene_dcc_work?.definition.candidate_scene_path}；上游地形候选保持字节不变。`,
          domains: ["群落·已绑定", "几何·可编辑", "LOD·已导入", "风材质·已写入", "重放·已对账"],
        }]
      : hasSimulationCache
      ? [{
          id: "simulation-cache-roundtrip",
          tab: "当前 Session · 动画缓存",
          title: "把 Blender 形变预演交付为 Unreal 可继续编排的时序资产",
          description: "Agent 将地形候选、帧段、网格密度、形变幅度和缓存预算编译为有限任务。Blender 输出可编辑动画源与 Alembic 顶点缓存，Unreal 导入 Geometry Cache 并写入项目 Level Sequence。",
          frames: [
            { src: "/api/showcase/production/m43-simulation-source", alt: "Unreal 地形与 PCG 来源候选", label: "时序来源", title: "M42 地形候选 · 内容已绑定" },
            { src: "/api/showcase/production/m43-simulation-blender", alt: "Blender 风幕形变缓存中间帧", label: "DCC 缓存", title: "F036 / 72 · Alembic 5.98 MB" },
            { src: "/api/showcase/production/m43-simulation-unreal", alt: "Unreal Geometry Cache 与 Sequencer 候选", label: "引擎时序", title: "1 绑定 · 1 轨道 · 1 区段" },
          ],
          transition: "内容寻址的顶点动画缓存",
          metricA: "72 / 24",
          metricALabel: "缓存帧 / fps",
          metricB: "0",
          metricBLabel: "重复资产",
          note: `模拟请求 ${shortId(agent.scene_dcc_work?.definition.simulation_cache_request_sha256 ?? "")} 已恢复为候选 ${agent.scene_dcc_work?.definition.candidate_scene_path}；上游地形候选保持字节不变。`,
          domains: ["来源·已绑定", "动画·可编辑", "缓存·已导入", "序列·已写入", "重放·已对账"],
        }]
      : hasMaterialVariation
      ? [{
          id: "material-variation-roundtrip",
          tab: "当前 Session · 材质变体",
          title: "让场景视觉方向成为 PCG 模块可继续编辑的材质系统",
          description: "Agent 将当前 ComfyUI 场景目标、Wayfinder 编辑源和原生 PCG 候选编译成一项有限材质任务。Blender 保留三套节点与六张烘焙贴图，Unreal 创建 Material Instances 并按 A / B / C 模块身份分配。",
          frames: [
            { src: "/api/showcase/production/m40-material-target", alt: "ComfyUI 根据 Unreal 场景生成的视觉条件", label: "场景条件", title: "Beauty + Depth · 内容已绑定" },
            { src: "/api/showcase/production/m40-material-blender", alt: "Blender 中三套可编辑 Wayfinder 材质", label: "DCC 材质", title: "3 套节点 · 6 张 512² Bake" },
            { src: "/api/showcase/production/m40-material-unreal", alt: "Unreal 原生 PCG 应用三套 Material Instances", label: "引擎候选", title: "3 个 MI · 12 个 PCG 实例" },
          ],
          transition: "内容绑定的材质参数",
          metricA: "92–95%",
          metricALabel: "三套 UV 覆盖",
          metricB: "0",
          metricBLabel: "重复组件修改",
          note: `材质请求 ${shortId(agent.scene_dcc_work?.definition.material_variation_request_sha256 ?? "")} 从未知完成状态恢复；候选 ${agent.scene_dcc_work?.definition.candidate_scene_path} 保持上游 PCG 与源关卡字节不变。`,
          domains: ["条件·已绑定", "UV·已验证", "材质·可编辑", "PCG·已分配", "恢复·已对账"],
        }]
      : hasCameraMove
      ? [{
          id: "camera-move-roundtrip",
          tab: "当前 Session · 镜头运动",
          title: "让 Blender 镜头预演成为 Unreal 中可继续编辑的运动轨道",
          description: "Agent 从当前 Shot Package 编译三个有限相机姿态。Blender 保留动画曲线和可编辑源文件，Unreal 从原 Sequence 派生新版本并写入 Transform Track；每个阶段并列呈现 DCC 预演与引擎结果。",
          frames: [
            { src: "/api/showcase/production/m38-blender-start", secondarySrc: "/api/showcase/production/m38-unreal-start", alt: "Blender 镜头运动起始帧", secondaryAlt: "Unreal 镜头运动起始帧", label: "起始姿态 · F000", title: "Blender / Unreal" },
            { src: "/api/showcase/production/m38-blender-middle", secondarySrc: "/api/showcase/production/m38-unreal-middle", alt: "Blender 镜头运动中间帧", secondaryAlt: "Unreal 镜头运动中间帧", label: "中间姿态 · F060", title: "Blender / Unreal" },
            { src: "/api/showcase/production/m38-blender-end", secondarySrc: "/api/showcase/production/m38-unreal-end", alt: "Blender 镜头运动结束帧", secondaryAlt: "Unreal 镜头运动结束帧", label: "结束姿态 · F119", title: "Blender / Unreal" },
          ],
          transition: "同一类型化相机姿态",
          metricA: "27",
          metricALabel: "Sequencer 键值",
          metricB: "412.43 cm",
          metricBLabel: "镜头位移",
          note: `派生 Sequence ${agent.scene_dcc_work?.definition.camera_move_sequence_path ?? ""} 绑定请求 ${shortId(agent.scene_dcc_work?.definition.camera_move_request_sha256 ?? "")}；第二个引擎进程对账相同轨道，重复轨道为 0。`,
          domains: ["目标·已绑定", "动画·可编辑", "轨道·已写入", "三帧·已回渲", "重放·已对账"],
        }]
      : hasShotPackage
      ? [{
          id: "shot-ready-environment",
          tab: "当前 Session · 镜头交付",
          title: "把程序化环境直接组织成可继续制作的引擎镜头",
          description: "Agent 将视觉方向、Blender 相机与三点灯光、ComfyUI 空间密度和 Unreal 原生 PCG 绑定到同一生产任务，最终在隔离候选关卡中创建可编辑 Level Sequence，而不是停留在二维示意图。",
          frames: [
            { src: "/api/showcase/production/m36-shot-blender", alt: "Blender 中按视觉方向预演的相机与灯光", label: "DCC 预演", title: "相机 + 三点灯光 · 可编辑" },
            { src: "/api/showcase/production/m36-shot-density", alt: "ComfyUI 节点图生成的场景空间密度", label: "空间条件", title: "节点密度 · 保护区泄漏 0" },
            { src: "/api/showcase/production/m36-shot-pcg", alt: "Unreal 原生 PCG 生成的环境实例", label: "环境生成", title: "12 实例 · 原生 PCG" },
            { src: "/api/showcase/production/m36-shot-unreal", alt: "Unreal Level Sequence 中的程序化环境镜头", label: "镜头交付", title: "4 条绑定 · 120 帧" },
          ],
          transition: "类型化跨应用编排",
          metricA: "4",
          metricALabel: "Sequencer 对象绑定",
          metricB: "120",
          metricBLabel: "镜头帧范围",
          note: `Level Sequence ${agent.scene_dcc_work?.definition.level_sequence_path ?? ""} 与候选 ${shortId(agent.scene_dcc_work?.definition.shot_package_request_sha256 ?? "")} 绑定；重复派发只对账，不重复创建资产。`,
          domains: ["视觉·已绑定", "DCC·可编辑", "密度·已验证", "PCG·原生执行", "镜头·已交付"],
        }]
      : hasNativePcgDensity
      ? [{
          id: "native-pcg-density",
          tab: "当前 Session · 空间生成",
          title: "让节点式图像条件真正驱动 Unreal 原生 PCG",
          description: "Agent 从当前场景深度与保护对象编译固定空间任务。ComfyUI 负责密度和排除蒙版，Blender 提供带 UV、LOD 与碰撞的三变体套件，项目自有 PCG 图再把 12 个验证点实例化到隔离候选。",
          frames: [
            { src: "/api/showcase/production/m34-density-exclusion", alt: "由 Unreal 对象范围编译的三个保护区域", label: "场景约束", title: "Depth + 3 个保护区域" },
            { src: "/api/showcase/production/m34-density-mask", alt: "ComfyUI 固定节点图输出的可用空间密度", label: "节点密度", title: "29.197% 覆盖 · 泄漏 0" },
            { src: "/api/showcase/production/m34-density-blender", alt: "Blender 生成的三变体 Wayfinder 程序化套件", label: "DCC 套件", title: "3 变体 · UV · LOD · 碰撞" },
            { src: "/api/showcase/production/m34-density-unreal", alt: "Unreal 原生 PCG 装配后的隔离候选", label: "原生 PCG", title: "12 实例 · 3 网格 · 已对账" },
          ],
          transition: "类型化空间投影",
          metricA: "12 / 3",
          metricALabel: "实例与网格变体",
          metricB: "0",
          metricBLabel: "保护区泄漏",
          note: `空间清单 ${shortId(agent.scene_dcc_work?.definition.pcg_density_spatial_manifest_sha256 ?? "")} 与原生图 ${agent.scene_dcc_work?.definition.native_pcg_graph_path ?? ""} 绑定；重复执行副作用为 0。`,
          domains: ["场景·已绑定", "密度·已验证", "DCC·可编辑", "PCG·原生执行", "UE·已对账"],
        }]
      : hasProceduralKit
      ? [{
          id: "procedural-kit-assembly",
          tab: "当前 Session · 程序化装配",
          title: "让二维视觉方向长成一套可布置的引擎模块",
          description: "Agent 绑定当前庭院边界和已登记的 ComfyUI 视觉目标，编译三变体 Wayfinder 套件。Blender 负责 Geometry Nodes、UV、材质、LOD 与碰撞准备；类型化 PCG consumer 再把九个确定性点位写入新的 Unreal 候选。",
          frames: [
            { src: "/api/showcase/production/m32-kit-target", alt: "ComfyUI 生成并登记的青铜绿视觉目标", label: "视觉方向", title: "ComfyUI · 内容已绑定" },
            { src: "/api/showcase/production/m32-kit-bounds", alt: "用于模块布置的 Unreal 当前庭院边界", label: "场景边界", title: "当前候选 · 有限空间" },
            { src: "/api/showcase/production/m32-kit-blender", alt: "Blender 生成的三变体程序化 Wayfinder 套件", label: "DCC 套件", title: "3 变体 · UV · LOD1 · 碰撞" },
            { src: "/api/showcase/production/m32-kit-unreal", alt: "Unreal 中完成九点装配的隔离候选", label: "PCG 装配", title: "9 点位 · 3 资产 · 已对账" },
          ],
          transition: "类型化场景装配",
          metricA: "3 × 2",
          metricALabel: "资产变体与 LOD",
          metricB: "0",
          metricBLabel: "重复回流对象变更",
          note: `套件清单 ${shortId(agent.scene_dcc_work?.definition.procedural_kit_manifest_sha256 ?? "")} 与当前工作项绑定；Unreal 只接收哈希匹配资产，源关卡字节未变化。`,
          domains: ["目标·已绑定", "几何·可编辑", "材质·已装配", "LOD/碰撞·通过", "PCG·已对账"],
        }]
      : hasSurfaceDetail
      ? [{
          id: "scene-surface-detail",
          tab: "当前 Session · 表面细节",
          title: "从引擎局部意图，生成可回流的三维材质嵌件",
          description: "Agent 绑定当前机位、对象与有限区域，编译已登记的 ComfyUI 图。选定细节随后进入 Blender 投射、UV 与 Bake，最终由 Unreal return tool 装配为候选专属网格、纹理和引擎材质。",
          frames: [
            { src: "/api/showcase/production/m30-detail-source", alt: "从 Unreal 当前候选裁取的嵌件区域", label: "场景取样", title: "当前机位 · AF_Inlay" },
            { src: "/api/showcase/production/m30-detail-generated", alt: "ComfyUI 根据场景生成的青铜绿日轮嵌件", label: "节点生成", title: "FLUX.2 Klein · 一次生成" },
            { src: "/api/showcase/production/m30-detail-blender", alt: "Blender 中投射并烘焙后的三维嵌件", label: "DCC 转化", title: "8 顶点 · 12 三角形 · 可编辑" },
            { src: "/api/showcase/production/m30-detail-unreal", alt: "Unreal 中接收表面细节资产的隔离候选", label: "引擎回流", title: "网格 + 纹理 + 项目材质" },
          ],
          transition: "类型化制品链",
          metricA: "21.44%",
          metricALabel: "生成图选区覆盖",
          metricB: "0",
          metricBLabel: "重复回流对象变更",
          note: `Surface Detail ${shortId(agent.scene_dcc_work?.definition.surface_detail_request_sha256 ?? "")} 绑定同一 Session；ComfyUI 输出只生成一次，Blender 与 Unreal 后续均按内容身份对账。`,
          domains: ["场景·已绑定", "节点图·已执行", "DCC·已烘焙", "材质·已装配", "UE·已对账"],
        }]
      : hasSetDressing
      ? [{
          id: "physics-set-dressing",
          tab: "当前 Session · 物理布景",
          title: "让 Blender 求解自然落点，再把确定结果交给 Unreal",
          description: "Agent 只开放登记原型、庭院边界、种子、数量和帧预算。Blender 负责刚体求解并返回可编辑场景与变换清单；通过稳定性、边界和间距检查后，Unreal 才在新候选关卡生成实例。",
          frames: [
            { src: "/api/showcase/production/m26-surface-unreal", alt: "物理布景前的 Unreal Surface 候选", label: "Surface 输入", title: "候选关卡 · 内容已绑定" },
            { src: "/api/showcase/production/m28-dressing-blender", alt: "Blender 刚体求解后的庭院碎石布景", label: "物理解算", title: "12 个实例 · 第 96 帧稳定" },
            { src: "/api/showcase/production/m28-dressing-unreal", alt: "Unreal 应用刚体变换清单后的布景候选", label: "UE 布景候选", title: "12 项变换 · 已对账" },
          ],
          transition: "验证后变换",
          metricA: "0.000002 m",
          metricALabel: "末帧最大位移",
          metricB: "0.768 m",
          metricBLabel: "最小中心间距",
          note: `变换清单 ${shortId(agent.scene_dcc_work?.definition.set_dressing_manifest_sha256 ?? "")} 与当前工作项绑定；重复回流新增 Actor 为 0，源关卡字节未变化。`,
          domains: ["Surface·已绑定", "物理·已求解", "边界·通过", "变换·已验证", "UE·已对账"],
        }]
      : hasSurfaceBake
      ? [{
          id: "surface-bake-roundtrip",
          tab: "当前 Session · Surface Bake",
          title: "把 Lookdev 收敛为可复用的引擎表面资产",
          description: "Agent 绑定当前 Lookdev、27 个登记对象与有限 UV/Bake 参数。Blender 生成命名 UV、两张 1024 图集、单材质 GLB 和可编辑源文件；Unreal 通过 Interchange 接收新的隔离候选，重复回流只执行对账。",
          frames: [
            { src: "/api/showcase/production/m24-lookdev-blender", alt: "已经接受的 Blender Lookdev 输入", label: "Lookdev 输入", title: "场景与材质方向已绑定" },
            { src: "/api/showcase/production/m26-surface-atlas", alt: "Blender 生成的 1024 平方像素 Base Color UV 图集", label: "UV 图集", title: "ArtFlow_BakedUV · 1024²" },
            { src: "/api/showcase/production/m26-surface-blender", alt: "Blender 生成的单材质可编辑 Surface", label: "DCC 结果", title: "2,818 顶点 · 5,364 三角形" },
            { src: "/api/showcase/production/m26-surface-unreal", alt: "Unreal 导入贴图材质后的隔离候选", label: "UE 候选", title: "1 材质 · 2 纹理 · 已对账" },
          ],
          transition: "内容身份",
          metricA: "11,104",
          metricALabel: "UV loops",
          metricB: "0",
          metricBLabel: "重复回流副作用",
          note: `Surface Request ${shortId(agent.scene_dcc_work?.definition.surface_request_sha256 ?? "")} 与当前事件流绑定；最终候选 ${agent.scene_dcc_work?.definition.candidate_scene_path}，源关卡字节未变化。`,
          domains: ["Lookdev·已绑定", "UV·已展开", "贴图·已烘焙", "DCC·已回流", "UE·已对账"],
        }]
      : hasSceneLookdev
      ? [{
          id: "scene-conditioned-lookdev",
          tab: "当前 Session · 场景 Lookdev",
          title: "把二维视觉方向落实为可编辑 DCC 与引擎候选",
          description: "Agent 绑定当前场景、ComfyUI 条件图与 Unreal 镜头，只编译三组登记材质色板和 key / fill / rim 灯光。Blender 保留可编辑场景，Unreal 接收内容寻址候选；再次执行只对账已有结果。",
          frames: [
            { src: "/api/showcase/production/m24-lookdev-target", alt: "ComfyUI 根据 Unreal Beauty 与 Depth 生成的视觉目标", label: "视觉目标", title: "Beauty + Depth · FLUX.2" },
            { src: "/api/showcase/production/m24-lookdev-blender", alt: "Blender 根据视觉目标生成的可编辑 Lookdev", label: "DCC 预演", title: "3 组材质色板 · 三点布光" },
            { src: "/api/showcase/production/m24-lookdev-unreal", alt: "Unreal 接收 Blender Lookdev 后的隔离候选", label: "UE 候选", title: "3 个材质槽 · 已对账" },
          ],
          transition: "类型化参数",
          metricA: "3 + 3",
          metricALabel: "材质目标与灯光角色",
          metricB: "0",
          metricBLabel: "重复回流副作用",
          note: `当前工作项 ${shortId(agent.scene_dcc_work?.definition.work_sha256 ?? "")} 由同一事件流恢复；最终候选 ${agent.scene_dcc_work?.definition.candidate_scene_path}，源关卡字节未变化。`,
          domains: ["图像·已绑定", "材质·已编译", "灯光·已编译", "DCC·已回流"],
        }]
      : []),
    {
      id: "rain-wet-courtyard",
      tab: hasCurrentLifecycle ? "当前 Session · 雨后庭院" : "雨后庭院 · 全管线",
      title: hasCurrentLifecycle
        ? currentPublished
          ? "内容寻址版本已发布，并由 Unreal 新进程复核"
          : currentAdopted
          ? "双灯光组通过复评，当前候选已由 Codex 采用"
          : correctionAccepted
            ? "双灯光组通过技术与视觉复评"
          : correctionNeedsAnotherPass
          ? "技术复检通过，视觉复评要求继续收敛灯光组"
          : correctionSucceeded
          ? "Unreal 已完成一次灯光域定向纠正"
          : "当前 Unreal 候选正在沿失败域收敛"
        : "从灰盒场景出发，编排材质、项目资产、PCG 与灯光",
      description: hasCurrentLifecycle
        ? currentPublished
          ? `当前候选已写入 ${liveLineage?.published_scene}。发布与审阅分别由独立 UE 5.8 进程对账，重复关卡包为 0，源关卡保存为 0。`
          : currentAdopted
          ? "Agent 将第二盏定向光从 6.0 压低至 0.25，并把主光改为冷蓝低角度方向。七项硬检查与独立视觉复评均通过；Codex 依据持久评价采用精确内容身份，尚未发布。"
          : correctionAccepted
            ? "第二盏中性顶光已被压低，主光方向与色温形成冷蓝清晨层次。通过域证据保持不变，当前候选已满足采用条件。"
          : correctionNeedsAnotherPass
          ? "七项技术检查证明本次修改没有越界，但新回渲仍受第二盏 DirectionalLight 主导，冷湿清晨方向不够明确。Agent 保留 image 与 PCG，只把 lighting 送入下一次受限灯光组纠正。"
          : correctionSucceeded
          ? "独立视觉评价只判定 lighting 失败。Agent 保留图像与 PCG 证据，仅把主光从 5.5 / 4200K 改为 3.2 / 7200K，并由 Unreal 以同机位重新渲染。"
          : "源场景、候选回渲、技术审查与视觉裁决来自同一个 Scene Session。当前空间布局已经通过，雨后清晨的光照方向仍需一次有界修正。"
        : "Agent 读取 Unreal 场景包，将雨后湿润方向编译成五类受限工具调用。ComfyUI 负责 PBR 技术图，项目资产和 PCG 完成空间铺陈，所有写入只发生在隔离候选关卡。",
      frames: hasCurrentLifecycle
        ? correctionSucceeded
          ? [
            { src: `/api/agent/runs/${agent.run_id}/scene/passes/beauty`, alt: "当前 Scene Session 的 Unreal 源场景", label: "源场景", title: "相机、灰盒与保护区已锁定" },
            {
              src: `/api/agent/runs/${agent.run_id}/scene-correction-work/beauty`,
              alt: "双定向灯修正后的 Unreal 同机位回渲",
              label: currentPublished ? "Published 版本" : currentAdopted ? "已采用候选" : "灯光纠正",
              title: currentPublished ? `V_${liveLineage?.content_identity_sha256.slice(0, 12)} · 已复核` : hasMultiLightReceipt ? "主光 2.2 / 8500K · 辅光 0.25 / 9000K" : "3.2 / 7200K · PCG 12→12",
            },
          ]
          : [
            { src: `/api/agent/runs/${agent.run_id}/scene/passes/beauty`, alt: "当前 Scene Session 的 Unreal 源场景", label: "当前源场景", title: "相机、灰盒与保护区已锁定" },
            { src: `/api/agent/runs/${agent.run_id}/scene-candidate-work/beauty`, alt: "当前 Scene Session 的 Unreal 候选回渲", label: "当前候选", title: currentVerdict?.status === "correction_required" ? "PCG 通过 · 灯光待修正" : "当前候选回渲" },
          ]
        : [
            { src: "/api/showcase/production/m13-rain-source", alt: "Unreal 灰盒源场景", label: "源场景", title: "相机、灰盒与保护区已锁定" },
            { src: "/api/showcase/production/m13-rain-candidate", alt: "雨后湿润庭院 Unreal 候选", label: "UE 候选", title: "PBR · 项目资产 · PCG · 灯光" },
          ],
      transition: hasCurrentLifecycle ? "当前 Scene Delta" : "类型化 Scene Delta",
      metricA: String(currentInput?.generated_instance_count ?? 12),
      metricALabel: "确定性 PCG 实例",
      metricB: "0",
      metricBLabel: "源关卡改写",
      note: hasCurrentLifecycle
        ? currentPublished
          ? "当前谱系由事件 35–37 的采用、发布与审阅回执重建；新进程加载的是精确 Published 版本，源 ArtFlowDemo 字节未变化。"
          : currentAdopted
          ? "采用决定引用当前双灯光组回执、新回渲与 accepted 评价；源关卡哈希和保护结构不变，发布仍是独立的后续动作。"
          : correctionAccepted
            ? "当前结果已经满足硬约束与视觉方向；采用与发布仍通过各自的类型化事件推进。"
          : correctionNeedsAnotherPass
          ? "复评结论来自当前纠正图而非历史案例；硬约束全部通过，视觉 lighting 仍失败，因此候选没有被采用。"
          : correctionSucceeded
          ? "UE 5.8 实测：源关卡哈希不变，保护结构不变，PCG 实例 12→12；新回渲等待独立复评。"
          : "当前 UE 5.8 回执与视觉观察已进入同一事件流；下一步只生成灯光域补丁。"
        : "真实 UE 5.8 回执；新进程对账时不会重复调用 Provider 或重新导入。",
      domains: hasCurrentLifecycle ? currentDomains : ["图像·参考", "材质·通过", "资产·通过", "PCG·通过", "灯光·通过"],
    },
    {
      id: "sunlit-overgrown",
      tab: "晴光庭院 · 定向纠正",
      title: "先用 GPT Image 2 定义视觉目标，再只修正失败的光照域",
      description: "视觉目标保持原相机和灰盒轮廓，只允许阳光、材质观感与少量植被变化。第一次 UE 候选故意注入错误主光；独立评价保留图像、材质、资产与 PCG 的证据，只下发一次灯光补丁。",
      frames: [
        { src: "/api/showcase/production/m13-sun-target", alt: "GPT Image 2 生成的晴光庭院视觉目标", label: "视觉目标", title: "GPT Image 2 · 构图受保护" },
        { src: "/api/showcase/production/m13-sun-failure", alt: "主光失败的 Unreal 候选", label: "失败候选", title: "0.05 / 6500K · 仅 lighting 失败" },
        { src: "/api/showcase/production/m13-sun-corrected", alt: "只修正灯光后的 Unreal 候选", label: "定向纠正", title: "5.5 / 4200K · 新进程已对账" },
      ],
      transition: "评价 → 单域补丁",
      metricA: "1",
      metricALabel: "实际重跑领域",
      metricB: "0",
      metricBLabel: "外部重复提交",
      note: "四个成功域的证据哈希在修正前后完全一致；源 ArtFlowDemo 哈希保持不变。",
      domains: ["图像·保留", "材质·保留", "资产·保留", "PCG·保留", "灯光·已纠正"],
    },
  ];
  const [caseId, setCaseId] = useState("rain-wet-courtyard");
  useEffect(() => {
    if (hasSimulationCache && caseId !== "simulation-cache-roundtrip") {
      setCaseId("simulation-cache-roundtrip");
    } else if (hasMaterialVariation && caseId !== "material-variation-roundtrip") {
      setCaseId("material-variation-roundtrip");
    } else if (hasCameraMove && caseId !== "camera-move-roundtrip") {
      setCaseId("camera-move-roundtrip");
    } else if (hasShotPackage && caseId !== "shot-ready-environment") {
      setCaseId("shot-ready-environment");
    } else if (hasNativePcgDensity && caseId !== "native-pcg-density") {
      setCaseId("native-pcg-density");
    } else if (hasProceduralKit && caseId !== "procedural-kit-assembly") {
      setCaseId("procedural-kit-assembly");
    } else if (hasSurfaceDetail && caseId !== "scene-surface-detail") {
      setCaseId("scene-surface-detail");
    } else if (hasSetDressing && caseId !== "physics-set-dressing") {
      setCaseId("physics-set-dressing");
    } else if (hasSurfaceBake && caseId !== "surface-bake-roundtrip") {
      setCaseId("surface-bake-roundtrip");
    } else if (hasSceneLookdev && caseId === "rain-wet-courtyard") {
      setCaseId("scene-conditioned-lookdev");
    }
  }, [caseId, hasCameraMove, hasMaterialVariation, hasNativePcgDensity, hasProceduralKit, hasSceneLookdev, hasSetDressing, hasShotPackage, hasSimulationCache, hasSurfaceBake, hasSurfaceDetail]);
  const activeCase = cases.find((item) => item.id === caseId) ?? cases[0];
  const capabilities = [
    { key: "image", label: "视觉方向", detail: "GPT Image 2 / ComfyUI", tone: "cyan" },
    { key: "mesh", label: "三维候选", detail: "GLB / 项目资产", tone: "amber" },
    { key: "material", label: "材质", detail: "PBR 五通道", tone: "violet" },
    { key: "layout", label: "场景布局", detail: "PCG / Actor", tone: "lime" },
    { key: "lighting", label: "灯光", detail: "强度 / 色温", tone: "coral" },
    { key: "unreal", label: "候选关卡", detail: "UE 5.8 Interchange", tone: "cyan" },
  ];
  return (
    <section className="pipeline-overview" aria-label="二维意图到 Unreal 三维候选">
      <nav className="case-switcher" aria-label="真实生产案例">
        {cases.map((item, index) => (
          <button
            className={item.id === caseId ? "active" : ""}
            key={item.id}
            onClick={() => setCaseId(item.id)}
            type="button"
          >
            <span>{String(index + 1).padStart(2, "0")}</span>
            {item.tab}
          </button>
        ))}
      </nav>
      <div className="pipeline-story">
        <div>
          <span className="pipeline-tag"><Workflow size={14} /> 当前场景路线</span>
          <h2>{activeCase.title}</h2>
          <p>{activeCase.description}</p>
        </div>
        <div className="pipeline-run-facts">
          <span><i className="live-dot" /> 运行追踪</span>
          <strong>{agent.timeline.length} 个场景事件</strong>
          <small>输入、变更与回执已绑定</small>
        </div>
      </div>

      <div
        className="domain-ledger"
        aria-label="本次 Scene Delta 领域状态"
        style={{ gridTemplateColumns: `repeat(${activeCase.domains.length}, minmax(0, 1fr))` }}
      >
        {activeCase.domains.map((item, index) => (
          <span key={item} className={item.includes("纠正") ? "corrected" : item.includes("待") ? "failed" : "passed"}>
            <b>{String(index + 1).padStart(2, "0")}</b>{item}
          </span>
        ))}
      </div>

      {activeCase.id === "sunlit-overgrown" && lineage && (
        <SceneVariantLedger lineage={lineage} source={lineageSource} />
      )}

      <div className={`intent-to-world frames-${activeCase.frames.length}`}>
        {activeCase.frames.map((frame, index) => (
          <Fragment key={frame.src}>
            <figure className={"secondarySrc" in frame ? "paired-frame" : undefined}>
              {"secondarySrc" in frame && typeof frame.secondarySrc === "string" ? (
                <div className="frame-pair">
                  <img src={frame.src} alt={frame.alt} />
                  <img
                    src={frame.secondarySrc}
                    alt={
                      "secondaryAlt" in frame && typeof frame.secondaryAlt === "string"
                        ? frame.secondaryAlt
                        : frame.alt
                    }
                  />
                </div>
              ) : (
                <img src={frame.src} alt={frame.alt} />
              )}
              <figcaption><span>{frame.label}</span><strong>{frame.title}</strong></figcaption>
            </figure>
            {index < activeCase.frames.length - 1 && (
              <div className="world-transition" aria-hidden="true">
                <ScanLine size={16} />
                <span />
                <ArrowRight size={16} />
                <small>{activeCase.transition}</small>
              </div>
            )}
          </Fragment>
        ))}
        <aside className="world-verdict">
          <span><BadgeCheck size={15} /> 实机已验证</span>
          <strong>{activeCase.metricA}</strong><small>{activeCase.metricALabel}</small>
          <strong>{activeCase.metricB}</strong><small>{activeCase.metricBLabel}</small>
          <p>{activeCase.note}</p>
        </aside>
      </div>

      <div className="capability-rail" role="list" aria-label="Agent 受限能力轨道">
        {capabilities.map((item, index) => (
          <div className={`rail-node tone-${item.tone}`} role="listitem" key={item.key}>
            <span>{String(index + 1).padStart(2, "0")}</span>
            <strong>{item.label}</strong>
            <small>{item.detail}</small>
            {index < capabilities.length - 1 && <i aria-hidden="true" />}
          </div>
        ))}
      </div>
    </section>
  );
}

function SceneVariantLedger({ lineage, source }: { lineage: SceneVariantLineage; source: string }) {
  const [copied, setCopied] = useState(false);
  const copyPublishedPath = async () => {
    await navigator.clipboard.writeText(lineage.published_scene);
    setCopied(true);
    window.setTimeout(() => setCopied(false), 1600);
  };
  return (
    <section className="variant-lineage" aria-label="晴光庭院场景变体谱系">
      <header className="lineage-header">
        <div>
          <span><Route size={14} /> 场景变体谱系</span>
          <strong>一次失败，只改变一条支线；采用结果已进入 Unreal 版本</strong>
        </div>
        <div className="lineage-identity">
          <small className="lineage-source">{source}</small>
          <small>内容身份</small>
          <code>{lineage.content_identity_sha256.slice(0, 12)}</code>
          <i />
          <span>UE 5.8 已复检</span>
        </div>
      </header>
      <div className="variant-film" role="list" aria-label="候选到发布的六段谱系">
        {lineage.steps.map((step) => (
          <article
            className={`variant-frame state-${step.state}`}
            key={step.kind}
            role="listitem"
          >
            <span className="frame-index">{String(step.index).padStart(2, "0")}</span>
            <i className="frame-pulse" />
            <div>
              <strong>{step.label}</strong>
              <p>{step.detail}</p>
            </div>
            <code>{step.identity}</code>
          </article>
        ))}
      </div>
      <footer className="lineage-publish-bar">
        <div>
          <span>正式场景版本</span>
          <code title={lineage.published_scene}>{lineage.published_scene}</code>
        </div>
        <dl>
          <div><dt>保留领域</dt><dd>{lineage.retained_domains.length} / 4</dd></div>
          <div><dt>PCG 实例</dt><dd>{lineage.generated_instance_count}</dd></div>
          <div><dt>重复副作用</dt><dd>{lineage.duplicate_side_effect_count}</dd></div>
          <div><dt>源关卡保存</dt><dd>{lineage.source_level_unchanged ? "0" : "—"}</dd></div>
        </dl>
        <button type="button" onClick={() => void copyPublishedPath()}>
          {copied ? <Check size={13} /> : <Copy size={13} />}
          {copied ? "路径已复制" : "复制 Unreal 版本路径"}
        </button>
      </footer>
    </section>
  );
}

function AgentCanvas({ agent }: { agent: AgentProjection }) {
  const scene = agent.scene;
  if (!scene) return <EmptyStage />;
  if (agent.comparison_plan)
    return (
      <ComparisonLaunchCanvas agent={agent} plan={agent.comparison_plan} />
    );
  const completed = agent.provider_executions.find(
    (item) => item.status === "succeeded" && item.receipt?.artifacts.length,
  );
  if (completed)
    return <MatchedExecutionCanvas agent={agent} execution={completed} />;
  const beautyUrl = `/api/agent/runs/${agent.run_id}/scene/passes/beauty`;
  const objectIdUrl = `/api/agent/runs/${agent.run_id}/scene/passes/object_id`;
  return (
    <div className="agent-workspace">
      <section className="constraint-viewport">
        <div className="viewport-tools">
          <span>
            <Box size={13} /> 已校验场景范围
          </span>
          <span>{scene.camera_resolution.join(" × ")}</span>
        </div>
        <div
          className="terrain-map real-scene-map"
          aria-label="从 Scene Package 导入的已校验 Beauty 通道"
        >
          <img
            className="scene-beauty"
            src={beautyUrl}
            alt={`从 ${scene.source_scene} 捕获的 Beauty 通道`}
          />
          <div className="scene-vignette" />
          <div className="scan-beam" />
          {scene.protected_regions.map((region, index) => (
            <span
              key={region}
              className={`region-pin protected pin-${index % 3}`}
            >
              <ShieldCheck size={12} />
              {region}
            </span>
          ))}
          {scene.editable_regions.map((region, index) => (
            <span
              key={region}
              className={`region-pin editable edit-${index % 3}`}
            >
              <Sparkles size={12} />
              {region}
            </span>
          ))}
          <div className="viewport-reticle" />
          <div className="real-capture-seal">
            <BadgeCheck size={15} />
            <div>
              <small>
                {scene.evidence_class === "real_unreal_capture"
                  ? "真实 Unreal 捕获"
                  : "已校验场景归档"}
              </small>
              <strong>SHA-256 完整</strong>
            </div>
          </div>
          <div className="object-id-peek">
            <span>对象 ID</span>
            <img src={objectIdUrl} alt="已校验对象 ID 通道" />
          </div>
          <div className="viewport-caption">
            <strong>
              {scene.source_application} ·{" "}
              {scene.source_application_version.split("+++")[0]}
            </strong>
            <span>
              {scene.source_scene} · {shortId(scene.archive_sha256)}
            </span>
          </div>
        </div>
        <div className="pass-ribbon">
          {scene.pass_kinds.map((kind, index) => (
            <div key={kind}>
              <span>{String(index + 1).padStart(2, "0")}</span>
              <strong>{pretty(kind)}</strong>
              <i />
            </div>
          ))}
        </div>
      </section>
      <Timeline items={agent.timeline} />
    </div>
  );
}
function MatchedExecutionCanvas({
  agent,
  execution,
}: {
  agent: AgentProjection;
  execution: ProviderExecution;
}) {
  const codex = agent.codex_image_candidates.at(-1);
  const adoptedLane =
    agent.adoption_decision?.selected_role === "local_comfy"
      ? "local"
      : "codex";
  const [lane, setLane] = useState<"local" | "codex">(
    agent.adoption_decision ? adoptedLane : codex ? "codex" : "local",
  );
  const [split, setSplit] = useState(54);
  const localArtifact = execution.receipt!.artifacts[0];
  const artifact =
    lane === "codex" && codex ? codex.receipt.artifact : localArtifact;
  const sourceUrl = `/api/agent/runs/${agent.run_id}/scene/passes/beauty`;
  const localUrl = `/api/agent/runs/${agent.run_id}/executions/${execution.execution_id}/artifacts/${localArtifact.sha256}`;
  const codexUrl = codex
    ? `/api/agent/runs/${agent.run_id}/codex-candidates/${codex.receipt.candidate_id}/artifacts/${codex.receipt.artifact.sha256}`
    : null;
  const candidateUrl = lane === "codex" && codexUrl ? codexUrl : localUrl;
  const provider =
    lane === "codex" && codex
      ? "codex-builtin-imagegen"
      : execution.provider_id;
  const model =
    lane === "codex" && codex
      ? codex.receipt.requested_model_family
      : execution.model_id;
  const requestIdentity =
    lane === "codex" && codex
      ? codex.receipt.request_binding_sha256
      : (execution.receipt!.provider_request_id ?? "missing");
  const tribunalResult = agent.tribunal_report?.results.find(
    (item) =>
      item.candidate_role ===
      (lane === "codex" ? "codex_image" : "local_comfy"),
  );
  return (
    <div className="local-result-workspace matched-result-workspace">
      <section className="local-result-stage">
        <div className="local-result-head">
          <div>
            <span>
              <Workflow size={14} /> 同约束真实候选
            </span>
            <h2>同一个 Unreal 来源，两条独立执行的生成方向</h2>
          </div>
          <div className="local-success">
            <BadgeCheck size={15} />
            <span>{codex ? "2 份回执已校验" : "回执已校验"}</span>
          </div>
        </div>
        {codex && (
          <div className="candidate-lanes" aria-label="真实候选路线">
            <button
              className={lane === "local" ? "active local" : "local"}
              onClick={() => setLane("local")}
            >
              <HardDrive size={15} />
              <span>
                <small>路线 A · 本地 GPU</small>
                <strong>ComfyUI / {execution.model_id}</strong>
                <code>{shortId(localArtifact.sha256)}</code>
              </span>
            </button>
            <button
              className={lane === "codex" ? "active codex" : "codex"}
              onClick={() => setLane("codex")}
            >
              <Sparkles size={15} />
              <span>
                <small>路线 B · GPT Image 2</small>
                <strong>GPT Image 2</strong>
                <code>{shortId(codex.receipt.artifact.sha256)}</code>
              </span>
            </button>
          </div>
        )}
        <div className="comparison-stage local-compare">
          <img
            className="compare-source"
            src={sourceUrl}
            alt="已校验 Unreal Beauty 来源"
          />
          <div
            className="compare-candidate"
            style={{ clipPath: `inset(0 0 0 ${split}%)` }}
          >
            <img
              src={candidateUrl}
              alt={
                lane === "codex"
                  ? "真实 Codex GPT Image 2 候选"
                  : "真实本地 ComfyUI 候选"
              }
            />
          </div>
          <span className="compare-label source">UE 来源</span>
          <span className={`compare-label result ${lane}`}>
            {lane === "codex" ? "GPT IMAGE 2 候选" : "COMFYUI 候选"}
          </span>
          <div className="split-line" style={{ left: `${split}%` }}>
            <i>
              <ChevronRight size={12} />
            </i>
          </div>
        </div>
        <div className="compare-control">
          <span>A</span>
          <input
            type="range"
            min="0"
            max="100"
            value={split}
            onChange={(event) => setSplit(Number(event.target.value))}
            aria-label="比较 Unreal 来源与当前真实候选"
          />
          <span>B</span>
          <strong>候选占比 {100 - split}%</strong>
        </div>
        <div className="local-receipt-strip">
          <div>
            <small>执行面</small>
            <strong>{provider}</strong>
            <code>{model}</code>
          </div>
          <div>
            <small>{lane === "codex" ? "请求绑定" : "提示词 ID"}</small>
            <strong>{shortId(requestIdentity)}</strong>
            <code>
              {lane === "codex"
                ? "只发送 Beauty · 本地通道未上传"
                : "持久事件账本"}
            </code>
          </div>
          <div>
            <small>输出 SHA-256</small>
            <strong>{shortId(artifact.sha256)}</strong>
            <code>{artifact.media_type}</code>
          </div>
          <div>
            <small>采用状态</small>
            <strong>
              {agent.adoption_decision?.selected_role ===
              (lane === "codex" ? "codex_image" : "local_comfy")
                ? "已采用"
                : "未选择"}
            </strong>
            <code>
              {agent.adoption_decision
                ? `Codex 证据 · ${shortId(agent.adoption_decision.decision_id)}`
                : tribunalResult
                  ? "已记录独立裁决"
                  : "等待独立评价"}
            </code>
          </div>
        </div>
        {tribunalResult && (
          <section className="tribunal-panel">
            <div className="tribunal-head">
              <span>
                <ShieldCheck size={14} /> 独立评价 Tribunal
              </span>
              <strong
                className={tribunalResult.eligible ? "eligible" : "ineligible"}
              >
                {tribunalResult.eligible
                  ? "可采用 · 尚未采用"
                  : "不可采用"}
              </strong>
              <code>{shortId(agent.tribunal_report!.dossier_sha256)}</code>
            </div>
            <div className="tribunal-claims">
              {tribunalResult.claims.map((claim) => (
                <article key={claim.claim_id} className={claim.verdict}>
                  <div>
                    <small>
                      {pretty(claim.evaluator_id)} ·{" "}
                      {claim.hard_failure ? "硬约束" : "代理指标"}
                    </small>
                    <strong>{pretty(claim.metric_name)}</strong>
                  </div>
                  <b>
                    {claim.observed.toFixed(3)}{" "}
                    <em>
                      {claim.comparator} {claim.threshold}
                    </em>
                  </b>
                  <p>{evidenceText(claim.limitation)}</p>
                </article>
              ))}
            </div>
          </section>
        )}
        {agent.multimodal_tribunal && (
          <NegativeControlPanel
            agent={agent}
            report={agent.multimodal_tribunal}
          />
        )}
        {agent.bounded_revision_result && (
          <BoundedRevisionPanel agent={agent} />
        )}
        {agent.recovery_scorecard && (
          <RecoveryPanel scorecard={agent.recovery_scorecard} />
        )}
        {agent.memory_scorecard && (
          <MemoryPanel
            records={agent.memory_records}
            scorecard={agent.memory_scorecard}
          />
        )}
        {agent.harness_scorecard && (
          <HarnessPanel scorecard={agent.harness_scorecard} />
        )}
        {agent.verified_delivery && (
          <VerifiedDeliveryPanel
            runId={agent.run_id}
            delivery={agent.verified_delivery}
          />
        )}
      </section>
      <Timeline items={agent.timeline} />
    </div>
  );
}
function NegativeControlPanel({
  agent,
  report,
}: {
  agent: AgentProjection;
  report: MultimodalTribunal;
}) {
  const record = report.negative_control;
  const artifact = record.receipt.artifact;
  const imageUrl = `/api/agent/runs/${agent.run_id}/negative-controls/${record.receipt.control_id}/artifacts/${artifact.sha256}`;
  const deterministic = report.deterministic_negative_result.claims;
  const aspect = deterministic.find(
    (claim) => claim.metric_name === "aspect_ratio_drift",
  );
  const layout = deterministic.find(
    (claim) => claim.metric_name === "coarse_edge_layout_similarity",
  );
  const critic = report.critic.claims.filter(
    (claim) => claim.candidate_role === "negative_control",
  );
  const aesthetic = critic.find(
    (claim) => claim.dimension === "aesthetic_coherence",
  );
  return (
    <section className="negative-control-panel">
      <div className="negative-control-head">
        <div>
          <span>
            <CircleAlert size={14} /> 仅用于评价的负对照
          </span>
          <h3>视觉上足够诱人，但违反约束，必须拒绝。</h3>
        </div>
        <strong>已拒绝 · 硬约束</strong>
      </div>
      <div className="negative-control-grid">
        <div className="negative-control-image">
          <img
            src={imageUrl}
            alt="视觉表现较强但违反场景约束的负对照"
          />
          <span>不能进入生产候选</span>
        </div>
        <div className="negative-control-evidence">
          <div className="appeal-vs-policy">
            <div>
              <small>多模态视觉评价</small>
              <strong>
                通过 · {Math.round((aesthetic?.confidence ?? 0) * 100)}%
              </strong>
            </div>
            <ArrowRight size={18} />
            <div>
              <small>确定性资格检查</small>
              <strong>失败 · 优先裁决</strong>
            </div>
          </div>
          <div className="negative-metrics">
            <Fact
              label="画幅漂移"
              value={`${aspect?.observed.toFixed(3)} > ${aspect?.threshold}`}
              mono
            />
            <Fact
              label="边缘布局代理指标"
              value={`${layout?.observed.toFixed(3)} < ${layout?.threshold}`}
              mono
            />
            <Fact label="制品" value={shortId(artifact.sha256)} mono />
            <Fact label="Critic 隐藏推理" value="不记录" />
          </div>
          <div className="violation-tags">
            {record.request.intended_violations.map((item) => (
              <span key={item}>{pretty(item)}</span>
            ))}
          </div>
          <div className="critic-observations">
            {critic
              .filter((claim) => claim.verdict === "fail")
              .map((claim) => (
                <p key={claim.claim_id}>
                  <b>{pretty(claim.dimension)}</b>
                  {evidenceText(claim.observation)}
                </p>
              ))}
          </div>
          <div className="hard-precedence">
            <ShieldCheck size={14} />
            <p>
              <strong>视觉置信度不能覆盖确定性资格失败。</strong>{" "}
              该负对照被永久隔离，后续生产决策只能从满足硬约束的路线中选择。
            </p>
          </div>
        </div>
      </div>
    </section>
  );
}

function BoundedRevisionPanel({ agent }: { agent: AgentProjection }) {
  const [split, setSplit] = useState(52);
  const adoption = agent.adoption_decision;
  const request = agent.bounded_revision_request;
  const result = agent.bounded_revision_result;
  const codex = agent.codex_image_candidates.find(
    (item) => item.receipt.candidate_id === adoption?.selected_candidate_id,
  );
  if (!adoption || !request || !result || !codex) return null;
  const base = `/api/agent/runs/${agent.run_id}/bounded-revisions/${result.revision_id}/artifacts`;
  const parentUrl = `/api/agent/runs/${agent.run_id}/codex-candidates/${codex.receipt.candidate_id}/artifacts/${codex.receipt.artifact.sha256}`;
  const revisionUrl = `${base}/composite/${result.composite_artifact_sha256}`;
  const maskUrl = `${base}/mask/${request.mask.artifact_sha256}`;
  return (
    <section className="bounded-revision-panel">
      <div className="revision-head">
        <div>
          <span>
            <Sparkles size={14} /> 自动采用 · 局部修订
          </span>
          <h3>证据选中方向，遮罩锁住改动。</h3>
          <p>
            Codex
            编排器自动采用唯一满足硬约束且视觉方向通过的候选，不需要人工批准。
          </p>
        </div>
        <div className="revision-seal">
          <Check size={15} />
          <span>已验证</span>
          <strong>遮罩外 0 像素变化</strong>
        </div>
      </div>
      <div className="revision-compare">
        <img src={parentUrl} alt="自动采用的父候选" />
        <div
          className="revision-after"
          style={{ clipPath: `inset(0 0 0 ${split}%)` }}
        >
          <img src={revisionUrl} alt="遮罩约束后的最终修订" />
        </div>
        <span className="revision-label before">采用父图</span>
        <span className="revision-label after">最终修订</span>
        <div className="revision-split" style={{ left: `${split}%` }}>
          <i>
            <ChevronRight size={12} />
          </i>
        </div>
      </div>
      <div className="revision-slider">
        <span>父图</span>
        <input
          type="range"
          min="0"
          max="100"
          value={split}
          onChange={(event) => setSplit(Number(event.target.value))}
          aria-label="比较采用父图与遮罩修订"
        />
        <span>修订</span>
      </div>
      <div className="revision-proof">
        <div className="mask-preview">
          <img src={maskUrl} alt="白色可编辑、黑色保护的持久化遮罩" />
          <span>可编辑遮罩</span>
          <strong>{(request.mask.coverage_ratio * 100).toFixed(2)}%</strong>
        </div>
        <div className="proof-metrics">
          <Fact
            label="遮罩外变化"
            value={`${result.leakage.outside_changed_pixels} / ${result.leakage.outside_pixel_count.toLocaleString()}`}
            mono
          />
          <Fact
            label="遮罩内变化"
            value={`${(result.leakage.inside_change_ratio * 100).toFixed(2)}%`}
            mono
          />
          <Fact
            label="修订尝试"
            value={`${result.attempt} 次 · 第 1 次硬边结果已保留`}
          />
          <Fact label="合成器" value={result.compositor_id} mono />
          <Fact label="决策证据" value={shortId(adoption.decision_id)} mono />
          <Fact
            label="最终制品"
            value={shortId(result.composite_artifact_sha256)}
            mono
          />
        </div>
      </div>
      <div className="revision-truth">
        <ShieldCheck size={14} />
        <p>
          <strong>像素级硬证明：</strong>1,530,358
          个遮罩外像素与采用父图逐像素一致。该证明不声称遮罩内语义质量或隐藏 3D
          拓扑已被验证。
        </p>
      </div>
    </section>
  );
}

const recoveryNames: Record<string, string> = {
  before_reservation: "预留前中断",
  after_reservation: "预留后中断",
  after_submit: "提交后失联",
  completion_unknown: "完成状态未知",
  after_artifact_persistence_before_event_commit: "制品落盘后中断",
  adoption_revision_replay: "采用与修订重放",
};

function RecoveryPanel({ scorecard }: { scorecard: RecoveryScorecard }) {
  const trace = scorecard.cases.find((item) => item.case_id === "after_submit");
  return (
    <section className="recovery-panel">
      <div className="recovery-heading">
        <div>
          <span>
            <RefreshCw size={14} /> 故障恢复 · Exactly-once
          </span>
          <h3>断点可以重放，外部副作用不能重复。</h3>
          <p>
            冻结故障矩阵由本地确定性夹具执行；完成状态未知时，Agent
            保持等待并禁止自动重提。
          </p>
        </div>
        <div className="recovery-score">
          <strong>
            {scorecard.passed_cases}/{scorecard.total_cases}
          </strong>
          <span>全部通过</span>
        </div>
      </div>
      <div className="recovery-cases">
        {scorecard.cases.map((item) => (
          <div key={item.case_id} className={item.passed ? "passed" : "failed"}>
            <Check size={12} />
            <span>{recoveryNames[item.case_id] ?? item.case_id}</span>
            <strong>{item.provider_side_effect_count} 次副作用</strong>
          </div>
        ))}
      </div>
      <div className="recovery-proof">
        <Fact
          label="重复副作用"
          value={String(scorecard.duplicate_side_effect_count)}
          mono
        />
        <Fact
          label="本地恢复总耗时"
          value={`${scorecard.recovery_latency_ms_total.toFixed(1)} ms`}
          mono
        />
        <Fact label="版本" value={scorecard.matrix_version} mono />
        <Fact
          label="事件序列"
          value={trace ? `#${trace.final_event_sequence}` : "—"}
          mono
        />
      </div>
      {trace && (
        <div className="recovery-trace">
          <Workflow size={14} />
          <div>
            <span>恢复链路样本</span>
            <strong>提交后失联 → 查询复用请求 → 禁止重提 → 验证终态</strong>
          </div>
          <code>
            {trace.trace_path} ·{" "}
            {shortId(trace.evidence_event_hashes.at(-1) ?? "")}
          </code>
        </div>
      )}
    </section>
  );
}

const memoryKindNames = {
  episodic: "运行经验",
  semantic: "项目规则",
  procedural: "生产方法",
};

function MemoryPanel({
  records,
  scorecard,
}: {
  records: MemoryRecord[];
  scorecard: MemoryScorecard;
}) {
  const active = records.filter((record) => record.status === "active");
  return (
    <section className="memory-panel">
      <div className="memory-heading">
        <div>
          <span>
            <BrainCircuit size={14} /> 证据治理 · 生产记忆
          </span>
          <h3>经验可以演化，但不能脱离来源。</h3>
          <p>
            Agent
            只检索当前项目的激活记录；每条规则都能回到真实事件哈希，项目私有证据不会静默提升为共享记忆。
          </p>
        </div>
        <div className="memory-score">
          <strong>
            {scorecard.passed_cases}/{scorecard.total_cases}
          </strong>
          <span>治理案例通过</span>
        </div>
      </div>
      <div className="memory-ledger">
        {active.map((record, index) => (
          <article
            key={record.proposal.memory_id}
            className={`memory-${record.proposal.kind}`}
          >
            <div className="memory-index">0{index + 1}</div>
            <div className="memory-copy">
              <span>
                {memoryKindNames[record.proposal.kind]} · v
                {record.proposal.version}
              </span>
              <strong>{record.proposal.value}</strong>
              <code>{record.proposal.subject_key}</code>
            </div>
            <div className="memory-citation">
              <small>来源事件</small>
              <strong>{record.proposal.source_event_hashes.length} 条</strong>
              <code>{shortId(record.proposal.content_sha256)}</code>
            </div>
          </article>
        ))}
      </div>
      <div className="memory-metrics">
        <Fact label="激活记忆" value={`${active.length} 条`} />
        <Fact
          label="检索精度"
          value={`${(scorecard.retrieval_precision * 100).toFixed(0)}%`}
          mono
        />
        <Fact
          label="冲突拒绝率"
          value={`${(scorecard.conflict_rejection_rate * 100).toFixed(0)}%`}
          mono
        />
        <Fact label="检索方式" value="精确元数据 + 事件引用" />
      </div>
      <div className="memory-truth">
        <ShieldCheck size={14} />
        <p>
          <strong>治理边界：</strong>
          当前没有向量检索、跨项目共享或个人聊天记忆。shared scope 缺少独立
          authority contract 时必定拒绝。
        </p>
      </div>
    </section>
  );
}

const harnessDomainNames = {
  context: "上下文",
  capability: "能力边界",
  routing: "模型路由",
  policy: "策略门禁",
  recovery: "故障恢复",
  memory: "记忆治理",
};

function HarnessPanel({ scorecard }: { scorecard: HarnessScorecard }) {
  const countByDomain = Object.fromEntries(
    Object.keys(harnessDomainNames).map((domain) => [
      domain,
      scorecard.cases.filter((item) => item.domain === domain).length,
    ]),
  );
  const metric = (id: string) =>
    scorecard.metrics.find((item) => item.metric_id === id);
  const taskPass = metric("harness_task_pass_rate");
  const contextRecall = metric("context_case_recall");
  const routePolicy = metric("route_policy_accuracy");
  const falseInterrupt = metric("false_interrupt_rate");
  const duplicate = metric("duplicate_side_effect_rate");
  const cost = metric("fixture_external_cost");
  return (
    <section className="harness-panel">
      <div className="harness-heading">
        <div>
          <span>
            <ScanLine size={14} /> 冻结 AGENT HARNESS · 飞行记录仪
          </span>
          <h3>不是一段漂亮演示，是可重放的 Agent 能力证据。</h3>
          <p>
            同一套冻结夹具同时审计上下文召回、能力声明、模型路由、策略优先级、崩溃恢复与记忆治理；每个结论都带事件或记分卡引用。
          </p>
        </div>
        <div className="harness-score">
          <strong>{scorecard.passed_cases}</strong>
          <i>/</i>
          <b>{scorecard.total_cases}</b>
          <span>案例通过</span>
        </div>
      </div>
      <div className="harness-domains">
        {Object.entries(harnessDomainNames).map(([domain, name], index) => (
          <article key={domain}>
            <small>0{index + 1}</small>
            <span>{name}</span>
            <strong>{countByDomain[domain]}</strong>
            <i>通过</i>
          </article>
        ))}
      </div>
      <div className="harness-metrics">
        <Fact
          label="上下文召回"
          value={`${contextRecall?.numerator ?? 0}/${contextRecall?.denominator ?? 0}`}
          mono
        />
        <Fact
          label="路由 / 策略准确"
          value={`${routePolicy?.numerator ?? 0}/${routePolicy?.denominator ?? 0}`}
          mono
        />
        <Fact
          label="误打断"
          value={`${falseInterrupt?.numerator ?? 0}/${falseInterrupt?.denominator ?? 0}`}
          mono
        />
        <Fact
          label="重复副作用"
          value={`${duplicate?.numerator ?? 0}/${duplicate?.denominator ?? 0}`}
          mono
        />
        <Fact label="外部调用成本" value={`$${cost?.value ?? 0}`} mono />
      </div>
      <div className="harness-footer">
        <div>
          <ShieldCheck size={15} />
          <p>
            <strong>证据边界：</strong>
            本分数衡量冻结本地夹具的控制面行为，不代表生产 provider
            延迟，也不声称开放域生成质量。
          </p>
        </div>
        <code>
          {scorecard.suite_version} · {shortId(scorecard.scorecard_sha256)} ·{" "}
          {taskPass?.numerator}/{taskPass?.denominator}
        </code>
      </div>
    </section>
  );
}

function VerifiedDeliveryPanel({
  runId,
  delivery,
}: {
  runId: string;
  delivery: VerifiedDelivery;
}) {
  const receipt = delivery.return_receipt;
  const visibleUrl = `/api/agent/runs/${runId}/verified-deliveries/${delivery.delivery_sha256}/visible/${delivery.visible_evidence_sha256}`;
  return (
    <section className="delivery-panel">
      <div className="delivery-visual">
        <img
          src={visibleUrl}
          alt="已采用结果回流到 Unreal ArtFlowDemo 的真实视口"
        />
        <div className="delivery-visual-seal">
          <BadgeCheck size={15} />
          <span>UE 5.8 真实回流</span>
          <strong>{receipt.binding_actor_label}</strong>
        </div>
        <div className="delivery-scan" />
      </div>
      <div className="delivery-story">
        <div className="delivery-kicker">
          <Fingerprint size={15} /> 可核验交付 · 闭环终点
        </div>
        <h3>从场景事实出发，带着证据回到 Unreal。</h3>
        <p className="delivery-lead">
          被独立 Tribunal 选中的候选经过蒙版限定修订，随后由固定 typed tool
          写回项目自有 UE
          工程。这里展示的不是概念图，而是绑定到持久事件的真实宿主截图。
        </p>
        <div className="delivery-chain" aria-label="ArtFlow 交付证据链">
          <div>
            <small>01</small>
            <span>Scene Package</span>
            <strong>真实四 Pass</strong>
          </div>
          <ArrowRight size={13} />
          <div>
            <small>02</small>
            <span>独立评价</span>
            <strong>硬约束优先</strong>
          </div>
          <ArrowRight size={13} />
          <div>
            <small>03</small>
            <span>局部纠正</span>
            <strong>蒙版外 0 像素</strong>
          </div>
          <ArrowRight size={13} />
          <div>
            <small>04</small>
            <span>Unreal 回流</span>
            <strong>Receipt 已记录</strong>
          </div>
        </div>
        <div className="delivery-proof-grid">
          <div className="delivery-proof-primary">
            <strong>9/9</strong>
            <span>来源文件哈希绑定通过</span>
            <small>独立只读验证器，不依赖 Agent UI 自报</small>
          </div>
          <Fact label="目标关卡" value={receipt.bound_scene_path} mono />
          <Fact
            label="引擎版本"
            value={receipt.engine_version.split("-")[0]}
            mono
          />
          <Fact label="事件序列" value="25 · 无待处理决策" mono />
          <Fact
            label="交付身份"
            value={shortId(delivery.delivery_sha256)}
            mono
          />
        </div>
        <div className="delivery-limit">
          <CircleAlert size={14} />
          <p>
            <strong>C2PA 边界：</strong>
            当前为采用 C2PA 2.4 断言词汇的 unsigned
            sidecar；内容哈希链已验证，但没有签名证书，
            <b>不声称加密签名凭证</b>。
          </p>
        </div>
        <code className="delivery-path">{receipt.imported_asset_path}</code>
      </div>
    </section>
  );
}

function ComparisonLaunchCanvas({
  agent,
  plan,
}: {
  agent: AgentProjection;
  plan: ComparisonPlan;
}) {
  const preview = plan.operator_preview;
  const results = new Map(
    agent.comparison_manifest?.children.map((child) => [child.role, child]),
  );
  const authorized = Boolean(agent.comparison_authorization);
  return (
    <div className="launch-workspace">
      <section className="launch-theatre">
        <div className="launch-head">
          <div>
            <span>
              <Workflow size={14} /> 同约束双 Provider 运行
            </span>
            <h2>同一个场景，两条相互隔离的执行路线</h2>
            <p>
              两条路线共享视觉目标，但执行身份、权限与恢复状态完全独立。
            </p>
          </div>
          <div
            className={`launch-state ${agent.comparison_manifest?.status ?? (authorized ? "authorized" : "awaiting")}`}
          >
            <i />
            {pretty(
              agent.comparison_manifest?.status ??
                (authorized ? "authorized" : "awaiting owner"),
            )}
          </div>
        </div>
        <div className="shared-origin">
          <span>场景约束包</span>
          <strong>{plan.scene_package_id}</strong>
          <code>{shortId(plan.scene_package_sha256)}</code>
          <div className="origin-pulse" />
        </div>
        <div className="provider-rails">
          {plan.children.map((child) => {
            const result = results.get(child.role);
            const isLocal = child.role === "local";
            return (
              <article
                className={`provider-rail ${child.role}`}
                key={child.role}
              >
                <div className="rail-index">
                  {isLocal ? "A / 本地" : "B / 托管"}
                </div>
                <div className="provider-mark">
                  {isLocal ? <HardDrive size={21} /> : <Cloud size={21} />}
                </div>
                <div className="provider-copy">
                  <small>
                    {isLocal ? "本地 GPU 路线" : "计费图像编辑"}
                  </small>
                  <h3>{child.provider_id}</h3>
                  <p>{child.model_id}</p>
                </div>
                <div className="rail-flow">
                  <span>beauty.png</span>
                  <ArrowRight size={16} />
                  <span>
                    {preview.output_count_per_provider} × {preview.output_size}
                  </span>
                </div>
                <div className="authority-seal">
                  <LockKeyhole size={14} />
                  <div>
                    <small>独立执行边界</small>
                    <strong>{pretty(child.authority_kind)}</strong>
                  </div>
                </div>
                <div
                  className={`result-signal status-${result?.status ?? (authorized ? "ready" : "locked")}`}
                >
                  <i />
                  <span>
                    {pretty(
                      result?.status ?? (authorized ? "ready" : "locked"),
                    )}
                  </span>
                  {result?.receipt?.provider_request_id && (
                    <code>{shortId(result.receipt.provider_request_id)}</code>
                  )}
                </div>
              </article>
            );
          })}
        </div>
        <div className="launch-metrics">
          <div>
            <Gauge size={16} />
            <span>托管调用估算</span>
            <strong>${preview.estimated_hosted_cost_usd.toFixed(2)}</strong>
            <small>
              最高 ${preview.maximum_hosted_cost_usd.toFixed(2)}
            </small>
          </div>
          <div>
            <ShieldCheck size={16} />
            <span>远程上传白名单</span>
            <strong>{preview.hosted_uploads.join(" + ")}</strong>
            <small>评价通道保持本地</small>
          </div>
          <div>
            <Fingerprint size={16} />
            <span>隐私范围</span>
            <strong>{pretty(preview.hosted_privacy_class)}</strong>
            <small>成本上限由控制平面执行</small>
          </div>
        </div>
        <div className="launch-truth">
          <CircleAlert size={15} />
          <p>
            <strong>尚未采用任何候选。</strong>
            {agent.comparison_manifest
              ? ` 持久化比较状态为 ${stageLabel(agent.comparison_manifest.status)}。`
              : authorized
                ? " 执行条件已记录，实际调用仍是独立的一次性动作。"
                : " 打开比较界面不会触发任何 Provider。"}
          </p>
        </div>
      </section>
      <Timeline items={agent.timeline} />
    </div>
  );
}
function Timeline({ items }: { items: AgentProjection["timeline"] }) {
  return (
    <section className="event-river">
      <div className="river-head">
        <span>
          <Workflow size={14} /> 场景演进记录
        </span>
        <small>按实际执行顺序记录</small>
      </div>
      <div className="event-track">
        {items.map((item) => (
          <article
            key={item.event_id}
            className={`event-node tone-${item.tone}`}
          >
            <span className="event-seq">
              {String(item.sequence).padStart(2, "0")}
            </span>
            <i />
            <div>
              <strong>{timelineText(item.label)}</strong>
              <p>{timelineText(item.detail)}</p>
              <code>{item.event_type}</code>
            </div>
          </article>
        ))}
      </div>
    </section>
  );
}
function LegacyCanvas({ run }: { run: LegacyRun }) {
  const directions = run.plan.directions
    .map((direction) => ({
      direction,
      candidate: run.candidates.find(
        (item) => item.direction_name === direction.name,
      ),
    }))
    .filter((item) => item.candidate);
  const [activeIndex, setActiveIndex] = useState(0);
  const [split, setSplit] = useState(52);
  const active =
    directions[Math.min(activeIndex, Math.max(0, directions.length - 1))];
  if (!active?.candidate) return <EmptyStage />;
  const candidateUrl = `/api/runs/${run.run_id}/candidates/${active.candidate.candidate_id}`;
  return (
    <div className="comparison-workspace">
      <section className="comparison-main">
        <div className="viewport-tools">
          <span>
            <Eye size={13} /> 来源 / 候选比较
          </span>
          <span>只读 · 尚未记录选择</span>
        </div>
        <div className="comparison-stage">
          <img
            className="compare-source"
            src={`/api/runs/${run.run_id}/source`}
            alt="来源构图"
          />
          <div
            className="compare-candidate"
            style={{ clipPath: `inset(0 ${100 - split}% 0 0)` }}
          >
            <img src={candidateUrl} alt={active.direction.visual_goal} />
          </div>
          <span className="compare-label source">来源</span>
          <span className="compare-label result">候选</span>
          <div className="split-line" style={{ left: `${split}%` }}>
            <i>
              <ChevronRight size={12} />
            </i>
          </div>
        </div>
        <div className="compare-control">
          <span>A</span>
          <input
            type="range"
            min="0"
            max="100"
            value={split}
            onChange={(event) => setSplit(Number(event.target.value))}
            aria-label="来源与候选分屏比较"
          />
          <span>B</span>
          <strong>候选占比 {split}%</strong>
        </div>
      </section>
      <section className="direction-switcher">
        <div className="river-head">
          <span>
            <Layers3 size={14} /> 已捕获方向
          </span>
          <small>
            {run.candidates.length}/{run.plan.directions.length}
          </small>
        </div>
        <div className="direction-options">
          {directions.map((item, index) => (
            <button
              key={item.candidate!.candidate_id}
              className={index === activeIndex ? "active" : ""}
              onClick={() => setActiveIndex(index)}
            >
              <span>V{index + 1}</span>
              <img
                src={`/api/runs/${run.run_id}/candidates/${item.candidate!.candidate_id}`}
                alt=""
              />
              <div>
                <strong>{item.direction.visual_goal}</strong>
                <p>{item.direction.prompt_delta}</p>
                <em>{index === activeIndex ? "当前展示" : "加入比较"}</em>
              </div>
            </button>
          ))}
        </div>
        <div className="comparison-truth">
          <CircleAlert size={14} />
          <p>
            <strong>该历史运行尚未记录采用结果。</strong>
            切换比较视图不会改变持久状态，也不会自动采用候选。
          </p>
        </div>
      </section>
    </div>
  );
}
function AgentInspector({ agent }: { agent: AgentProjection }) {
  const scene = agent.scene;
  const attestation = agent.capability_attestations.at(-1);
  const preview = agent.comparison_plan?.operator_preview;
  return (
    <div className="inspector-scroll">
      <InspectorSection label="运行身份">
        <Fact label="运行 ID" value={shortId(agent.run_id)} mono />
        <Fact label="协议" value={agent.schema_id} mono />
        <Fact
          label="路线策略"
          value={
            agent.status.approval === "approved" &&
            agent.pending_decisions.length === 0
              ? "已接受"
              : stageLabel(agent.status.approval)
          }
        />
      </InspectorSection>
      {scene && (
        <>
          <div className="unreal-evidence-signal">
            <BadgeCheck size={15} />
            <div>
              <span>
                {scene.evidence_class === "real_unreal_capture"
                  ? "真实 Unreal 场景"
                  : "已校验场景归档"}
              </span>
              <strong>{scene.source_scene}</strong>
            </div>
          </div>
          <InspectorSection label="场景输入">
            <Fact
              label="宿主"
              value={`${scene.source_application} ${scene.source_application_version.split("+++")[0]}`}
            />
            <Fact label="归档哈希" value={shortId(scene.archive_sha256)} mono />
            <Fact
              label="渲染通道"
              value={`${scene.artifact_count} 个独立哈希通道`}
            />
            <Fact label="模式" value="只读导入" />
          </InspectorSection>
        </>
      )}
      {preview && (
        <>
          <div className="comparison-inspector-signal">
            <span>双 Provider 控制</span>
            <strong>
              {agent.comparison_manifest
                ? pretty(agent.comparison_manifest.status)
                : agent.comparison_authorization
                  ? "已记录执行条件"
                  : "等待执行条件"}
            </strong>
          </div>
          <InspectorSection label="托管调用影响">
            <Fact label="Endpoint" value={preview.hosted_endpoint} mono />
            <Fact label="模型" value={preview.hosted_model} mono />
            <Fact label="上传内容" value={preview.hosted_uploads.join(", ")} />
            <Fact
              label="估算 / 上限"
              value={`$${preview.estimated_hosted_cost_usd.toFixed(2)} / $${preview.maximum_hosted_cost_usd.toFixed(2)}`}
            />
            <Fact
              label="保留策略"
              value={pretty(preview.hosted_privacy_class)}
            />
          </InspectorSection>
          <InspectorSection label="尚未确认的宿主事实">
            <ul className="unresolved-list">
              {preview.unresolved_real_host_facts.map((fact) => (
                <li key={fact}>{fact}</li>
              ))}
            </ul>
          </InspectorSection>
        </>
      )}
      {agent.route && (
        <InspectorSection label="已绑定路线">
          <Fact label="Provider" value={agent.route.provider_id} mono />
          <Fact label="模型" value={agent.route.model_id} mono />
          <Fact label="隐私范围" value={pretty(agent.route.privacy_class)} />
          <Fact
            label="成本上限"
            value={`$${agent.route.max_cost_usd.toFixed(2)}`}
          />
        </InspectorSection>
      )}
      {attestation && (
        <InspectorSection label="本地运行时实测">
          <div className={`attestation-status ${attestation.status}`}>
            <span>{attestation.status === "supported" ? "已支持" : attestation.status === "unsupported" ? "不支持" : "未知"}</span>
            <i />
          </div>
          <Fact label="设备" value={attestation.device_name ?? "未知"} />
          <Fact
            label="VRAM"
            value={
              attestation.vram_mb
                ? `${Math.round(attestation.vram_mb / 1024)} GB`
                : "未知"
            }
          />
          <Fact
            label="节点 / 模型"
            value={`${attestation.observed_node_count} / ${attestation.observed_model_count}`}
          />
          <Fact
            label="环境指纹"
            value={shortId(attestation.environment_sha256)}
            mono
          />
        </InspectorSection>
      )}
      {scene && (
        <>
          <ConstraintList
            label="必须保持"
            values={scene.preserve}
            tone="keep"
          />
          <ConstraintList
            label="禁止引入"
            values={scene.prohibit}
            tone="block"
          />
        </>
      )}
      <InspectorSection label="受限工具能力">
        {agent.capabilities.map((capability) => (
          <div className="capability" key={capability.capability_id}>
            <div>
              <Zap size={13} />
              <strong>{capability.capability_id}</strong>
              <span>{capability.risk}</span>
            </div>
            <p>{evidenceText(capability.verification_signal)}</p>
            <small>
              {capability.authority.writes.length
                ? `${capability.authority.writes.length} 个写入域`
                : "只读"}{" "}
              · {pretty(capability.availability)}
            </small>
          </div>
        ))}
      </InspectorSection>
      <InspectorSection label="内容证据">
        <Fact
          label="制品"
          value={String(agent.status.artifact_ids.length)}
        />
        <Fact label="失败" value={String(agent.status.failure_count)} />
        <Fact
          label="待执行工具"
          value={String(agent.status.pending_tool_call_count)}
        />
      </InspectorSection>
    </div>
  );
}
function LegacyInspector({
  run,
  health,
}: {
  run: LegacyRun;
  health: Health | null;
}) {
  return (
    <div className="inspector-scroll">
      <div className="legacy-notice">
        <span>历史运行证据</span>
        <p>
          这条真实 RTX 4080 运行按原始状态保留，不把它包装成事件溯源 Agent 运行。
        </p>
      </div>
      <ConstraintList
        label="必须保持"
        values={run.brief.preserve}
        tone="keep"
      />
      <ConstraintList label="避免" values={run.brief.avoid} tone="block" />
      <InspectorSection label="运行事实">
        <Fact label="运行 ID" value={shortId(run.run_id)} mono />
        <Fact label="任务" value={pretty(run.brief.task_type)} />
        <Fact
          label="ComfyUI"
          value={health?.reachable ? "已连接" : "离线"}
        />
        <Fact label="候选" value={String(run.candidates.length)} />
      </InspectorSection>
    </div>
  );
}
function InspectorSection({
  label,
  children,
}: {
  label: string;
  children: React.ReactNode;
}) {
  return (
    <section className="inspector-section">
      <h3>{label}</h3>
      {children}
    </section>
  );
}
function Fact({
  label,
  value,
  mono = false,
}: {
  label: string;
  value: string;
  mono?: boolean;
}) {
  return (
    <div className="fact-row">
      <span>{label}</span>
      <strong className={mono ? "mono" : ""}>{value}</strong>
    </div>
  );
}
function ConstraintList({
  label,
  values,
  tone,
}: {
  label: string;
  values: string[];
  tone: "keep" | "block";
}) {
  return (
    <InspectorSection label={label}>
      <ul className={`constraint-list ${tone}`}>
        {values.map((value) => (
          <li key={value}>
            <span>{tone === "keep" ? "+" : "−"}</span>
            {constraintLabel(value)}
          </li>
        ))}
      </ul>
    </InspectorSection>
  );
}
function LoadingStage() {
  return (
    <div className="loading-stage">
      <span className="loader-orbit">
        <i />
      </span>
      <strong>正在重建持久状态</strong>
      <p>校验事件链与场景事实…</p>
    </div>
  );
}
function ErrorStage({ message }: { message: string }) {
  return (
    <div className="empty-stage error">
      <CircleAlert size={28} />
      <h2>场景导演台无法校验当前状态</h2>
      <p>{message}</p>
    </div>
  );
}
function EmptyStage() {
  return (
    <div className="empty-stage">
      <Aperture size={30} />
      <span>没有活动场景</span>
      <h2>先导入事实，再开始生成。</h2>
      <p>
        创建 Agent 运行并附加已校验的 Scene Package。界面不会虚构场景或 Agent 事件。
      </p>
      <code>artflow create-agent-run → attach-scene-package</code>
    </div>
  );
}
