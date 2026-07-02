# Scaling

See [DESIGN.md](DESIGN.md) for the full story:

- **§3 Load testing** — k6 install, script profile, what to watch, interpreting results
- **§4 Scaling & saturation** — worker replica sweep (1 → 4 → 8)
- **§5 What breaks under load** — failure modes

## Quick test

```bash
kubectl scale deployment workflow-worker -n workflow-system --replicas=1
k6 run -e API_URL=http://localhost:18700 loadtest/k6_workflows.js

kubectl scale deployment workflow-worker -n workflow-system --replicas=4
k6 run -e API_URL=http://localhost:18700 loadtest/k6_workflows.js

kubectl scale deployment workflow-worker -n workflow-system --replicas=8
k6 run -e API_URL=http://localhost:18700 loadtest/k6_workflows.js
```

## Saturation summary

| Workers | Behavior |
|---|---|
| 1 | `workflow_pending_steps` rises; high completion latency |
| 4 | Good throughput for laptop demo |
| 8+ | SQLite `database is locked`; diminishing returns |

## Production path

External queue (SQS) + Postgres/RDS + HPA on `workflow_pending_steps`.
