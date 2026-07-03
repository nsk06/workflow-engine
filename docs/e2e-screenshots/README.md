# E2E screenshots

Captured against the local docker compose stack (ports in `.env.ports`).

## UI flow (`http://localhost:18780`)

| File | Description |
|------|-------------|
| `01-dashboard-demo.png` | Dashboard as `demo` — lists only demo-submitted runs |
| `02-submit-fanout.png` | Submit workflow page, fanout-fanin preset |
| `03-run-completed-fanout.png` | Run detail after submit — status COMPLETED, step timeline |
| `04-dashboard-alice-empty.png` | Dashboard as `alice` — empty (proves per-user isolation) |

Reproduce: `make up` → open UI → login as demo → submit fanout → logout → login as alice.

## Observability (`http://localhost:18701`, `http://localhost:18790`)

| File | Description |
|------|-------------|
| `05-grafana-dashboard-demo.png` | Grafana workflow-engine dashboard, **User = demo** |
| `06-prometheus-targets.png` | Prometheus targets — API and worker jobs **UP** |
| `07-prometheus-workflow-metrics.png` | Prometheus graph for `workflow_runs_submitted_total` |

Reproduce: `make up` → submit workflows → `./scripts/capture-obs-screenshots.sh`

Referenced from the root [README](../README.md) and [OBSERVABILITY.md](../OBSERVABILITY.md).
