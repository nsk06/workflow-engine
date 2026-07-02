# Architecture

## Components

| Component | Role |
|---|---|
| **workflow-api** | REST API: submit, list, status, cancel. JWT auth. Writes durable state. |
| **workflow-worker** | Polls SQLite for pending steps (`SKIP LOCKED`), executes handlers, schedules dependents. |
| **workflow-ui** | React dashboard: multi-user login, submit presets, live step timeline. |
| **SQLite** | Single source of truth for runs, steps, and implicit work queue (WAL mode). |
| **Prometheus + Grafana** | Metrics with per-user labels; pre-provisioned dashboard. |
| **OTel Collector + Jaeger** | Distributed traces for submit and step execution. |

## Why separate API and workers?

- API stays responsive under load (submit returns 202 immediately)
- Workers scale independently (HPA / `kubectl scale`)
- Crash isolation: worker failure doesn't take down API

## Why SQLite-as-queue?

- Zero bootstrap dependencies for local demo
- `FOR UPDATE SKIP LOCKED` gives safe concurrent leasing across workers
- Tradeoff: single-writer limit (~4–6 workers before lock contention)
- Production path: dedicated queue (SQS) + Postgres/RDS — see [DESIGN.md](DESIGN.md)

## State machine

**Run:** pending → running → completed | failed | cancelled

**Step:** pending → running → completed | failed | skipped | cancelled

Failed `flaky` steps retry with exponential backoff (max 5 attempts).

## DAG scheduling

On submit, all steps are created. Root steps (no deps) are pollable immediately. When a step completes, dependents whose deps are all `completed` become pollable.

## Auth

- Users: `demo`, `alice`, `bob` (password = username, configured via `DEMO_USERS`)
- JWT HS256; `submitted_by` on each run
- API filters all run endpoints by authenticated user

See [DESIGN.md](DESIGN.md) for full design rationale, observability, and scaling.
