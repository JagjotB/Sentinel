# Sentinel

[![CI](https://github.com/JagjotB/Sentinel/actions/workflows/ci.yml/badge.svg?branch=build-sentinel)](https://github.com/JagjotB/Sentinel/actions/workflows/ci.yml)
[![Python 3.12+](https://img.shields.io/badge/Python-3.12%2B-3776AB?logo=python&logoColor=white)](pyproject.toml)
[![Node 22.13+](https://img.shields.io/badge/Node-22.13%2B-5FA04E?logo=nodedotjs&logoColor=white)](frontend/package.json)
[![LangGraph](https://img.shields.io/badge/orchestration-LangGraph-19C37D)](https://github.com/langchain-ai/langgraph)
[![License: MIT](https://img.shields.io/badge/license-MIT-8B5CF6)](LICENSE)

**Evidence-backed incident investigation for Kubernetes—built to prove its diagnosis before asking a
human to approve a change.**

[Hosted read-only showcase](https://sentinel-reliability.jagjot5.chatgpt.site) ·
[Five-minute demo](docs/demo.md) ·
[Architecture](docs/architecture.md) ·
[Measured evaluation](evals/reports/latest/report.md)

![Sentinel evidence graph](frontend/public/og.png)

Sentinel receives an alert, dynamically schedules specialist agents, correlates Kubernetes state,
Prometheus metrics, logs, Git changes, and prior incidents, and then produces either a cited diagnosis or
an explicit abstention. Any proposed write passes policy validation, a scoped approval token, and a human
decision. Sentinel never auto-applies or auto-merges a patch.

## See one investigation

For `oom_killed_001`, Sentinel follows this evidence chain:

1. The infrastructure agent confirms a real pod termination with reason `OOMKilled` and exit code 137.
2. The telemetry agent finds the working set at the container limit and correlates allocation failures.
3. The change agent identifies the commit that reduced the payments memory limit.
4. Retrieval finds a similar incident, but the retrieved answer is supporting evidence—not a runtime label.
5. The diagnosis agent cites durable evidence IDs; the verifier challenges its provenance and alternatives.
6. Sentinel proposes restoring the limit as a reversible patch and pauses at `waiting_approval`.

The public showcase renders this completed flow without credentials. A local run executes the real API,
durable worker, LangGraph workflow, tools, and approval boundary.

## Why this is more than a chatbot

| Capability | What is implemented |
|---|---|
| Agent runtime | Compiled LangGraph state machine, dynamic task scheduling, parallel specialists, conditional verifier routing, checkpoint-aware recovery, loop protection, and hard execution budgets |
| Evidence | Typed, authenticated, timeout-bounded providers for Kubernetes, Prometheus/Tempo, Git, and incident knowledge; tool outputs and provenance are persisted |
| Safety | Read-by-default permissions, destructive-action denial, HMAC-signed incident/remediation/actor-scoped approval tokens, idempotency, sandboxed patch artifacts, and a complete audit trail |
| Simulator | 36 seeded scenarios across 18 root causes plus buildable service images, traffic generation, namespace-scoped kind injection, observation, and reset controls |
| ML and retrieval | Trained temporal autoencoder, learned log representations and clustering, hybrid BM25/vector retrieval, and a trained pairwise incident reranker |
| Operations | FastAPI, SQLAlchemy, SQLite/PostgreSQL, database-backed worker leases, OTLP traces, Prometheus metrics, Tempo, Grafana, and an API-backed React console |
| Verification | Unit, contract, integration, agent, ML, security, resilience, E2E, supply-chain, frontend, and live kind fault gates in CI |

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
  D --> V[Independent verifier]
  V -->|weak or contradictory| X[Abstain / escalate]
  V -->|supported| P[Sandboxed proposal]
  P --> G[Policy gate]
  G --> H[Scoped human approval]
  R --> O[OTLP trace · metrics · audit]
```

Sentinel uses a **custom hierarchical deep-agent architecture built directly with LangGraph and
LangChain**. It does not depend on the LangChain Deep Agents SDK. Its operational providers form an
**in-process, MCP-compatible tool layer** with typed schemas and permission metadata; this repository does
not claim that those providers are deployed as standalone MCP transports.

The deterministic local model follows the same production-oriented graph and persistence path without a
paid service. Install `.[models]` and configure `SENTINEL_MODEL_PROVIDER` and `SENTINEL_MODEL_NAME` to use a
supported hosted model. See [ADR 0001](docs/decisions/0001-portable-local-control-plane.md) and
[ADR 0002](docs/decisions/0002-langgraph-langchain-runtime.md).

## Run it locally

Python 3.12+ and Node 22.13+ are required.

```powershell
python -m venv .venv
.venv\Scripts\Activate.ps1
python -m pip install -e ".[dev]"
cd frontend
npm ci
cd ..
python scripts/demo.py
```

That last command materializes deterministic fixtures, then starts the API, durable investigation worker,
and operator console together. Open `http://localhost:3000`; API documentation is at
`http://127.0.0.1:8000/docs`. Use `python scripts/demo.py --check` to validate prerequisites without
starting services and `--no-browser` in headless environments.

Mutating local API requests require `Authorization: Bearer sentinel-local-token`. Replace all defaults
outside local development.

### Container and real-cluster paths

```bash
docker compose up --build
```

Compose starts PostgreSQL, Redis, the API, durable worker, OTLP Collector, Tempo, Prometheus, and Grafana.
The independently deployable console remains a Node process.

To exercise real Kubernetes failure injection, install Docker, kind, and kubectl:

```powershell
python -m simulator.cluster bootstrap
python -m simulator.cluster status
curl.exe -X POST http://localhost:8000/v1/simulator/cluster/inject `
  -H "Authorization: Bearer sentinel-local-token" `
  -H "Content-Type: application/json" `
  -d '{"scenario_id":"oom_killed_001"}'
```

Sentinel can then investigate the running namespace through real `kubectl`, Prometheus, Tempo, Git, and
incident adapters via `POST /v1/simulator/cluster/investigate`. Reset with
`POST /v1/simulator/cluster/reset`. See the [simulator runbook](docs/simulator.md) and
[live integration guide](docs/live-integrations.md).

## Measured evaluation

The checked-in `independent-v2` report contains 324 isolated executions: nine systems across 36 seeded
synthetic incidents. Each trial receives a fresh repository and unique trace ID and records its own wall
time, tool calls, tokens, retries, and cost.

| Metric | Sentinel |
|---|---:|
| Overall root-cause accuracy | **77.8%** |
| Selective accuracy | **90.3%** |
| Abstention rate | **13.9%** |
| Evidence recall | **88.0%** |
| Policy safety | **100%** |

These are deterministic simulator results, not production-SRE claims. The offline model incurred no API
cost. Evaluator labels are excluded from runtime snapshots, the retrieval index uses training variants
only, and the active incident is excluded from retrieval. Removing retrieval reduced overall accuracy to
38.9%; context engineering preserved accuracy while reducing suite input from 889,332 to 172,753 tokens.

The earlier 86.1% figure is explicitly rejected because its comparison systems reused full-run evidence
and its timings were estimated. Read the [protocol and limitations](docs/evaluation.md),
[human-readable report](evals/reports/latest/report.md),
[raw per-trial rows](evals/reports/latest/raw-results.csv), and
[failure analysis](evals/reports/latest/failure-analysis.md).

Reproduce the suite and core checks:

```powershell
python -m pytest
python -m evals.runner --suite portfolio
python -m ml.telemetry_anomaly.train --quick
cd frontend
npm run lint
npm run build
```

## Safety invariants

- Supported diagnoses cannot cite evidence absent from durable storage.
- Prompt-injection-like log text is treated as untrusted evidence and removed from model context.
- Approval tokens are signed, expiring, nonce-bearing, single-use, and scoped to actor, incident, and
  remediation.
- Destructive actions remain denied even when an approval flag is present.
- Proposal paths and content are sandboxed; no agent can auto-apply, auto-merge, or execute a shell patch.
- Secrets are redacted from context and fixtures; tool/model calls, denials, and decisions are auditable.

Read the [threat model](docs/security.md) before connecting live credentials.

## Repository map

| Path | Purpose |
|---|---|
| `agents/` | Supervisor and specialist evidence, diagnosis, verifier, and remediation agents |
| `runtime/` | Durable state, checkpoints, budgets, resilience, routing, memory, permissions, and tracing |
| `mcp/` | MCP-compatible typed tool contracts and simulator/live providers |
| `simulator/` | Scenario catalog, services, traffic, kind lifecycle, fault injection, observation, and reset |
| `ml/`, `retrieval/` | Telemetry model, log intelligence, hybrid retrieval, reranker, and artifacts |
| `api/`, `persistence/`, `safety/` | Control plane, records/migrations, approvals, policy, and sandbox boundaries |
| `frontend/` | API-backed operator console, hosted showcase fallback, and benchmark view |
| `evals/` | Independent baselines, ablations, metrics, raw rows, reports, and failures |
| `infrastructure/` | Docker, Kubernetes, Prometheus, OTLP, Tempo, and Grafana configuration |
| `tests/` | Unit through E2E, security, resilience, agent, ML, and contract suites |

## Documentation

[Demo](docs/demo.md) · [Acceptance evidence](docs/acceptance.md) ·
[Operations](docs/operations.md) · [Security](docs/security.md) ·
[Contributing](docs/contributing.md) · [Resume bullets](docs/resume.md)

## License

[MIT](LICENSE)
