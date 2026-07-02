# Architecture

Deep-dive on components, diagrams, leasing, DAGs, and auth. For load testing and scaling see [DESIGN.md](DESIGN.md).

---

## System overview

```mermaid
flowchart TB
    subgraph clients [Clients]
        Browser[Browser / React UI]
        K6[k6 load test]
    end

    subgraph app [Application tier]
        API[workflow-api<br/>FastAPI]
        Worker1[workflow-worker 1]
        WorkerN[workflow-worker N]
    end

    subgraph data [Data tier]
        SQLite[(SQLite<br/>runs + steps + queue)]
    end

    subgraph obs [Observability]
        Prom[Prometheus]
        Graf[Grafana]
        OTel[OTel Collector]
        Jaeger[Jaeger]
    end

    Browser -->|HTTPS REST + JWT| API
    K6 -->|POST /runs + JWT| API
    API --> SQLite
    Worker1 --> SQLite
    WorkerN --> SQLite
    API -->|/metrics| Prom
    Worker1 -->|/metrics| Prom
    Prom --> Graf
    API -->|OTLP traces| OTel
    Worker1 -->|OTLP traces| OTel
    OTel --> Jaeger
```

| Component | Role |
|-----------|------|
| **workflow-api** | REST: auth, submit, list, get, cancel. Writes durable state. Stateless. |
| **workflow-worker** | Polls SQLite, claims steps, executes handlers, schedules dependents. |
| **workflow-ui** | React SPA (nginx): login, submit presets, live step timeline. |
| **SQLite** | Single source of truth for runs, steps, and the work queue (WAL mode). |
| **Prometheus + Grafana** | Metrics with per-user labels; provisioned dashboard. |
| **OTel + Jaeger** | Traces for `submit_run` and `execute_step`. |

---

## Docker Compose deployment

```mermaid
flowchart LR
    subgraph host [localhost]
        UI[ui :18780]
        API[api :18700]
        W[worker :18710 metrics]
        DB[(workflow-data volume)]
        PR[prometheus :18790]
        GR[grafana :18701]
        JA[jaeger :18786]
        OC[otel-collector]
    end

    UI -->|VITE_API_URL| API
    API --> DB
    W --> DB
    PR --> API
    PR --> W
    GR --> PR
    API --> OC
    W --> OC
    OC --> JA
```

---

## End-to-end: submit a workflow

```mermaid
sequenceDiagram
    autonumber
    participant U as User / Browser
    participant UI as React UI
    participant API as workflow-api
    participant DB as SQLite
    participant W as workflow-worker

    U->>UI: Choose preset, Submit
    UI->>API: POST /runs + Bearer JWT
    API->>API: Validate DAG (acyclic, types)
    API->>DB: INSERT workflow_run
    API->>DB: INSERT all workflow_steps (pending)
    API->>DB: schedule_ready_steps()
    API->>API: metrics: runs_submitted{user}
    API-->>UI: 202 {run_id}
    UI->>API: GET /runs/{id} (poll 1.5s)

    loop Until queue empty
        W->>DB: SELECT ... FOR UPDATE SKIP LOCKED
        W->>DB: SET status=running, leased_until, worker_id
        W->>W: execute_step (sleep / transform / flaky)
        W->>DB: SET status=completed, output
        W->>DB: schedule_ready_steps(run_id)
    end

    API-->>UI: status=completed, steps[]
```

**Key idea:** the API never runs step logic. It only **records** work. Workers **pull** work from the same database.

---

## DAG and topological sort

### What is the DAG here?

A **Directed Acyclic Graph**: steps are nodes, `depends_on` are arrows (“B waits for A”). **No cycles** — you can’t have A depend on B while B depends on A.

**Fanout preset example:**

```mermaid
flowchart TD
    validate[validate<br/>transform]
    branch_a[branch_a<br/>sleep 400ms]
    branch_b[branch_b<br/>sleep 500ms]
    aggregate[aggregate<br/>transform]
    finalize[finalize<br/>transform]

    validate --> branch_a
    validate --> branch_b
    branch_a --> aggregate
    branch_b --> aggregate
    aggregate --> finalize
```

- **Roots** (no deps): `validate` — runnable immediately after submit.
- **Parallel**: `branch_a` and `branch_b` can run on different workers once `validate` completes.
- **Fan-in**: `aggregate` waits until **both** branches are done.

### Where DAG logic lives (two different jobs)

| Layer | File | What it does |
|-------|------|----------------|
| **Validation** | `backend/app/engine/dag.py` | On submit: duplicate keys, unknown deps, **cycle detection** (DFS), max 10 steps |
| **Scheduling** | `backend/app/engine/scheduler.py` | At runtime: “which `pending` steps have all deps `completed`?” — **not** full topo sort |
| **Display** | `frontend/.../RunDetail.tsx` | **Topological sort** to order the timeline UI top-to-bottom |

### Topological sort — what and why

**Topological sort** = order nodes so every dependency comes **before** its dependents.

- **Backend `topological_order()`** — used in tests/validation; proves the graph is a valid DAG and could order batch execution (we don’t use it to drive the worker; workers use **ready-set** polling instead).
- **Frontend `topologicalSteps()`** — sorts steps for the **timeline UI** so parents appear above children, even if `branch_b` finished before `branch_a`.

```mermaid
flowchart LR
    subgraph submit [On submit - API]
        V[validate_workflow]
        V --> C{cycle?}
        C -->|no| M[materialize all step rows]
        C -->|yes| E[400 error]
    end

    subgraph runtime [At runtime - worker]
        P[poll pending step]
        D{all deps completed?}
        P --> D
        D -->|yes| X[execute]
        D -->|no| P
        X --> S[schedule_ready_steps]
    end

    subgraph ui [UI display]
        T[topologicalSteps]
        T --> TL[timeline render]
    end
```

**Interview line:** “Topo sort validates and **displays** the DAG; **execution order** comes from dependency checks on each poll, which naturally allows parallel branches.”

### How `schedule_ready_steps` works

1. Load all steps for a `run_id`.
2. Build set of `completed` step keys.
3. For each `pending` step: if every key in `depends_on` is in `completed`, it’s **ready** (worker can claim it).
4. Resolve `input_data` from upstream `output` JSON.
5. If all steps terminal → mark run `completed` and aggregate outputs.

No central “orchestrator” process — the **database rows + scheduler function** are the orchestration.

---

## Authentication end-to-end

### Design choices

- **Stateless API** — no server-side sessions; JWT proves identity on every request.
- **Row-level tenancy** — `workflow_runs.submitted_by` set at submit from JWT `sub`.
- **404 not 403** on other users’ runs — don’t leak that a run ID exists.

### Auth flow diagram

```mermaid
sequenceDiagram
    participant U as User
    participant UI as React UI
    participant LS as localStorage
    participant API as workflow-api
    participant DB as SQLite

    Note over U,DB: Login
    U->>UI: username + password
    UI->>API: POST /auth/login {username, password}
    API->>API: authenticate_user vs DEMO_USERS
    API->>API: create_access_token (JWT HS256, exp 24h)
    API-->>UI: {access_token, username}
    UI->>LS: workflow_token, workflow_user
    UI->>UI: React state token + username

    Note over U,DB: Authenticated API call
    U->>UI: Submit workflow
    UI->>API: POST /runs + Authorization: Bearer JWT
    API->>API: get_current_user: decode JWT, extract sub
    API->>DB: INSERT run submitted_by = user.sub
    API-->>UI: 202

    Note over U,DB: List runs (isolation)
    UI->>API: GET /runs + Bearer JWT
    API->>API: get_current_user
    API->>DB: SELECT * WHERE submitted_by = user.sub
    API-->>UI: only this user's runs

    Note over U,DB: Access control
    UI->>API: GET /runs/{other_users_id} + Bearer JWT
    API->>DB: SELECT WHERE id = ? AND submitted_by = user.sub
    DB-->>API: no row
    API-->>UI: 404 Not found

    Note over U,DB: Logout
    U->>UI: Logout
    UI->>LS: clear workflow_token, workflow_user
    UI->>UI: redirect /login
```

### Step-by-step

1. **Login** — `POST /auth/login` checks `DEMO_USERS` env (`demo:demo,alice:alice,bob:bob`).
2. **Token** — PyJWT signs `{sub, username, exp}` with `JWT_SECRET`.
3. **Storage** — Browser stores token in `localStorage`; `apiFetch` adds `Authorization: Bearer ...` on every call.
4. **Protected routes** — FastAPI `Depends(get_current_user)` on `/runs`, `/presets`, etc.
5. **Submit** — `submitted_by=user.sub` written to DB; metric `workflow_runs_submitted_total{user="..."}` incremented.
6. **Read** — `list_runs` and `get_run` filter `WHERE submitted_by = user.sub`.
7. **Expiry** — API returns 401; UI clears session and shows “log in again”.
8. **Observability** — same `user` on metrics and trace spans; Grafana filters per tenant.

```mermaid
flowchart TB
    subgraph identity [Identity]
        Login[POST /auth/login]
        JWT[JWT access_token]
    end

    subgraph enforcement [Enforcement]
        Dep[get_current_user dependency]
        Filter[SQL submitted_by = sub]
    end

    subgraph surfaces [Surfaces]
        UIOnly[UI: dashboard scoped by token]
        Metrics[Prometheus: user label]
        Traces[Jaeger: user attribute]
    end

    Login --> JWT
    JWT --> Dep
    Dep --> Filter
    Filter --> UIOnly
    Filter --> Metrics
    Filter --> Traces
```

---

## Why separate API and workers?

- Submit returns **202** immediately — API never blocks on step duration.
- Workers scale with `kubectl scale`; API replicas stay light.
- Worker crash doesn’t take down the API.

## Why SQLite-as-queue?

- Zero extra infra for the demo.
- `FOR UPDATE SKIP LOCKED` = safe concurrent consumers.
- **Ceiling:** single-writer lock (~4–6 workers). Production: SQS + Postgres — [DESIGN.md](DESIGN.md).

## State machines

**Run:** `pending` → `running` → `completed` | `failed` | `cancelled`

**Step:** `pending` → `running` → `completed` | `failed` | `skipped` | `cancelled`

`flaky` steps: `running` → `pending` (retry with `next_attempt_at`) up to 5 attempts.

Workers claim steps with `FOR UPDATE SKIP LOCKED`, set `leased_until` and `worker_id`, and a background reaper resets expired `running` rows to `pending`.

```mermaid
stateDiagram-v2
    [*] --> pending: step created on submit
    pending --> running: worker claims step
    running --> completed: handler succeeds
    running --> pending: retry or expired lease
    running --> failed: max attempts exceeded
    pending --> skipped: run cancelled
    completed --> [*]
    failed --> [*]
    skipped --> [*]
```

---

## Data model (simplified)

```mermaid
erDiagram
    workflow_runs ||--o{ workflow_steps : contains
    workflow_runs {
        string id PK
        string status
        string submitted_by
        json definition
        json input
        json output
    }
    workflow_steps {
        string id PK
        string run_id FK
        string step_key
        string status
        json depends_on
        datetime leased_until
        string worker_id
        int attempt
    }
```

---

## Related docs

| Doc | Topics |
|-----|--------|
| [DESIGN.md](DESIGN.md) | Interview write-up, load testing, saturation |
| [OBSERVABILITY.md](OBSERVABILITY.md) | PromQL, Grafana, Jaeger |
| [SCALING.md](SCALING.md) | k6 worker sweep |
