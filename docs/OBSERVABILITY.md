# Observability

## Signals

| Signal | Tool | Correlation |
|---|---|---|
| Metrics | Prometheus → Grafana | `user`, `step_type`, `status` labels |
| Traces | OTel → Jaeger | `user`, `run_id`, `step_key` span attributes |
| Logs | structlog JSON (stdout) | `run_id`, `step_key`, `user` fields |

## Demo walkthrough

1. `make seed-multi-user` — populate metrics for demo, alice, bob
2. Open Grafana → **User** filter → per-user tables and charts
3. Submit workflow from UI → watch `workflow_runs_submitted_total{user="..."}` increase
4. Jaeger → service `workflow-api` or `workflow-worker` → filter by `user` tag

## URLs (default ports in `.env.ports`)

- Grafana: http://localhost:18701/d/workflow-engine/workflow-engine
- Prometheus: http://localhost:18790
- Jaeger: http://localhost:18786

## Alerts (suggested)

```promql
workflow_pending_steps > 50   # worker saturation
histogram_quantile(0.95, rate(workflow_worker_poll_latency_seconds_bucket[5m])) > 1  # DB contention
```

Full queries and scaling notes: [DESIGN.md](DESIGN.md)
