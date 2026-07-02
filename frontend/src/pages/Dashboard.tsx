import { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { apiFetch, RunSummary } from "../api";
import { useAuth } from "../auth";

const statusClass = (s: string) => `badge badge-${s}`;

export default function Dashboard() {
  const { token } = useAuth();
  const [runs, setRuns] = useState<RunSummary[]>([]);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let active = true;
    const load = async () => {
      try {
        const data = await apiFetch<RunSummary[]>("/runs", token);
        if (active) setRuns(data);
      } catch (e) {
        if (active) setError(String(e));
      }
    };
    load();
    const id = setInterval(load, 2000);
    return () => {
      active = false;
      clearInterval(id);
    };
  }, [token]);

  return (
    <div className="card">
      <div className="row-between">
        <h2>My workflow runs</h2>
        <Link className="primary link-btn" to="/submit">
          + New workflow
        </Link>
      </div>
      {error && <p className="error">{error}</p>}
      <table>
        <thead>
          <tr>
            <th>Name</th>
            <th>Status</th>
            <th>Submitted by</th>
            <th>Created</th>
            <th>Steps</th>
          </tr>
        </thead>
        <tbody>
          {runs.map((run) => (
            <tr key={run.id}>
              <td>
                <Link to={`/runs/${run.id}`}>{run.name}</Link>
                <div className="mono small">{run.id.slice(0, 8)}</div>
              </td>
              <td>
                <span className={statusClass(run.status)}>{run.status}</span>
              </td>
              <td>{run.submitted_by}</td>
              <td>{new Date(run.created_at).toLocaleString()}</td>
              <td>{Object.values(run.step_counts).reduce((a, b) => a + b, 0)}</td>
            </tr>
          ))}
          {runs.length === 0 && (
            <tr>
              <td colSpan={5}>No runs yet. Submit a workflow to get started.</td>
            </tr>
          )}
        </tbody>
      </table>
    </div>
  );
}
