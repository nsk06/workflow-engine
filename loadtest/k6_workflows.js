import http from "k6/http";
import { check, sleep } from "k6";

export const options = {
  vus: 100,
  duration: "30s",
};

const API = __ENV.API_URL || "http://localhost:18700";

export function setup() {
  const login = http.post(
    `${API}/auth/login`,
    JSON.stringify({ username: "demo", password: "demo" }),
    { headers: { "Content-Type": "application/json" } }
  );
  return { token: login.json("access_token") };
}

export default function (data) {
  const headers = {
    "Content-Type": "application/json",
    Authorization: `Bearer ${data.token}`,
  };
  const res = http.post(`${API}/runs`, JSON.stringify({ preset: "linear" }), { headers });
  check(res, { "submit 202": (r) => r.status === 202 });
  sleep(0.1);
}
