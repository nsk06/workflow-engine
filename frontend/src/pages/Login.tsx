import { FormEvent, useState } from "react";
import { useNavigate } from "react-router-dom";
import { useAuth } from "../auth";

const DEMO_ACCOUNTS = [
  { username: "demo", password: "demo", label: "demo" },
  { username: "alice", password: "alice", label: "alice" },
  { username: "bob", password: "bob", label: "bob" },
] as const;

export default function Login() {
  const { login } = useAuth();
  const navigate = useNavigate();
  const [username, setUsername] = useState("demo");
  const [password, setPassword] = useState("demo");
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);

  const doLogin = async (user: string, pass: string) => {
    setLoading(true);
    setError(null);
    try {
      await login(user, pass);
      navigate("/");
    } catch (err) {
      setError(String(err));
    } finally {
      setLoading(false);
    }
  };

  const onSubmit = async (e: FormEvent) => {
    e.preventDefault();
    await doLogin(username, password);
  };

  return (
    <div className="card login-card">
      <h2>Sign in</h2>
      <p>Log in to submit workflows. You will only see your own runs.</p>
      <form onSubmit={onSubmit} className="login-form">
        <label>
          Username
          <input
            type="text"
            value={username}
            onChange={(e) => setUsername(e.target.value)}
            autoComplete="username"
            required
          />
        </label>
        <label>
          Password
          <input
            type="password"
            value={password}
            onChange={(e) => setPassword(e.target.value)}
            autoComplete="current-password"
            required
          />
        </label>
        {error && <p className="error">{error}</p>}
        <button type="submit" className="primary" disabled={loading}>
          {loading ? "Signing in..." : "Sign in"}
        </button>
      </form>
      <div className="demo-users">
        <p className="hint">Quick login (password = username):</p>
        <div className="demo-user-buttons">
          {DEMO_ACCOUNTS.map((acct) => (
            <button
              key={acct.username}
              type="button"
              className="secondary"
              disabled={loading}
              onClick={() => {
                setUsername(acct.username);
                setPassword(acct.password);
                void doLogin(acct.username, acct.password);
              }}
            >
              {acct.label}
            </button>
          ))}
        </div>
      </div>
    </div>
  );
}
