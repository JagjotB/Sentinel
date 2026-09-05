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
| Tempo | 3200 | `/ready` and Grafana Explore |
| OTLP gRPC | 4317 | Collector receiver |
| OTLP HTTP | 4318 | Collector receiver |
| kind demo frontend | 30080 | `/`, `/healthz`, `/metrics` |

SQLite is the default. Set `SENTINEL_DATABASE_URL` to the Compose PostgreSQL URL for containers. Schema
version 4 is applied idempotently at repository startup.

`POST /v1/alerts` idempotently creates one queued work item per incident. Run `sentinel-worker` as a
separate process (the Compose stack already does this). A worker claims a time-bounded lease, renews it
during execution, and writes its execution ID on completion. If a process dies, another worker can reclaim
the expired lease and resume the existing checksummed graph checkpoint. Provider failures use bounded
exponential retries; exhausted jobs become `failed` after `SENTINEL_WORKER_MAX_ATTEMPTS`.

## Common failures

- **Model artifact missing:** run `python -m ml.telemetry_anomaly.train --quick`.
- **Frontend native binding error:** use Node 22.13+ and run `npm ci` inside `frontend`; do not invoke Vinext
  from the repository root.
- **API returns 401:** add the configured bearer token.
- **API returns 409:** the idempotency key was reused with a different body. Generate a new key or replay
  the exact original body.
- **Investigation ends `insufficient_evidence`:** inspect evidence, tasks, and trace. Do not force approval.
- **Execution was interrupted:** use `resume_execute` with its existing execution ID. Checkpoint checksums
  detect damaged state, `graph_stage` resumes at the next LangGraph node, and prior time/token/tool/cost
  usage is restored before the next operation.
- **Hosted model will not initialize:** install `.[models]`, use a provider name supported by LangChain, and
  configure that provider's credentials. The default `deterministic` model requires no external credentials.
- **CORS blocks the console:** add the deployed origin to the API allowlist; do not use a wildcard with
  credentials.
- **Cluster bootstrap fails before deployment:** verify that Docker is running and `docker`, `kind`, and
  `kubectl` are all on `PATH`. `python -m simulator.cluster status` prints the complete demo workload state.
- **A fault leaves the demo degraded:** call `POST /v1/simulator/cluster/reset` or run the reset command in
  the README. Reset is namespace-scoped and reapplies canonical images, environment, configuration, probes,
  selectors, resource limits, traffic settings, secrets, and network policy.

## Observability

Prometheus scrapes `/metrics`; Grafana loads `infrastructure/grafana/sentinel-dashboard.json`. The dashboard
covers HTTP, incident and diagnosis latency, incident outcomes, model calls/tokens/cost, tool calls,
retries, approvals, abstentions, worker outcomes, and errors. Metric labels are deliberately bounded; use
traces or the audit API for per-incident identifiers rather than adding high-cardinality IDs to Prometheus.

The API and worker export OTLP/HTTP spans to the OpenTelemetry Collector, which batches them into Tempo.
The persisted 32-character execution trace ID is the actual OpenTelemetry trace ID. It remains stable when
a leased job is resumed after a process restart. Graph nodes, model calls, tool calls, approvals, governed
actions, HTTP requests, and worker execution are nested spans. Compose configures
`SENTINEL_OTLP_ENDPOINT=http://otel-collector:4318/v1/traces`; leave the setting blank to disable export in
a local process. In Grafana, select the provisioned Tempo source in Explore and paste an execution trace ID.

For production, send OTLP over TLS to an authenticated collector and configure retention/object storage;
the bundled one-hour local Tempo volume is for reproducible development only.
