# E2E screenshots

Captured via local browser automation against `http://localhost:18780` (ports in `.env.ports`).

| File | Description |
|------|-------------|
| `01-dashboard-demo.png` | Dashboard as `demo` — lists only demo-submitted runs |
| `02-submit-fanout.png` | Submit workflow page, fanout-fanin preset |
| `03-run-completed-fanout.png` | Run detail after submit — status COMPLETED, step timeline |
| `04-dashboard-alice-empty.png` | Dashboard as `alice` — empty (proves per-user isolation) |

Reproduce: `make up` → open UI → login as demo → submit fanout → logout → login as alice.

Referenced from the root [README](../README.md#e2e-screenshots).
