import { useEffect, useState } from "react";
import { Link, useNavigate } from "react-router-dom";
import { apiFetch, Preset } from "../api";
import { useAuth } from "../auth";

export default function Submit() {
  const { token } = useAuth();
  const navigate = useNavigate();
  const [presets, setPresets] = useState<Preset[]>([]);
  const [selected, setSelected] = useState("fanout");
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    apiFetch<Preset[]>("/presets", token).then(setPresets).catch((e) => setError(String(e)));
  }, [token]);

  const submit = async () => {
    setLoading(true);
    setError(null);
    try {
      const res = await apiFetch<{ run_id: string }>("/runs", token, {
        method: "POST",
        body: JSON.stringify({ preset: selected }),
      });
      navigate(`/runs/${res.run_id}`);
    } catch (e) {
      setError(String(e));
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="card">
      <h2>Submit workflow</h2>
      <p>Choose a preset DAG and submit. Workers execute steps asynchronously.</p>
      {error && <p className="error">{error}</p>}
      <div className="preset-grid">
        {presets.map((p) => (
          <label key={p.id} className={`preset ${selected === p.id ? "selected" : ""}`}>
            <input
              type="radio"
              name="preset"
              value={p.id}
              checked={selected === p.id}
              onChange={() => setSelected(p.id)}
            />
            <strong>{p.name}</strong>
            <span>{p.steps} steps</span>
            <span className="mono">{p.id}</span>
          </label>
        ))}
      </div>
      <div className="actions">
        <button type="button" className="primary" disabled={loading} onClick={submit}>
          {loading ? "Submitting..." : "Submit workflow"}
        </button>
        <Link to="/">Cancel</Link>
      </div>
    </div>
  );
}
