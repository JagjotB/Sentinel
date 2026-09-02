# Sentinel

Sentinel is an evidence-backed reliability engineering platform. It ingests an alert, dynamically assigns
specialized investigation agents, correlates Kubernetes state, metrics, logs, changes, and prior incidents,
then emits a verified diagnosis or explicitly abstains. Every remediation is a proposal: policy validation,
a scoped approval token, and a human decision stand between an agent and a write.

![Sentinel evidence graph](frontend/public/og.png)

## What is implemented

- A custom checkpointed runtime with explicit state, budgets, retries, circuit breakers, loop detection,
  task scheduling, context compression, permissions, model routing, OpenTelemetry spans, and Prometheus
  metrics.
- A dynamic supervisor plus infrastructure, telemetry, change-analysis, retrieval, diagnosis, verifier, and
  remediation agents. Supported claims must reference durable evidence IDs.
- Typed, authenticated, timeout-bounded, idempotent tool servers for Kubernetes, observability, Git, and
  incident knowledge. Tool calls and their output provenance are persisted.
- A deterministic simulator containing 36 scenarios and 18 root causes across resource, Kubernetes,
  network, database, deployment, and traffic failures.
- A real four-layer temporal autoencoder trained with explicit NumPy backpropagation, learned log
  representations and clustering, hybrid BM25/vector retrieval, and a trained pairwise incident reranker.
- FastAPI, SQLAlchemy, SQLite/PostgreSQL support, signed approval tokens, a React operator console,
  Grafana/Prometheus, Docker Compose, Kubernetes manifests, test suites, and CI.

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

The deterministic local path requires no model API or paid service. The container path swaps SQLite for
PostgreSQL while retaining the same repository and contracts. See [architecture](docs/architecture.md) and
[ADR 0001](docs/decisions/0001-portable-local-control-plane.md).

## Quick start

Python 3.12+ and Node 22.13+ are required.

```powershell
python -m venv .venv
.venv\Scripts\Activate.ps1
python -m pip install -e ".[dev]"
python -m simulator.bootstrap --materialize
uvicorn api.main:app --reload --port 8000
```

In a second terminal:

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

This starts PostgreSQL, Redis, the API, Prometheus at `:9090`, and Grafana at `:3001` with the Sentinel
dashboard provisioned. The React console remains a separate Node process so it can be deployed independently.

## Reproduce the demo and evaluation

```powershell
python -m pytest
python -m evals.runner --suite portfolio
python -m ml.telemetry_anomaly.train --quick
cd frontend
npm run lint
npm run build
```

The portfolio run executes all 36 seeded scenarios through the real Sentinel workflow, then replays captured
evidence through three baselines and five component ablations. Raw JSON/CSV, Markdown/HTML, plots, and five
failure analyses are committed under [`evals/reports/latest`](evals/reports/latest).

Latest checked-in portfolio results:

| System | Root-cause accuracy | Evidence precision / recall | Abstention | Unsafe actions |
|---|---:|---:|---:|---:|
| Direct alert baseline | 61.1% | 0.0% / 0.0% | 0.0% | 0 |
| Simple ReAct baseline | 44.4% | 22.2% / 7.4% | 55.6% | 0 |
| Simple graph baseline | 50.0% | 17.6% / 13.0% | 50.0% | 0 |
| **Sentinel** | **86.1%** | **62.4% / 69.4%** | **13.9%** | **0** |

Five cases did not clear the verifier’s corroboration threshold and were safely marked
`insufficient_evidence`. Those observed failures and their regression actions are documented in
[failure-analysis.md](evals/reports/latest/failure-analysis.md). The simpler z-score anomaly baseline also
currently beats the neural autoencoder on F1 (0.962 versus 0.917); [the evaluation notes](docs/evaluation.md)
explain why that limitation is intentionally visible.

## Safety invariants

- Read tools run under explicit allowlists; low-risk writes require approval; destructive actions are
  denied even when an approval flag is present.
- Approval tokens are HMAC-signed, actor/incident/remediation-scoped, nonce-bearing, and expiring.
- Prompt-injection-like log text is treated as untrusted evidence and removed from runtime context.
- Supported diagnoses cannot reference evidence that is absent from durable storage.
- Patch paths and content are sandboxed. Proposals never auto-merge or auto-execute.
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
- [Contributing](docs/contributing.md)
- [Resume-ready project bullets](docs/resume.md)

## License

[MIT](LICENSE)
