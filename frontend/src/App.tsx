import { Link, Navigate, Route, Routes } from "react-router-dom";
import { useAuth } from "./auth";
import Dashboard from "./pages/Dashboard";
import RunDetail from "./pages/RunDetail";
import Submit from "./pages/Submit";
import Login from "./pages/Login";

export default function App() {
  const { token, username, logout, ready } = useAuth();

  if (!ready) return <div className="loading">Loading...</div>;

  return (
    <div className="app">
      <header className="header">
        <div>
          <h1>Workflow Engine</h1>
          <p className="subtitle">Async DAG execution demo</p>
        </div>
        <nav>
          {token ? (
            <>
              <Link to="/">Runs</Link>
              <Link to="/submit">Submit</Link>
              <span className="user">{username}</span>
              <button type="button" onClick={logout}>
                Logout
              </button>
            </>
          ) : (
            <Link to="/login">Login</Link>
          )}
        </nav>
      </header>
      <main>
        <Routes>
          <Route path="/login" element={token ? <Navigate to="/" /> : <Login />} />
          <Route path="/" element={token ? <Dashboard /> : <Navigate to="/login" />} />
          <Route path="/submit" element={token ? <Submit /> : <Navigate to="/login" />} />
          <Route path="/runs/:id" element={token ? <RunDetail /> : <Navigate to="/login" />} />
        </Routes>
      </main>
    </div>
  );
}
