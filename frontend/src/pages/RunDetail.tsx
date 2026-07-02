import { useEffect, useState } from "react";
import { Link, useParams } from "react-router-dom";
import { apiFetch, type RunDetail, type Step } from "../api";
import { useAuth } from "../auth";

function StepTimeline({ steps }: { steps: Step[] }) {
  const order = topologicalSteps(steps);
  return (
    <div className="timeline">
      {order.map((step) => (
        <div key={step.id} className={`timeline-item status-${step.status}`}>
          <div className="timeline-marker" />
          <div className="timeline-body">
            <div className="row-between">
              <strong>{step.step_key}</strong>
              <span className={`badge badge-${step.status}`}>{step.status}</span>
            </div>
            <div className="meta">
              type: {step.step_type}
              {step.depends_on.length > 0 && <> · deps: {step.depends_on.join(", ")}</>}
              {step.attempt > 0 && <> · attempts: {step.attempt}</>}
            </div>
            {step.error && <p className="error small">{step.error}</p>}
            {step.output && (
              <pre className="output">{JSON.stringify(step.output, null, 2)}</pre>
            )}
          </div>
        </div>
      ))}
    </div>
  );
}

function topologicalSteps(steps: Step[]): Step[] {
  const byKey = Object.fromEntries(steps.map((s) => [s.step_key, s]));
  const visited = new Set<string>();
  const result: Step[] = [];

  const visit = (key: string) => {
    if (visited.has(key)) return;
    const step = byKey[key];
    if (!step) return;
    step.depends_on.forEach(visit);
    visited.add(key);
    result.push(step);
  };

  steps.forEach((s) => visit(s.step_key));
  return result;
}

export default function RunDetail() {
  const { id } = useParams();
  const { token } = useAuth();
  const [run, setRun] = useState<RunDetail | null>(null);
  const [error, setError] = useState<string | null>(null);

  const load = async () => {
    if (!id) return;
    try {
      const data = await apiFetch<RunDetail>(`/runs/${id}`, token);
      setRun(data);
    } catch (e) {
      setError(String(e));
    }
  };

  useEffect(() => {
    load();
    const timer = setInterval(load, 1500);
    return () => clearInterval(timer);
  }, [id, token]);

  const cancel = async () => {
    if (!id) return;
    await apiFetch(`/runs/${id}/cancel`, token, { method: "POST" });
    load();
  };

  if (error) return <p className="error">{error}</p>;
  if (!run) return <div className="loading">Loading run...</div>;

  const canCancel = !["completed", "failed", "cancelled"].includes(run.status);

  return (
    <div className="card">
      <div className="row-between">
        <div>
          <Link to="/">← Back</Link>
          <h2>{run.name}</h2>
          <p className="mono small">{run.id}</p>
        </div>
        <div className="actions">
          <span className={`badge badge-${run.status}`}>{run.status}</span>
          {canCancel && (
            <button type="button" className="danger" onClick={cancel}>
              Cancel
            </button>
          )}
        </div>
      </div>
      <div className="meta-grid">
        <div>
          <label>Submitted by</label>
          <div>{run.submitted_by}</div>
        </div>
        <div>
          <label>Created</label>
          <div>{new Date(run.created_at).toLocaleString()}</div>
        </div>
        <div>
          <label>Updated</label>
          <div>{new Date(run.updated_at).toLocaleString()}</div>
        </div>
      </div>
      <h3>Step timeline</h3>
      <StepTimeline steps={run.steps} />
    </div>
  );
}
