const API_BASE = import.meta.env.VITE_API_URL || "/api";
const TOKEN_KEY = "workflow_token";
const USER_KEY = "workflow_user";

export { API_BASE, TOKEN_KEY, USER_KEY };

export interface RunSummary {
  id: string;
  name: string;
  status: string;
  submitted_by: string;
  created_at: string;
  updated_at: string;
  step_counts: Record<string, number>;
}

export interface Step {
  id: string;
  step_key: string;
  status: string;
  step_type: string;
  depends_on: string[];
  config: Record<string, unknown>;
  input: Record<string, unknown>;
  output: Record<string, unknown> | null;
  attempt: number;
  error: string | null;
  started_at: string | null;
  completed_at: string | null;
}

export interface RunDetail {
  id: string;
  name: string;
  status: string;
  submitted_by: string;
  input: Record<string, unknown>;
  output: Record<string, unknown> | null;
  definition: Record<string, unknown>;
  created_at: string;
  updated_at: string;
  cancelled_at: string | null;
  steps: Step[];
}

export interface Preset {
  id: string;
  name: string;
  steps: number;
}

export function getStoredToken(): string | null {
  return localStorage.getItem(TOKEN_KEY);
}

export function getStoredUser(): string | null {
  return localStorage.getItem(USER_KEY);
}

export function storeSession(token: string, username: string) {
  localStorage.setItem(TOKEN_KEY, token);
  localStorage.setItem(USER_KEY, username);
}

export function clearSession() {
  localStorage.removeItem(TOKEN_KEY);
  localStorage.removeItem(USER_KEY);
}

export async function login(username: string, password: string): Promise<string> {
  const res = await fetch(`${API_BASE}/auth/login`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ username, password }),
  });
  if (!res.ok) {
    const text = await res.text();
    throw new Error(text || "Login failed");
  }
  const data = await res.json();
  storeSession(data.access_token, data.username);
  return data.access_token;
}

export async function apiFetch<T>(path: string, token: string | null, options: RequestInit = {}): Promise<T> {
  const headers: Record<string, string> = {
    "Content-Type": "application/json",
    ...(options.headers as Record<string, string>),
  };
  if (token) headers.Authorization = `Bearer ${token}`;
  const res = await fetch(`${API_BASE}${path}`, { ...options, headers });
  if (res.status === 401) {
    clearSession();
    throw new Error("Session expired — please log in again");
  }
  if (!res.ok) {
    const text = await res.text();
    throw new Error(text || res.statusText);
  }
  return res.json();
}
