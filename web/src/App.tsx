import {
  Activity,
  Check,
  ChevronRight,
  CircleAlert,
  Cpu,
  Image as ImageIcon,
  Layers3,
  Play,
  RefreshCw,
  ShieldCheck,
  Sparkles,
} from "lucide-react";
import { useCallback, useEffect, useMemo, useState } from "react";

type RunStatus =
  | "awaiting_approval"
  | "approved"
  | "running"
  | "review"
  | "completed"
  | "failed";

type DirectionRun = {
  direction_name: string;
  status: "pending" | "running" | "completed" | "failed";
  attempt_count: number;
  error: string | null;
};

type Candidate = {
  candidate_id: string;
  direction_name: string;
};

type RunState = {
  run_id: string;
  status: RunStatus;
  created_at: string;
  selected_candidate_id: string | null;
  parent_run_id: string | null;
  source_candidate_id: string | null;
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
  direction_runs: DirectionRun[];
  candidates: Candidate[];
};

type Health = {
  reachable: boolean;
  vram_mb: number | null;
  node_count: number;
  model_inventory: Record<string, string[]>;
};

type Job = { active: boolean; error: string | null };

const statusLabel: Record<RunStatus, string> = {
  awaiting_approval: "Approval required",
  approved: "Approved",
  running: "Generating",
  review: "Human review",
  completed: "Completed",
  failed: "Failed",
};

async function request<T>(url: string, init?: RequestInit): Promise<T> {
  const response = await fetch(url, init);
  if (!response.ok) {
    const payload = await response.json().catch(() => ({ detail: response.statusText }));
    throw new Error(payload.detail ?? "Request failed");
  }
  return response.json();
}

export default function App() {
  const [runs, setRuns] = useState<RunState[]>([]);
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const [run, setRun] = useState<RunState | null>(null);
  const [health, setHealth] = useState<Health | null>(null);
  const [job, setJob] = useState<Job | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const refresh = useCallback(async () => {
    const [nextRuns, nextHealth] = await Promise.all([
      request<RunState[]>("/api/runs"),
      request<Health>("/api/health"),
    ]);
    setRuns(nextRuns);
    setHealth(nextHealth);
    const nextId = selectedId ?? nextRuns[0]?.run_id ?? null;
    if (nextId) {
      setSelectedId(nextId);
      const [nextRun, nextJob] = await Promise.all([
        request<RunState>(`/api/runs/${nextId}`),
        request<Job>(`/api/runs/${nextId}/job`),
      ]);
      setRun(nextRun);
      setJob(nextJob);
    }
  }, [selectedId]);

  const refreshSelected = useCallback(async () => {
    if (!selectedId) return;
    const [nextRun, nextJob] = await Promise.all([
      request<RunState>(`/api/runs/${selectedId}`),
      request<Job>(`/api/runs/${selectedId}/job`),
    ]);
    setRun(nextRun);
    setJob(nextJob);
  }, [selectedId]);

  useEffect(() => {
    refresh().catch((reason) => setError(String(reason)));
  }, [refresh]);

  useEffect(() => {
    if (!job?.active && run?.status !== "running") return;
    const timer = window.setInterval(() => refreshSelected().catch(() => undefined), 1800);
    return () => window.clearInterval(timer);
  }, [job?.active, run?.status, refreshSelected]);

  const act = async (action: () => Promise<unknown>) => {
    setBusy(true);
    setError(null);
    try {
      await action();
      await refresh();
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : String(reason));
    } finally {
      setBusy(false);
    }
  };

  const selectRun = async (runId: string) => {
    setSelectedId(runId);
    setRun(await request<RunState>(`/api/runs/${runId}`));
    setJob(await request<Job>(`/api/runs/${runId}/job`));
  };

  const completedDirections = run?.direction_runs.filter((item) => item.status === "completed").length ?? 0;
  const progress = run?.direction_runs.length
    ? Math.round((completedDirections / run.direction_runs.length) * 100)
    : 0;
  const action = useMemo(() => {
    if (!run) return null;
    if (run.status === "awaiting_approval") {
      return {
        label: "Approve plan",
        icon: ShieldCheck,
        run: () => request(`/api/runs/${run.run_id}/approve`, { method: "POST" }),
      };
    }
    if (run.status === "approved" || run.status === "running") {
      return {
        label: job?.active ? "Generation in progress" : "Run approved directions",
        icon: Play,
        disabled: job?.active,
        run: () =>
          request(`/api/runs/${run.run_id}/execute`, {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: "{}",
          }),
      };
    }
    if (run.status === "review") {
      return {
        label: "Build contact sheet",
        icon: Layers3,
        run: () => request(`/api/runs/${run.run_id}/contact-sheet`, { method: "POST" }),
      };
    }
    return null;
  }, [run, job?.active]);

  return (
    <div className="app-shell">
      <header className="topbar">
        <div className="identity">
          <div className="mark"><Sparkles size={16} /></div>
          <div><strong>ArtFlow</strong><span>Agent workbench</span></div>
        </div>
        <div className="runtime">
          <span className={health?.reachable ? "runtime-dot online" : "runtime-dot"} />
          <Cpu size={15} />
          <span>{health?.reachable ? `ComfyUI · ${Math.round((health.vram_mb ?? 0) / 1024)} GB VRAM` : "Runtime offline"}</span>
          <button className="icon-button" onClick={() => refresh()} aria-label="Refresh"><RefreshCw size={15} /></button>
        </div>
      </header>

      <aside className="run-rail">
        <div className="rail-heading"><span>Runs</span><span>{runs.length}</span></div>
        <nav aria-label="ArtFlow runs">
          {runs.map((item) => (
            <button
              key={item.run_id}
              className={`run-row ${item.run_id === selectedId ? "selected" : ""}`}
              onClick={() => selectRun(item.run_id)}
            >
              <span className={`status-pin status-${item.status}`} />
              <span><strong>{item.brief.project_name}</strong><small>{item.run_id} · {statusLabel[item.status]}</small></span>
              <ChevronRight size={15} />
            </button>
          ))}
        </nav>
      </aside>

      <main className="workspace">
        {run ? (
          <>
            <section className="context-line">
              <div><span className="eyebrow">Current brief</span><h1>{run.brief.project_name}</h1><p>{run.brief.intent}</p></div>
              <div className={`status-chip status-${run.status}`}><Activity size={14} />{statusLabel[run.status]}</div>
            </section>

            <section className="stage-track" aria-label="Run stages">
              <Stage index="01" label="Plan" active completed />
              <div className="stage-rule" />
              <Stage index="02" label="Generate" active={run.status === "running" || run.status === "approved"} completed={["review", "completed"].includes(run.status)} />
              <div className="stage-rule" />
              <Stage index="03" label="Review" active={run.status === "review"} completed={run.status === "completed"} />
            </section>

            <section className="visual-workspace">
              <div className="source-frame">
                <div className="frame-label"><ImageIcon size={14} /> Source composition</div>
                <img src={`/api/runs/${run.run_id}/source`} alt="Source composition" />
                <div className="composition-lock"><ShieldCheck size={14} /> Composition locked</div>
              </div>

              <div className="direction-field">
                <div className="field-header"><span>Directed variants</span><span>{completedDirections}/{run.direction_runs.length} complete</span></div>
                <div className="progress-line"><span style={{ width: `${progress}%` }} /></div>
                <div className="direction-grid">
                  {run.plan.directions.map((direction, index) => {
                    const state = run.direction_runs.find((item) => item.direction_name === direction.name);
                    const candidate = run.candidates.find((item) => item.direction_name === direction.name);
                    return (
                      <article key={direction.name} className={`direction-lane lane-${state?.status ?? "pending"}`}>
                        <div className="lane-top"><span>0{index + 1}</span><DirectionState status={state?.status ?? "pending"} /></div>
                        {candidate ? (
                          <img src={`/api/runs/${run.run_id}/candidates/${candidate.candidate_id}`} alt={direction.visual_goal} />
                        ) : (
                          <div className="lane-placeholder"><Sparkles size={20} /><span>Awaiting approved generation</span></div>
                        )}
                        <div className="lane-copy"><h2>{direction.visual_goal}</h2><p>{direction.prompt_delta}</p><code>{direction.recipe_id}</code></div>
                        {candidate && run.status === "review" && (
                          <button className="select-button" onClick={() => act(() => request(`/api/runs/${run.run_id}/select/${candidate.candidate_id}`, { method: "POST" }))}>Select this direction</button>
                        )}
                        {run.selected_candidate_id === candidate?.candidate_id && <div className="selected-stamp"><Check size={14} /> Selected</div>}
                      </article>
                    );
                  })}
                </div>
              </div>
            </section>
          </>
        ) : <div className="empty-state">No run state found.</div>}
      </main>

      <aside className="inspector">
        {run && <>
          <div className="inspector-title"><span>Run inspector</span><code>{run.run_id}</code></div>
          <InspectorGroup title="Preserve" tone="positive" items={run.brief.preserve} />
          <InspectorGroup title="Prohibited" tone="negative" items={run.brief.avoid} />
          {run.parent_run_id && <div className="evidence-block"><h3>Revision lineage</h3><dl><div><dt>Parent run</dt><dd>{run.parent_run_id}</dd></div><div><dt>Selected source</dt><dd>{run.source_candidate_id}</dd></div></dl><button className="lineage-link" onClick={() => selectRun(run.parent_run_id!)}>Open parent run <ChevronRight size={13} /></button></div>}
          <div className="evidence-block"><h3>Runtime evidence</h3><dl><div><dt>Nodes</dt><dd>{health?.node_count ?? "—"}</dd></div><div><dt>Diffusion</dt><dd>{health?.model_inventory.diffusion_models?.length ?? 0}</dd></div><div><dt>Task</dt><dd>{run.brief.task_type.replaceAll("_", " ")}</dd></div></dl></div>
          {(error || job?.error) && <div className="error-box"><CircleAlert size={16} /><span>{error ?? job?.error}</span></div>}
        </>}
      </aside>

      <footer className="actionbar">
        <div><strong>{run ? statusLabel[run.status] : "No active run"}</strong><span>{run?.status === "awaiting_approval" ? "GPU work is blocked until you approve this exact plan." : "Every generation is recorded with its recipe, seed and workflow hash."}</span></div>
        {action && <button className="primary-action" disabled={busy || action.disabled} onClick={() => act(action.run)}><action.icon size={16} />{busy ? "Working…" : action.label}</button>}
      </footer>
    </div>
  );
}

function Stage({ index, label, active = false, completed = false }: { index: string; label: string; active?: boolean; completed?: boolean }) {
  return <div className={`stage ${active ? "active" : ""} ${completed ? "completed" : ""}`}><span>{completed ? <Check size={13} /> : index}</span><strong>{label}</strong></div>;
}

function DirectionState({ status }: { status: DirectionRun["status"] }) {
  return <span className={`direction-state state-${status}`}>{status === "completed" && <Check size={12} />}{status}</span>;
}

function InspectorGroup({ title, items, tone }: { title: string; items: string[]; tone: "positive" | "negative" }) {
  return <section className="inspector-group"><h3>{title}</h3><ul>{items.map((item) => <li key={item} className={tone}><span>{tone === "positive" ? "+" : "−"}</span>{item}</li>)}</ul></section>;
}
