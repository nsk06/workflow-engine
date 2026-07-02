# Workflow Engine — Design & Operations

Principal-engineer interview demo: async DAG workflow execution with multi-user auth, observability, and a scaling story.

---

## 1. How I designed it

### Problem framing

Build a system that accepts DAG workflows, executes steps asynchronously with retries, survives worker crashes, and gives operators visibility into backlog and latency — without requiring a full cloud stack for local demo.

### Architecture

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

## 3. Scaling demonstration & saturation point

### Procedure

**Docker compose (single worker):**

```bash
make up
make seed-multi-user
# Watch workflow_pending_steps rise during burst submits
```

**Kubernetes (horizontal workers):**

```bash
make kind-up && make deploy

kubectl scale deployment workflow-worker -n workflow-system --replicas=1
k6 run -e API_URL=http://localhost:18700 loadtest/k6_workflows.js
# Note: pending_steps rises, completion latency grows

kubectl scale deployment workflow-worker -n workflow-system --replicas=4
k6 run loadtest/k6_workflows.js

kubectl scale deployment workflow-worker -n workflow-system --replicas=8
k6 run loadtest/k6_workflows.js
```

`loadtest/k6_workflows.js`: 100 VUs, 30s, each submits `linear` preset (4 steps, ~1s total).

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

## 4. What breaks under load

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

## 5. Changes made to improve the system

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

## 6. If I had more time

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
