# Workflow Engine — Design & Operations

Principal-engineer interview demo: async DAG workflow execution with multi-user auth, observability, and a scaling story.

---

## 1. How I designed it

### Problem framing

Build a system that accepts DAG workflows, executes steps asynchronously with retries, survives worker crashes, and gives operators visibility into backlog and latency — without requiring a full cloud stack for local demo.

### Architecture

See [ARCHITECTURE.md](docs/ARCHITECTURE.md) for Mermaid diagrams (system, deploy, submit flow, auth, DAG fanout) and how topological sort vs runtime scheduling differ.

```
Browser → React UI → FastAPI API → SQLite (runs + steps + queue)
                         ↑
              Worker(s) poll with SKIP LOCKED leasing
                         ↓
         Prometheus metrics + OTel traces → Grafana / Jaeger
```

### Key design decisions

| Decision | Rationale |
|----------|-----------|
| **API / worker split** | Submit returns immediately (202); workers scale independently; API stays responsive under load. |
| **SQLite as queue + state** | Zero external dependencies for demo. `FOR UPDATE SKIP LOCKED` gives safe concurrent step claiming. |
| **Row leasing + reaper** | Workers set `leased_until`; expired leases are reclaimed so crashed pods don't lose work. |
| **DAG in application layer** | All steps created on submit; scheduler marks dependents runnable when deps complete. No workflow engine framework — keeps code readable. |
| **JWT auth + row ownership** | `submitted_by` on every run; API filters list/detail/cancel by JWT `sub`. Simple, auditable, no IdP dependency. |
| **Per-user metric labels** | `user` label on counters/histograms so Grafana can show isolation and saturation per tenant. |
| **Presets over arbitrary DAGs** | `linear`, `fanout`, `flaky` demonstrate pipeline, parallelism, and retry without a DAG editor. |

### Step handlers

- `sleep` — simulated work (configurable `duration_ms`)
- `transform` — pure function steps (validate, enrich, aggregate)
- `flaky` — transient failures with exponential backoff (max 5 attempts)

### What I intentionally did *not* build

- External message queue (SQS/Kafka) — documented as production path
- Postgres — SQLite is the deliberate ceiling for the scaling narrative
- Human-in-the-loop / callbacks — out of scope

---

## 2. How I observe the system

### Three signals

| Signal | Tool | What to look at |
|--------|------|-----------------|
| **Metrics** | Prometheus → Grafana | `workflow_pending_steps`, `workflow_runs_submitted_total{user}`, `rate(workflow_steps_executed_total)`, step duration p95 |
| **Traces** | OTel Collector → Jaeger | Spans: `submit_run`, `execute_step` with `user`, `run_id`, `step_key` |
| **Logs** | structlog JSON on stdout | `run_submitted`, `step_completed`, `step_retry` with `run_id` |

### Demo URLs (docker compose, ports in `.env.ports`)

| Service | URL |
|---------|-----|
| UI | http://localhost:18780 |
| API docs | http://localhost:18700/docs |
| Grafana | http://localhost:18701/d/workflow-engine/workflow-engine |
| Prometheus | http://localhost:18790 |
| Jaeger | http://localhost:18786 |

### Grafana workflow

1. Open dashboard → use **User** dropdown (`demo`, `alice`, `bob`)
2. Tables show runs/steps **per user** — proves tenant isolation in metrics
3. Submit a workflow → **Runs submitted (per minute)** bar chart spikes within one scrape interval (15s)

### Useful PromQL

```promql
# Backlog
sum(workflow_pending_steps{job="workflow-worker"})

# Per-user throughput
sum by (user) (rate(workflow_steps_executed_total{job="workflow-worker",status="completed"}[1m]))

# Submit rate
sum by (user) (increase(workflow_runs_submitted_total{job="workflow-api"}[1m]))

# Worker poll latency (DB contention proxy)
histogram_quantile(0.95, sum(rate(workflow_worker_poll_latency_seconds_bucket[1m])) by (le))
```

### Auth observability demo

```bash
make seed-multi-user   # 2 workflows each for demo, alice, bob
```

Log in as each user in the UI — dashboards show only that user's runs; Grafana tables split metrics by `user`.

---

## 3. Local testing

Run the stack first: `make up` (ports in `.env.ports`).

### Unit tests (`make test`)

pytest against the FastAPI app and engine (no docker required for most tests):

- DAG validation — cycles, unknown deps, step limits
- JWT ownership — users cannot read or cancel another user's runs
- Metrics — `workflow_runs_submitted_total` includes `user` label

### End-to-end verification (`make verify-e2e`)

`scripts/verify-e2e.sh` exercises the **full docker compose stack**:

| Check | Pass criteria |
|-------|---------------|
| API | `/health`, `/ready` |
| Observability | Prometheus, Grafana, Jaeger reachable |
| UI | nginx serves the React app |
| Auth | `POST /auth/login` as `demo` returns JWT |
| Workflow | `POST /runs` with `linear` preset → poll until `status=completed` |
| Metrics | `GET /metrics` contains `workflow_` series |

Optional seed data for multi-user demos: `make seed-multi-user` (2 runs each for demo, alice, bob).

Manual UI validation is documented with screenshots in [e2e-screenshots/](e2e-screenshots/) and [ARCHITECTURE.md](ARCHITECTURE.md) (auth E2E flow).

### CLI demo (`make demo`)

Interactive curl walkthrough — login, submit, poll status — without opening the browser.

---

## 4. Load testing

Load tests validate two separate concerns: **(A) the API accepts burst submits while staying fast**, and **(B) workers drain the queue until saturation** (SQLite lock or too few replicas).

### Tooling

| Item | Detail |
|------|--------|
| **Runner** | [k6](https://k6.io/) (Grafana k6) |
| **Script** | `loadtest/k6_workflows.js` |
| **Make target** | `make loadtest` |
| **Auth** | `setup()` logs in once as `demo`; all VUs share that JWT |

Install k6:

```bash
# macOS
brew install k6

# Linux
sudo gpg -k && sudo gpg --no-default-keyring --keyring /usr/share/keyrings/k6-archive-keyring.gpg \
  --keyserver hkp://keyserver.ubuntu.com:80 --recv-keys C5AD17C747E3415A3642D57D77C6C491D6AC1D69
echo "deb [signed-by=/usr/share/keyrings/k6-archive-keyring.gpg] https://dl.k6.io/deb stable main" | sudo tee /etc/apt/sources.list.d/k6.list
sudo apt-get update && sudo apt-get install k6
```

### Default test profile

```javascript
// loadtest/k6_workflows.js
export const options = {
  vus: 100,        // 100 concurrent virtual users
  duration: "30s", // fixed duration (not ramping)
};
```

Each iteration:

1. `POST /runs` with `{"preset":"linear"}` and `Authorization: Bearer <token>`
2. Assert HTTP **202 Accepted**
3. `sleep(0.1)` — 100ms think time between submits

**Rough order of magnitude:** 100 VUs × ~30s ≈ **hundreds to low thousands** of workflow submissions (depends on API latency). Each `linear` run creates **4 steps** (~300ms of simulated `sleep` work plus transforms), so the worker must complete **~4× submit count** step executions.

### Workload under test (`linear` preset)

| Step | Type | Depends on | Work |
|------|------|------------|------|
| `validate` | transform | — | instant |
| `enrich` | transform | validate | instant |
| `process` | sleep | enrich | 300ms |
| `finalize` | transform | process | instant |

End-to-end run time with **1 worker**: ~0.5–1.5s (poll interval + DB + sleep). Under load, completion time is dominated by **queue depth**, not step duration.

### How to run

**Docker compose (1 worker — good for backlog demo):**

```bash
make up
# optional baseline
curl -sf http://localhost:18700/metrics | grep workflow_pending_steps

make loadtest
# or explicitly:
k6 run -e API_URL=http://localhost:18700 loadtest/k6_workflows.js
```

**Kubernetes (scale workers between runs):**

```bash
make kind-up && make deploy

# Port-forward API if needed (kind ingress) or use NodePort
export API_URL=http://localhost:18700

for REPLICAS in 1 4 8; do
  kubectl scale deployment workflow-worker -n workflow-system --replicas=$REPLICAS
  kubectl rollout status deployment/workflow-worker -n workflow-system
  echo "=== workers=$REPLICAS ==="
  k6 run -e API_URL=$API_URL loadtest/k6_workflows.js
  sleep 30   # let queue drain before next run
done
```

### What to watch during a run

| Where | Signal | Healthy | Saturated |
|-------|--------|---------|-----------|
| **k6 stdout** | `http_req_duration` p95 | Stable, low hundreds of ms | Climbing |
| **k6 stdout** | `checks{submit 202}` | 100% pass | Drops if API overloaded |
| **Grafana** | `workflow_pending_steps` | Brief spike, returns to 0 | Stays high through test |
| **Grafana** | `rate(workflow_steps_executed_total)` | Rises with workers | Plateaus at 8 workers |
| **Grafana** | `workflow_worker_poll_latency_seconds` p95 | Low | High — DB contention |
| **Worker logs** | `database is locked` | Absent | Frequent at 8 workers |
| **Prometheus** | `workflow_runs_submitted_total{user="demo"}` | Jumps by submit count | — |

Open Grafana before starting k6: http://localhost:18701/d/workflow-engine/workflow-engine?refresh=5s — filter **User = demo** (load test user).

### Interpreting k6 output

Example fields at end of run:

```
http_req_duration..............: avg=45ms  p(95)=120ms
http_req_failed................: 0.00%
checks.........................: 100.00% ✓ submit 202
iterations.....................: 2847    # total submit attempts
vus............................: 100     max=100
```

- **Submit path is healthy** if `submit 202` checks pass and `http_req_failed` ≈ 0%. The API is designed to return quickly (202) even when workers are behind.
- **Worker saturation** is *not* visible in k6 alone — use `workflow_pending_steps` and step completion rate in Grafana during and after the run.
- After the test ends, pending steps should drain to **0** within ~1–5 minutes (depends on worker count and backlog size).

### Tuning the test

Override via k6 CLI without editing the script:

```bash
# Lighter smoke test
k6 run --vus 10 --duration 15s -e API_URL=http://localhost:18700 loadtest/k6_workflows.js

# Heavier burst
k6 run --vus 200 --duration 60s -e API_URL=http://localhost:18700 loadtest/k6_workflows.js
```

To test other presets, change `preset` in `k6_workflows.js`:

| Preset | Steps | Notes |
|--------|-------|-------|
| `linear` | 4 | Default; steady load |
| `fanout` | 5 | Parallel branches; more DB writes per run |
| `flaky` | 3 | Retries; amplifies queue pressure |

### Multi-user load (extension)

The default script uses a **single** `demo` token. To stress per-user isolation and per-user metrics:

1. Run separate k6 scenarios per user (different `setup()` tokens), or
2. Use k6 `executor` with multiple scenarios in one script.

Grafana **Runs submitted by user** table should show growth only on `demo` during the default test.

### Worker config that affects load results

| Env var | Default | Effect |
|---------|---------|--------|
| `WORKER_POLL_INTERVAL_MS` | 200 | Lower = faster drain, more DB polls |
| `WORKER_LEASE_SECONDS` | 60 | Must exceed step time + lock wait |
| SQLite `busy_timeout` | tuned in `db.py` | Retries on lock instead of immediate fail |

### Recommended interview demo flow

1. Scale workers to **1** → run k6 → show backlog rising in Grafana
2. Scale to **4** → re-run k6 → backlog clears faster; higher step rate
3. Scale to **8** → re-run k6 → show flat step rate + `database is locked` in logs
4. Verbalize: *"Saturation is SQLite single-writer; production would use SQS + Postgres."*

---

## 5. Scaling demonstration & saturation point

### Procedure

**Docker compose (single worker):**

```bash
make up
make seed-multi-user
# Watch workflow_pending_steps rise during burst submits
```

**Kubernetes (horizontal workers)** — see [§4 Load testing](#4-load-testing) for full procedure:

```bash
make kind-up && make deploy

kubectl scale deployment workflow-worker -n workflow-system --replicas=1
k6 run -e API_URL=http://localhost:18700 loadtest/k6_workflows.js

kubectl scale deployment workflow-worker -n workflow-system --replicas=4
k6 run -e API_URL=http://localhost:18700 loadtest/k6_workflows.js

kubectl scale deployment workflow-worker -n workflow-system --replicas=8
k6 run -e API_URL=http://localhost:18700 loadtest/k6_workflows.js
```

Default profile: **100 VUs, 30s**, `linear` preset (~4 steps per run). See §4 for workload math and Grafana signals.

### Expected behavior

| Workers | Throughput | `workflow_pending_steps` | Notes |
|---------|------------|--------------------------|-------|
| 1 | Low | Rises sharply under 100 VU load | Single poll loop bottleneck |
| 4 | ~matches moderate load | Stabilizes faster | Good sweet spot on laptop |
| 8 | Diminishing returns | May still spike on burst | SQLite write lock dominates |

### Saturation point

**Primary ceiling: SQLite single-writer lock** (~4–6 active workers on a single DB file).

Evidence:
- `workflow_worker_poll_latency_seconds` p95 increases
- Worker logs: `database is locked` under high parallelism
- Adding workers past ~4–6 does not linearly increase completed steps/sec

**Secondary ceiling:** single worker poll interval (`WORKER_POLL_INTERVAL_MS`, default 500ms) — one worker can't drain faster than poll + execute cycle.

---

## 6. What breaks under load

| Failure mode | Symptom | Root cause |
|--------------|---------|------------|
| **Queue backlog** | `workflow_pending_steps` high, slow UI status updates | Too few workers for submit rate |
| **SQLite lock contention** | Worker errors, retries, flat throughput at 8 workers | Multiple writers on one SQLite file |
| **Lease expiry storms** | Same step re-attempted after slow execution | `duration_ms` + lock wait > `WORKER_LEASE_SECONDS` |
| **Flaky step amplification** | Retry metrics spike, pending queue grows | `flaky` preset under high concurrency |
| **API auth hot path** | 401s if load test token expires | k6 uses single token from setup — fine for demo |
| **Prometheus scrape lag** | Grafana appears stale for ~15s | `scrape_interval: 15s` — not a system failure |

What does **not** break (by design):
- Worker pod kill → reaper recovers expired leases; run continues
- API restart → SQLite persists on volume; workers resume polling

---

## 7. Changes made to improve the system

| Change | Impact |
|--------|--------|
| **WAL mode + `busy_timeout`** on SQLite | Reduces immediate `database is locked` failures |
| **Filtered index** on `(status) WHERE status IN ('pending','running')` | Faster worker poll queries |
| **`SKIP LOCKED` leasing** | Safe multi-worker concurrency without double execution |
| **Lease reaper background task** | Crash recovery without manual intervention |
| **Per-user Prometheus labels** | Grafana proves auth isolation in metrics, not just UI |
| **Grafana dashboard v4** | Datasource binding, user template variable, per-user tables |
| **PyJWT** (replaced python-jose) | Fixed SIGILL in slim Docker image |
| **Dedicated port block** (`.env.ports`) | Avoids kubectl port-forward conflicts on laptop |
| **Multi-user seed script** | `make seed-multi-user` populates demo/alice/bob data for observability |

---

## 8. If I had more time

### Production hardening (priority order)

1. **Decouple queue from state** — SQS (or Redis Streams) for step dispatch; Postgres/RDS for durable state. Removes SQLite write ceiling.
2. **Idempotency keys** on submit — safe client retries.
3. **HPA on custom metric** — scale workers on `workflow_pending_steps` (KEDA or Prometheus adapter).
4. **Postgres migration** — same SQLAlchemy models; connection pooling; read replica for `GET /runs`.
5. **Rate limiting per user** — protect API from one tenant saturating workers.

### Observability

- Exemplars linking Prometheus histograms → Jaeger traces
- Alertmanager rules: `pending_steps > 50 for 5m`, high poll latency p95
- Structured log correlation: inject `trace_id` into all log lines

### Product / UX

- Workflow definition UI (not just presets)
- Step-level cancel and per-run priority
- WebSocket push instead of 1.5s polling on run detail

### Testing

- Integration tests with Testcontainers (Postgres)
- Chaos tests: kill worker mid-step, verify exactly-once completion semantics
- CI pipeline: `make test`, `make verify-e2e`, k6 smoke on PR

---

## Quick reference

```bash
make up              # docker compose stack
make verify-e2e      # API + auth + workflow + observability checks
make seed-multi-user # demo / alice / bob sample data
make test            # pytest
make loadtest        # k6 (requires k6 installed)
make demo            # CLI walkthrough
```

**Users:** `demo/demo`, `alice/alice`, `bob/bob` — password equals username.
