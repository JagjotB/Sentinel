# Operations and troubleshooting

## Local ports

| Service | Port | Check |
|---|---:|---|
| React console | 3000 | `/` and `/benchmarks` |
| FastAPI | 8000 | `/healthz`, `/docs`, `/metrics` |
| PostgreSQL | 5432 | Compose health check |
| Redis | 6379 | `redis-cli ping` |
| Prometheus | 9090 | `/-/healthy` |
| Grafana | 3001 | provisioned Sentinel folder |

SQLite is the default. Set `SENTINEL_DATABASE_URL` to the Compose PostgreSQL URL for containers. Schema
version 1 is applied idempotently at repository startup.

## Common failures

- **Model artifact missing:** run `python -m ml.telemetry_anomaly.train --quick`.
- **Frontend native binding error:** use Node 22.13+ and run `npm ci` inside `frontend`; do not invoke Vinext
  from the repository root.
- **API returns 401:** add the configured bearer token.
- **API returns 409:** the idempotency key was reused with a different body. Generate a new key or replay
  the exact original body.
- **Investigation ends `insufficient_evidence`:** inspect evidence, tasks, and trace. Do not force approval.
- **Execution was interrupted:** use `resume_execute` with its existing execution ID. Checkpoint checksums
  detect damaged state, and `graph_stage` resumes at the next LangGraph node.
- **Hosted model will not initialize:** install `.[models]`, use a provider name supported by LangChain, and
  configure that provider's credentials. The default `deterministic` model requires no external credentials.
- **CORS blocks the console:** add the deployed origin to the API allowlist; do not use a wildcard with
  credentials.

## Observability

Prometheus scrapes `/metrics`; Grafana loads `infrastructure/grafana/sentinel-dashboard.json`. HTTP counts
and latency, incident outcomes, tool calls, model tokens/cost, retries, approvals, and errors carry stable
incident/execution/trace identifiers. Set `SENTINEL_OTLP_ENDPOINT` to export spans.
