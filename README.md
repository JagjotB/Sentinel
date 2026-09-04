# Sentinel

Sentinel is an evidence-backed reliability engineering platform. It ingests an alert, dynamically assigns
specialized investigation agents, correlates Kubernetes state, metrics, logs, changes, and prior incidents,
then emits a verified diagnosis or explicitly abstains. Every remediation is a proposal: policy validation,
a scoped approval token, and a human decision stand between an agent and a write.

![Sentinel evidence graph](frontend/public/og.png)

## What is implemented

- A compiled LangGraph state machine with conditional verification routing, concurrent specialist
  collection, checkpoint-aware restart routing, explicit budgets, and a durable Sentinel state model.
- LangChain prompt/model/output-parser pipelines for diagnosis and independent verification. Every MCP
  tool is exposed as a schema-bound LangChain `StructuredTool`; every model call is metered and persisted.
- A dynamic supervisor plus infrastructure, telemetry, change-analysis, retrieval, diagnosis, verifier, and
  remediation agents. Supported claims must reference durable evidence IDs.
- Typed, authenticated, timeout-bounded, idempotent tool servers for Kubernetes, observability, Git, and
  incident knowledge. Tool calls and their output provenance are persisted.
- A deterministic simulator containing 36 scenarios and 18 root causes across resource, Kubernetes,
  network, database, deployment, and traffic failures.
- A buildable kind cluster with checkout, payments, worker, frontend, PostgreSQL, and continuous traffic;
  all 18 root causes map to namespace-scoped `kubectl` fault and reset strategies.
- A real four-layer temporal autoencoder trained with explicit NumPy backpropagation, learned log
  representations and clustering, hybrid BM25/vector retrieval, and a trained pairwise incident reranker.
- FastAPI, SQLAlchemy, SQLite/PostgreSQL support, signed approval tokens, a React operator console,
  Grafana/Prometheus, Docker Compose, Kubernetes manifests, test suites, and CI.
- A live operator console backed by a server-side API proxy: incident selection, scenario execution,
  durable tasks/evidence/traces, real budget usage, verifier state, and governed approval decisions are
  loaded from the control plane rather than demo constants.

## Architecture

```mermaid
flowchart LR
  A[Alert API] --> R[Durable runtime]
  R --> S[Dynamic supervisor]
  S --> I[Infrastructure]
  S --> T[Telemetry + logs]
  S --> C[Change analysis]
  S --> K[Retrieval]
  I & T & C & K --> E[(Evidence store)]
  E --> D[Diagnosis]
  D --> V[Verifier]
  V -->|weak or contradictory| X[Abstain / escalate]
  V -->|supported| P[Sandboxed proposal]
  P --> G[Policy gate]
  G --> H[Scoped human approval]
  R --> O[Trace · metrics · audit]
```

The deterministic local provider runs through the same LangChain and LangGraph production path without a
paid service. Install `.[models]` and set `SENTINEL_MODEL_PROVIDER` / `SENTINEL_MODEL_NAME` to use a
LangChain-supported hosted model. The container path swaps SQLite for PostgreSQL while retaining the same
repository and contracts. See [architecture](docs/architecture.md), [ADR 0001](docs/decisions/0001-portable-local-control-plane.md),
and [ADR 0002](docs/decisions/0002-langgraph-langchain-runtime.md).

## Quick start

Python 3.12+ and Node 22.13+ are required.

```powershell
python -m venv .venv
.venv\Scripts\Activate.ps1
python -m pip install -e ".[dev]"
python -m simulator.bootstrap --materialize
uvicorn api.main:app --reload --port 8000
```

In a second terminal, start the durable investigation worker:

```powershell
sentinel-worker
```

In a third terminal:

```powershell
cd frontend
npm ci
npm run dev
```

Open the operator console at `http://localhost:3000`, API documentation at `http://localhost:8000/docs`,
and the checked-in report at `evals/reports/latest/report.html`. Mutating local API requests use
`Authorization: Bearer sentinel-local-token`; replace all defaults outside local development.

For the container stack:

```bash
docker compose up --build
```

This starts PostgreSQL, Redis, the API, a lease-based investigation worker, Prometheus at `:9090`, and
Grafana at `:3001` with the Sentinel dashboard provisioned. The React console remains a separate Node
process so it can be deployed independently.

For the real local Kubernetes simulator, install Docker, kind, and kubectl, then run:

```powershell
python -m simulator.cluster bootstrap
curl.exe -X POST http://localhost:8000/v1/simulator/cluster/inject `
  -H "Authorization: Bearer sentinel-local-token" `
  -H "Content-Type: application/json" `
  -d '{"scenario_id":"oom_killed_001"}'
python -c "from simulator.faults.kubernetes import KubernetesFaultController; KubernetesFaultController().reset()"
```

The cluster exposes the demo frontend at `http://localhost:30080`. See the
[simulator runbook](docs/simulator.md) for the complete fault mapping and reset guarantees.

To investigate the running cluster through real `kubectl`, Prometheus, Tempo, Git, and durable incident
adapters, configure the `SENTINEL_*` integration settings in `.env.example` and call:

```powershell
curl.exe -X POST http://localhost:8000/v1/simulator/cluster/investigate `
  -H "Authorization: Bearer sentinel-local-token" `
  -H "Content-Type: application/json" `
  -d '{"scenario_id":"oom_killed_001"}'
```

These adapters retain the same schemas and policy boundary as simulator tools. See the
[live integration guide](docs/live-integrations.md) for scopes, credentials, and verification limits.

## Reproduce the demo and evaluation

```powershell
python -m pytest
python -m evals.runner --suite portfolio
python -m ml.telemetry_anomaly.train --quick
cd frontend
npm run lint
npm run build
```

The retrieval benchmark now builds its index only from training variants, excludes the active incident at
runtime, and constructs queries solely from alert-time fields. Its split and corpus checksum are recorded in
`ml/artifacts/retrieval_metrics.json`.

The prior 86.1% portfolio result is intentionally **not presented as a current project claim**. The audit
found that its comparison systems reused a full-run evidence capture and reported proportional replay
timings. Those checked-in files remain historical evidence while the independent baseline/ablation runner is
rebuilt. See [the evaluation notes](docs/evaluation.md).

## Safety invariants

- Read tools run under explicit allowlists; low-risk writes require approval; destructive actions are
  denied even when an approval flag is present.
- Approval tokens are HMAC-signed, actor/incident/remediation-scoped, nonce-bearing, expiring, and
  single-use; idempotent replays return the original recorded decision.
- Prompt-injection-like log text is treated as untrusted evidence and removed from runtime context.
- Supported diagnoses cannot reference evidence that is absent from durable storage.
- Patch paths and content are sandboxed. An approval may materialize a content-addressed patch artifact,
  but proposals never auto-apply, auto-merge, or execute shell commands.
- Secrets are redacted from context and fixtures; tool/model calls, approvals, and denials are auditable.

See the [threat model](docs/security.md) before connecting live credentials.

## Repository map

| Path | Purpose |
|---|---|
| `api/` | FastAPI control plane and stable schemas |
| `runtime/` | Execution state, checkpoints, budgets, retries, permissions, tracing |
| `agents/` | Supervisor and specialized evidence/verification/remediation agents |
| `mcp/` | Typed audited infrastructure and knowledge tool contracts |
| `simulator/` | Reproducible services, fault injectors, catalog, Kubernetes assets |
| `ml/` | Telemetry model, log intelligence, reranker, trained artifacts |
| `retrieval/` | Versioned corpus, hybrid search, provenance, evaluation |
| `persistence/` | SQLAlchemy records, migrations, idempotency, audit trail |
| `safety/` | Approval, policy, sandbox, payload, and secret boundaries |
| `frontend/` | React operator console and benchmark view |
| `evals/` | Baselines, ablations, metrics, raw and rendered reports |
| `infrastructure/` | Docker, Kubernetes, Prometheus, and Grafana configuration |
| `tests/` | Unit, contract, integration, agent, ML, security, resilience, E2E |

## Documentation

- [Five-minute demo](docs/demo.md)
- [Evaluation protocol and limitations](docs/evaluation.md)
- [Operations and troubleshooting](docs/operations.md)
- [Security and threat model](docs/security.md)
- [Kubernetes simulator](docs/simulator.md)
- [Live investigation adapters](docs/live-integrations.md)
- [Contributing](docs/contributing.md)
- [Resume-ready project bullets](docs/resume.md)

## License

[MIT](LICENSE)
