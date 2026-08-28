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
  ScanLine,
  ShieldCheck,
  Sparkles,
  Upload,
  Workflow,
  Zap,
} from "lucide-react";
import {
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
    throw new Error(payload.detail ?? "Request failed");
  }
  return response.json();
}
const pretty = (value: string) => value.replaceAll("_", " ");
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
  const resolveAgentApproval = async (
    decisionId: string,
    resolution: "approved" | "rejected",
  ) => {
    if (!agent) return;
    setBusy(true);
    setError(null);
    try {
      await request(`/api/agent/runs/${agent.run_id}/approvals/${decisionId}`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ resolution }),
      });
      await open({ kind: "agent", id: agent.run_id });
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : String(reason));
    } finally {
      setBusy(false);
    }
  };
  const authorizeComparison = async (approvedBy: string) => {
    if (!agent) return;
    setBusy(true);
    setError(null);
    try {
      const next = await request<AgentProjection>(
        `/api/agent/runs/${agent.run_id}/comparison/authorize`,
        {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ approved_by: approvedBy }),
        },
      );
      setAgent(next);
      setAgentRuns((runs) =>
        runs.map((run) =>
          run.run_id === next.run_id
            ? {
                ...run,
                stage: next.status.stage,
                last_sequence:
                  next.timeline.at(-1)?.sequence ?? run.last_sequence,
                pending_decision_count: next.pending_decisions.length,
              }
            : run,
        ),
      );
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
          title: "No scene attached",
          subtitle:
            "Import a verified Scene Package to begin a durable Agent run.",
          stage: "empty",
        };
  const actionLabel =
    legacy?.status === "awaiting_approval"
      ? "Approve exact plan"
      : legacy?.status === "approved" || legacy?.status === "running"
        ? "Run approved directions"
        : legacy?.status === "review"
          ? "Build contact sheet"
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
                <strong>{item.scene_package_id ?? "Awaiting scene"}</strong>
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
          <span>决策与证据</span>
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
      {agent?.pending_decisions[0]?.kind === "comparison_authorization" &&
      agent.comparison_plan ? (
        <ComparisonApprovalSheet
          decision={agent.pending_decisions[0]}
          plan={agent.comparison_plan}
          busy={busy}
          onAuthorize={authorizeComparison}
        />
      ) : agent?.pending_decisions[0] ? (
        <ApprovalSheet
          decision={agent.pending_decisions[0]}
          route={agent.route}
          busy={busy}
          onResolve={resolveAgentApproval}
        />
      ) : null}
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
                ? "Reducer 状态为唯一事实"
                : legacy
                  ? "历史工作流仍可读取"
                  : "Scene Lab 已就绪"}
            </strong>
            <span>
              {agent
                ? `${agent.timeline.length} 个持久事件 · ${agent.status.artifact_ids.length} 个内容寻址制品`
                : "界面不显示也不存储隐藏思维链。"}
            </span>
          </div>
        </div>
        {agent ? (
          <div className="budget-readout">
            <span>
              ITER{" "}
              <b>
                {agent.status.budgets.used_iterations}/
                {agent.status.budgets.max_iterations}
              </b>
            </span>
            <span>
              TOOLS{" "}
              <b>
                {agent.status.budgets.used_tool_calls}/
                {agent.status.budgets.max_tool_calls}
              </b>
            </span>
            <button disabled={agent.pending_decisions.length === 0}>
              <ShieldCheck size={15} />
                {agent.pending_decisions.length
                ? "存在待处理决策"
                : "等待下一项类型化动作"}
            </button>
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
            {busy ? "Working…" : actionLabel}
            <ArrowUpRight size={14} />
          </button>
        ) : null}
      </footer>
    </div>
  );
}

function ScenePipelineOverview({ agent }: { agent: AgentProjection }) {
  const cases = [
    {
      id: "image-to-3d",
      tab: "图生 3D 道具",
      title: "从概念道具到 Unreal 可审查三维候选",
      description: "GPT Image 2 提供项目自有参考，TripoSR 生成 GLB。Agent 在写入前检查许可证、外部 URI、扩展、几何和预算，再经 Interchange 放入隔离候选关卡。",
      before: "/api/showcase/production/reference",
      beforeAlt: "GPT Image 2 生成的玄武岩祭坛概念参考",
      beforeLabel: "二维意图",
      beforeTitle: "玄武岩祭坛概念参考",
      after: "/api/showcase/production/unreal",
      afterAlt: "Unreal Engine 候选关卡中的真实三维祭坛",
      afterLabel: "UE 三维候选",
      afterTitle: "约 180 cm · 源关卡未改写",
      transition: "接纳、缩放、碰撞",
      metricA: "4,817",
      metricALabel: "UE 构建后三角面",
      metricB: "1 + 1",
      metricBLabel: "材质槽 / 简单碰撞",
      note: "当前为可识别几何和顶点色，不宣称最终 PBR 品质。",
    },
    {
      id: "pbr-return",
      tab: "PBR 材质回流",
      title: "把生成方向拆成可验证的 Unreal PBR 材质",
      description: "受审 ComfyUI 图生成五个材质通道，技术门禁逐通道拒绝彩色标量图和无效法线，只纠正失败域，再创建 UE Master Material 与 Material Instance。",
      before: "/api/showcase/production/pbr-source",
      beforeAlt: "通过校验的玄武岩 BaseColor",
      beforeLabel: "AI 材质输入",
      beforeTitle: "通过校验的玄武岩 BaseColor",
      after: "/api/showcase/production/pbr-unreal",
      afterAlt: "Unreal Engine 中完成 Shader 编译的 PBR 材质回渲",
      afterLabel: "UE Shader-ready 回渲",
      afterTitle: "Material Instance 已绑定候选球体",
      transition: "逐通道校验、纠正、绑定",
      metricA: "5 / 5",
      metricALabel: "PBR 通道通过",
      metricB: "0",
      metricBLabel: "重复导入资产",
      note: "BaseColor 来自真实 GPU 生成，失败的技术域由确定性纠正器重建。",
    },
    {
      id: "multi-domain",
      tab: "场景联合改造",
      title: "同一计划联合修改材质、PCG、灯光与项目资产",
      description: "Agent 把四个领域编译为依赖 DAG，非 UE 资产可并行准备，引擎写入严格串行。主机位判断视觉方向，瞬态验证机位复检镜头外空间关系。",
      before: "/api/showcase/production/scene-authored",
      beforeAlt: "四域 Scene Delta 的主机位回渲",
      beforeLabel: "美术主机位",
      beforeTitle: "视觉方向与构图检查",
      after: "/api/showcase/production/scene-validation",
      afterAlt: "四域 Scene Delta 的验证机位回渲",
      afterLabel: "瞬态验证机位",
      afterTitle: "空间关系与保护区复检",
      transition: "同一候选、双机位评价",
      metricA: "12",
      metricALabel: "确定性 PCG 实例",
      metricB: "0",
      metricBLabel: "保护区侵入",
      note: "重复执行仍为 12 个实例，源 ArtFlowDemo 关卡哈希保持不变。",
    },
    {
      id: "targeted-correction",
      tab: "失败域纠正",
      title: "评价失败后只重做灯光，不重跑整条生成链",
      description: "测试主动注入 0.05 lux 主光失败。Technical Judge 与 Visual Critic 独立锁定 lighting，Correction Planner 锁住已通过的资产、材质和 PCG 证据。",
      before: "/api/showcase/production/lighting-failure",
      beforeAlt: "注入低照度失败的 Unreal 候选",
      beforeLabel: "失败回渲",
      beforeTitle: "0.05 lux · 平均亮度 117.72",
      after: "/api/showcase/production/lighting-corrected",
      afterAlt: "只纠正灯光后的 Unreal 候选",
      afterLabel: "定向纠正",
      afterTitle: "8.0 lux / 4200K · 平均亮度 166.66",
      transition: "失败分类、灯光补丁、复检",
      metricA: "1",
      metricALabel: "实际重跑领域",
      metricB: "0",
      metricBLabel: "外部重复提交",
      note: "材质路径和 12 个 PCG 实例保持不变，丢失回执由新进程对账。",
    },
  ] as const;
  const [caseId, setCaseId] = useState<(typeof cases)[number]["id"]>("image-to-3d");
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
          <span className="pipeline-tag"><Workflow size={14} /> 当前作品集主线</span>
          <h2>{activeCase.title}</h2>
          <p>{activeCase.description}</p>
        </div>
        <div className="pipeline-run-facts">
          <span><i className="live-dot" /> 当前运行</span>
          <strong>{agent.timeline.length} 个持久事件</strong>
          <small>隐藏思维链不进入界面或回执</small>
        </div>
      </div>

      <div className="intent-to-world">
        <figure>
          <img src={activeCase.before} alt={activeCase.beforeAlt} />
          <figcaption><span>{activeCase.beforeLabel}</span><strong>{activeCase.beforeTitle}</strong></figcaption>
        </figure>
        <div className="world-transition" aria-hidden="true">
          <ScanLine size={18} />
          <span />
          <ArrowRight size={18} />
          <small>{activeCase.transition}</small>
        </div>
        <figure>
          <img src={activeCase.after} alt={activeCase.afterAlt} />
          <figcaption><span>{activeCase.afterLabel}</span><strong>{activeCase.afterTitle}</strong></figcaption>
        </figure>
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
            <Box size={13} /> VERIFIED SCENE FIELD
          </span>
          <span>{scene.camera_resolution.join(" × ")}</span>
        </div>
        <div
          className="terrain-map real-scene-map"
          aria-label="Verified beauty pass from the imported Scene Package"
        >
          <img
            className="scene-beauty"
            src={beautyUrl}
            alt={`Beauty pass captured from ${scene.source_scene}`}
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
                  ? "REAL UNREAL CAPTURE"
                  : "VERIFIED SCENE ARCHIVE"}
              </small>
              <strong>SHA-256 intact</strong>
            </div>
          </div>
          <div className="object-id-peek">
            <span>OBJECT ID</span>
            <img src={objectIdUrl} alt="Verified object-ID pass" />
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
              <Workflow size={14} /> MATCHED REAL CANDIDATES
            </span>
            <h2>One Unreal source. Two independently executed directions.</h2>
          </div>
          <div className="local-success">
            <BadgeCheck size={15} />
            <span>{codex ? "2 RECEIPTS VERIFIED" : "RECEIPT VERIFIED"}</span>
          </div>
        </div>
        {codex && (
          <div className="candidate-lanes" aria-label="Real candidate lanes">
            <button
              className={lane === "local" ? "active local" : "local"}
              onClick={() => setLane("local")}
            >
              <HardDrive size={15} />
              <span>
                <small>LANE A · LOCAL GPU</small>
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
                <small>LANE B · CODEX BUILT-IN</small>
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
            alt="Verified Unreal beauty source"
          />
          <div
            className="compare-candidate"
            style={{ clipPath: `inset(0 0 0 ${split}%)` }}
          >
            <img
              src={candidateUrl}
              alt={
                lane === "codex"
                  ? "Real Codex GPT Image 2 candidate"
                  : "Real local ComfyUI candidate"
              }
            />
          </div>
          <span className="compare-label source">UE SOURCE</span>
          <span className={`compare-label result ${lane}`}>
            {lane === "codex" ? "GPT IMAGE 2 CANDIDATE" : "COMFY CANDIDATE"}
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
            aria-label="Compare Unreal source and selected real candidate"
          />
          <span>B</span>
          <strong>{100 - split}% candidate</strong>
        </div>
        <div className="local-receipt-strip">
          <div>
            <small>EXECUTION SURFACE</small>
            <strong>{provider}</strong>
            <code>{model}</code>
          </div>
          <div>
            <small>{lane === "codex" ? "REQUEST BINDING" : "PROMPT ID"}</small>
            <strong>{shortId(requestIdentity)}</strong>
            <code>
              {lane === "codex"
                ? "beauty only · local passes withheld"
                : "durable ledger"}
            </code>
          </div>
          <div>
            <small>OUTPUT SHA-256</small>
            <strong>{shortId(artifact.sha256)}</strong>
            <code>{artifact.media_type}</code>
          </div>
          <div>
            <small>ADOPTION</small>
            <strong>
              {agent.adoption_decision?.selected_role ===
              (lane === "codex" ? "codex_image" : "local_comfy")
                ? "ADOPTED"
                : "NOT SELECTED"}
            </strong>
            <code>
              {agent.adoption_decision
                ? `Codex evidence · ${shortId(agent.adoption_decision.decision_id)}`
                : tribunalResult
                  ? "independent verdicts recorded"
                  : "tribunal pending"}
            </code>
          </div>
        </div>
        {tribunalResult && (
          <section className="tribunal-panel">
            <div className="tribunal-head">
              <span>
                <ShieldCheck size={14} /> INDEPENDENT TRIBUNAL
              </span>
              <strong
                className={tribunalResult.eligible ? "eligible" : "ineligible"}
              >
                {tribunalResult.eligible
                  ? "ELIGIBLE · NOT ADOPTED"
                  : "INELIGIBLE"}
              </strong>
              <code>{shortId(agent.tribunal_report!.dossier_sha256)}</code>
            </div>
            <div className="tribunal-claims">
              {tribunalResult.claims.map((claim) => (
                <article key={claim.claim_id} className={claim.verdict}>
                  <div>
                    <small>
                      {pretty(claim.evaluator_id)} ·{" "}
                      {claim.hard_failure ? "HARD GATE" : "PROXY"}
                    </small>
                    <strong>{pretty(claim.metric_name)}</strong>
                  </div>
                  <b>
                    {claim.observed.toFixed(3)}{" "}
                    <em>
                      {claim.comparator} {claim.threshold}
                    </em>
                  </b>
                  <p>{claim.limitation}</p>
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
            <CircleAlert size={14} /> EVALUATION-ONLY NEGATIVE CONTROL
          </span>
          <h3>Beautiful enough to tempt. Invalid enough to reject.</h3>
        </div>
        <strong>REJECTED · HARD GATE</strong>
      </div>
      <div className="negative-control-grid">
        <div className="negative-control-image">
          <img
            src={imageUrl}
            alt="Attractive but constraint-invalid negative control"
          />
          <span>NOT A PRODUCTION CANDIDATE</span>
        </div>
        <div className="negative-control-evidence">
          <div className="appeal-vs-policy">
            <div>
              <small>MULTIMODAL AESTHETIC</small>
              <strong>
                PASS · {Math.round((aesthetic?.confidence ?? 0) * 100)}%
              </strong>
            </div>
            <ArrowRight size={18} />
            <div>
              <small>DETERMINISTIC ELIGIBILITY</small>
              <strong>FAIL · PRECEDENCE</strong>
            </div>
          </div>
          <div className="negative-metrics">
            <Fact
              label="Aspect drift"
              value={`${aspect?.observed.toFixed(3)} > ${aspect?.threshold}`}
              mono
            />
            <Fact
              label="Edge-layout proxy"
              value={`${layout?.observed.toFixed(3)} < ${layout?.threshold}`}
              mono
            />
            <Fact label="Artifact" value={shortId(artifact.sha256)} mono />
            <Fact label="Critic reasoning" value="excluded" />
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
                  {claim.observation}
                </p>
              ))}
          </div>
          <div className="hard-precedence">
            <ShieldCheck size={14} />
            <p>
              <strong>Aesthetic confidence cannot override eligibility.</strong>{" "}
              This control is permanently isolated; the later production
              decision can select only an eligible lane.
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
            <ScanLine size={14} /> FROZEN AGENT HARNESS · 飞行记录仪
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
            <i>PASS</i>
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
              <Workflow size={14} /> MATCHED PROVIDER RUN
            </span>
            <h2>One scene. Two sealed execution lanes.</h2>
            <p>
              The visual brief is shared; identity, authority and recovery never
              are.
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
          <span>SCENE CONSTRAINT PACKAGE</span>
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
                  {isLocal ? "A / LOCAL" : "B / HOSTED"}
                </div>
                <div className="provider-mark">
                  {isLocal ? <HardDrive size={21} /> : <Cloud size={21} />}
                </div>
                <div className="provider-copy">
                  <small>
                    {isLocal ? "PRIVATE GPU ROUTE" : "METERED IMAGE EDIT"}
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
                    <small>SEPARATE AUTHORITY</small>
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
            <span>HOSTED ESTIMATE</span>
            <strong>${preview.estimated_hosted_cost_usd.toFixed(2)}</strong>
            <small>
              ${preview.maximum_hosted_cost_usd.toFixed(2)} owner ceiling
            </small>
          </div>
          <div>
            <ShieldCheck size={16} />
            <span>REMOTE ALLOWLIST</span>
            <strong>{preview.hosted_uploads.join(" + ")}</strong>
            <small>evaluation passes stay local</small>
          </div>
          <div>
            <Fingerprint size={16} />
            <span>PRIVACY POSTURE</span>
            <strong>{pretty(preview.hosted_privacy_class)}</strong>
            <small>cost cap not provider-enforced</small>
          </div>
        </div>
        <div className="launch-truth">
          <CircleAlert size={15} />
          <p>
            <strong>No winner has been chosen.</strong>
            {agent.comparison_manifest
              ? ` The persisted comparison is ${pretty(agent.comparison_manifest.status)}.`
              : authorized
                ? " Approval is recorded; execution remains a separate one-use action."
                : " Opening this review does not authorize either provider."}
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
          <Workflow size={14} /> AGENT PULSE
        </span>
        <small>REPLAYED, NOT INFERRED</small>
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
              <strong>{item.label}</strong>
              <p>{item.detail}</p>
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
            <Eye size={13} /> SOURCE / CANDIDATE COMPARE
          </span>
          <span>READ ONLY · NO SELECTION RECORDED</span>
        </div>
        <div className="comparison-stage">
          <img
            className="compare-source"
            src={`/api/runs/${run.run_id}/source`}
            alt="Source composition"
          />
          <div
            className="compare-candidate"
            style={{ clipPath: `inset(0 ${100 - split}% 0 0)` }}
          >
            <img src={candidateUrl} alt={active.direction.visual_goal} />
          </div>
          <span className="compare-label source">SOURCE</span>
          <span className="compare-label result">CANDIDATE</span>
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
            aria-label="Source and candidate comparison split"
          />
          <span>B</span>
          <strong>{split}% candidate</strong>
        </div>
      </section>
      <section className="direction-switcher">
        <div className="river-head">
          <span>
            <Layers3 size={14} /> CAPTURED DIRECTIONS
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
                <em>{index === activeIndex ? "ON STAGE" : "COMPARE"}</em>
              </div>
            </button>
          ))}
        </div>
        <div className="comparison-truth">
          <CircleAlert size={14} />
          <p>
            <strong>Human selection is still open.</strong>This historical run
            remains in review; changing the comparison does not adopt a
            candidate.
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
            <span>DUAL PROVIDER CONTROL</span>
            <strong>
              {agent.comparison_manifest
                ? pretty(agent.comparison_manifest.status)
                : agent.comparison_authorization
                  ? "authorized"
                  : "awaiting owner"}
            </strong>
          </div>
          <InspectorSection label="Hosted consequence">
            <Fact label="Endpoint" value={preview.hosted_endpoint} mono />
            <Fact label="Model" value={preview.hosted_model} mono />
            <Fact label="Upload" value={preview.hosted_uploads.join(", ")} />
            <Fact
              label="Estimate / max"
              value={`$${preview.estimated_hosted_cost_usd.toFixed(2)} / $${preview.maximum_hosted_cost_usd.toFixed(2)}`}
            />
            <Fact
              label="Retention"
              value={pretty(preview.hosted_privacy_class)}
            />
          </InspectorSection>
          <InspectorSection label="Unresolved facts">
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
            <p>{capability.verification_signal}</p>
            <small>
              {capability.authority.writes.length
                ? `${capability.authority.writes.length} 个写入域`
                : "只读"}{" "}
              · {capability.availability}
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
        <span>LEGACY EVIDENCE</span>
        <p>
          This real RTX 4080 run is preserved as recorded. It is not presented
          as an event-sourced Agent run.
        </p>
      </div>
      <ConstraintList
        label="Must preserve"
        values={run.brief.preserve}
        tone="keep"
      />
      <ConstraintList label="Avoid" values={run.brief.avoid} tone="block" />
      <InspectorSection label="Runtime facts">
        <Fact label="Run" value={shortId(run.run_id)} mono />
        <Fact label="Task" value={pretty(run.brief.task_type)} />
        <Fact
          label="ComfyUI"
          value={health?.reachable ? "reachable" : "offline"}
        />
        <Fact label="Candidates" value={String(run.candidates.length)} />
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
function ComparisonApprovalSheet({
  decision,
  plan,
  busy,
  onAuthorize,
}: {
  decision: AgentProjection["pending_decisions"][number];
  plan: ComparisonPlan;
  busy: boolean;
  onAuthorize: (approvedBy: string) => Promise<void>;
}) {
  const [approvedBy, setApprovedBy] = useState("");
  const preview = plan.operator_preview;
  return (
    <div className="approval-scrim comparison-scrim" role="presentation">
      <section
        className="approval-sheet comparison-approval"
        role="dialog"
        aria-modal="true"
        aria-labelledby="comparison-approval-title"
      >
        <div className="approval-signal">
          <span>HUMAN OWNER / DUAL AUTHORITY</span>
          <i />
        </div>
        <div className="approval-title">
          <div>
            <LockKeyhole size={22} />
            <span>EXTERNAL SIDE-EFFECT REVIEW</span>
          </div>
          <h2 id="comparison-approval-title">
            Two actions. One exact fingerprint.
          </h2>
          <p>{decision.summary}</p>
        </div>
        <div className="approval-lanes">
          <div>
            <HardDrive size={18} />
            <span>LOCAL GPU</span>
            <strong>ComfyUI · {preview.local_uploads.join(", ")}</strong>
            <small>One reviewed workflow · one output</small>
          </div>
          <div>
            <Cloud size={18} />
            <span>HOSTED / METERED</span>
            <strong>
              OpenAI · ${preview.estimated_hosted_cost_usd.toFixed(2)} est.
            </strong>
            <small>
              {pretty(preview.hosted_privacy_class)} · $
              {preview.maximum_hosted_cost_usd.toFixed(2)} max
            </small>
          </div>
        </div>
        <div className="approval-facts">
          <Fact
            label="Output"
            value={`${preview.output_count_per_provider} each · ${preview.output_size}`}
          />
          <Fact
            label="Remote upload"
            value={preview.hosted_uploads.join(", ")}
          />
          <Fact label="Endpoint" value={preview.hosted_endpoint} mono />
          <Fact
            label="Fingerprint"
            value={
              decision.fingerprint ? shortId(decision.fingerprint) : "missing"
            }
            mono
          />
        </div>
        <label className="owner-field">
          <span>Human owner identity</span>
          <input
            value={approvedBy}
            onChange={(event) => setApprovedBy(event.target.value)}
            placeholder="Your name or review handle"
            autoComplete="name"
          />
          <small>
            This value is persisted with the authorization event. The Agent
            cannot fill it for you.
          </small>
        </label>
        <div className="approval-note">
          <CircleAlert size={14} />
          <p>
            Approval records both exact action scopes. It does not start either
            provider, authorize Unreal return, or select a winner.
          </p>
        </div>
        <div className="approval-actions">
          <button
            className="approve-command"
            disabled={busy || !approvedBy.trim()}
            onClick={() => void onAuthorize(approvedBy.trim())}
          >
            <Check size={15} />
            {busy ? "Binding decision…" : "Authorize both exact actions"}
          </button>
        </div>
      </section>
    </div>
  );
}
function ApprovalSheet({
  decision,
  route,
  busy,
  onResolve,
}: {
  decision: AgentProjection["pending_decisions"][number];
  route: AgentProjection["route"];
  busy: boolean;
  onResolve: (
    decisionId: string,
    resolution: "approved" | "rejected",
  ) => Promise<void>;
}) {
  return (
    <div className="approval-scrim" role="presentation">
      <section
        className="approval-sheet"
        role="dialog"
        aria-modal="true"
        aria-labelledby="approval-title"
      >
        <div className="approval-signal">
          <span>HUMAN INTERRUPT</span>
          <i />
        </div>
        <div className="approval-title">
          <div>
            <ShieldCheck size={22} />
            <span>ROUTE / APPROVAL</span>
          </div>
          <h2 id="approval-title">The Agent is waiting at the boundary.</h2>
          <p>{decision.summary}</p>
        </div>
        <div className="approval-facts">
          <Fact label="Decision" value={decision.decision_id} mono />
          <Fact
            label="Fingerprint"
            value={
              decision.fingerprint
                ? shortId(decision.fingerprint)
                : "not supplied"
            }
            mono
          />
          {route ? (
            <>
              <Fact
                label="Provider / model"
                value={`${route.provider_id} / ${route.model_id}`}
                mono
              />
              <Fact label="Privacy" value={pretty(route.privacy_class)} />
              <Fact
                label="Cost ceiling"
                value={`$${route.max_cost_usd.toFixed(2)}`}
              />
              <Fact
                label="Controls"
                value={route.required_controls.join(", ")}
              />
            </>
          ) : (
            <>
              <Fact label="Authority" value="Human only" />
              <Fact label="State effect" value="Append event" />
            </>
          )}
        </div>
        <div className="approval-note">
          <CircleAlert size={14} />
          <p>
            This action records only your decision. It does not start GPU work,
            call a provider or adopt an output.
          </p>
        </div>
        <div className="approval-actions">
          <button
            className="reject-command"
            disabled={busy}
            onClick={() => void onResolve(decision.decision_id, "rejected")}
          >
            Reject route
          </button>
          <button
            className="approve-command"
            disabled={busy}
            onClick={() => void onResolve(decision.decision_id, "approved")}
          >
            <Check size={15} />
            {busy ? "Recording…" : "Approve this fingerprint"}
          </button>
        </div>
      </section>
    </div>
  );
}
