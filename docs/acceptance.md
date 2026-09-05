# Master-plan acceptance evidence

This matrix maps the Sentinel Codex Master Build Plan's final definition of done to inspectable repository
evidence. It distinguishes implementation and deterministic verification from host-dependent live checks.

| Requirement | Repository evidence | Verification |
|---|---|---|
| Documented local bootstrap | `README.md`, `.env.example`, `compose.yaml`, `simulator/bootstrap.py` | CI materializes fixtures, validates Compose, and builds all service images |
| Instrumented Kubernetes simulator and deterministic faults | `infrastructure/kubernetes`, `simulator/cluster.py`, `simulator/faults/kubernetes.py`, `docs/simulator.md` | Unit/contract tests validate every scenario's namespace-scoped plan; CI deploys a real kind cluster, injects and observes an OOM fault, resets all workloads, and tears it down |
| 30+ ground-truth scenarios and 10+ classes | `simulator/scenarios/catalog.json` | 36 scenarios across 18 root-cause classes; runtime snapshots explicitly exclude evaluator-only fields |
| API, persistence, and incident lifecycle | `api`, `persistence`, `runtime/worker.py` | Integration and E2E tests exercise ingestion through approval and checkpoint recovery |
| Custom harness | `runtime` | Durable executions/tasks/checkpoints, budgets, retries, loop protection, policy, model routing, memory, context, and tracing are unit/integration tested |
| Hierarchical deep-agent workflow | `agents`, `runtime/graph.py` | Compiled LangGraph dynamically schedules specialists within the custom harness; agent tests assert graph paths and durable calls |
| Kubernetes, observability, Git, and incident tools | `mcp/*/live.py`, `docs/live-integrations.md` | Typed contract tests cover live-adapter command/HTTP behavior, permission classes, partial responses, timeouts, and audit records |
| Telemetry neural model | `ml/telemetry_anomaly` | Trained artifact, held-out evaluation, deterministic inference, and live investigation evidence; neural F1 0.917 vs z-score 0.962 |
| Log intelligence | `ml/log_intelligence` | Learned vectorization, clustering, ranking, and compression tests; integrated evidence reduces prompt context |
| Historical retrieval and reranking | `retrieval`, `ml/incident_reranker` | Label-isolated train/test split, provenance, hybrid retrieval, reranking comparison, and checksums |
| Structured diagnoses and verifier | `agents/diagnosis.py`, `agents/verifier.py`, `runtime/graph.py` | Schema validation, evidence-ID existence checks, contradictions, abstention, and conditional verifier routing are tested |
| Governed remediation | `safety`, `runtime/remediation_executor.py`, API approval routes | Read-by-default, signed scoped single-use approval, destructive denial, sandboxed patch artifact, no auto-apply/merge |
| End-to-end observability | `runtime/tracing.py`, `infrastructure/otel`, `infrastructure/tempo`, Grafana dashboard | In-memory integration tests assert alert-to-worker parent/child continuity and model/tool/runtime spans; Compose wires OTLP Collector to Tempo |
| Operator console | `frontend/app`, `frontend/lib/api.ts` | API-backed incident list/detail, task/evidence timeline, hypotheses, verifier, tool/model trace, approval controls, and benchmark page; lint/build gate |
| Complete test layers | `tests/unit`, `contract`, `integration`, `ml`, `agent`, `e2e`, `resilience`, `security` | Full pytest suite plus Ruff and strict MyPy in CI |
| Independent evaluation and ablations | `evals/runner.py`, `evals/reports/latest` | 324 isolated executions, three baselines, full system, five real feature ablations, unique trace IDs, measured wall time/tokens/retries/cost |
| Real benchmark and failures | `evals/reports/latest/report.md`, `raw-results.csv`, `failure-analysis.md` | 77.8% overall / 90.3% selective accuracy with 13.9% abstention; five measured failures analyzed |
| CI and supply-chain gates | `.github/workflows/ci.yml` | Python lint/type/test/eval smoke, frontend lint/build/audit, pip audit, Compose validation, all container builds, and real kind fault/reset smoke |
| Documentation and portfolio assets | `README.md`, `docs`, `evals/reports/latest`, `frontend/public/og.png` | Architecture, ADRs, evaluation, demo, operations, threat model, simulator, integrations, resume bullets, reports, and social preview are checked in |
| Commit discipline and clean tree | Git history | Coherent milestone commits are pushed to `build-sentinel`; final handoff records the resulting status |

## Host-dependent live acceptance

The following commands exercise the real infrastructure path and should be rerun on any host with a
responsive Docker daemon:

```powershell
python -m simulator.cluster bootstrap
python -m simulator.cluster status
docker compose up --build -d
pytest tests/e2e tests/resilience tests/security -q
```

Then inject a scenario through `POST /v1/simulator/cluster/inject`, investigate it through
`POST /v1/simulator/cluster/investigate`, approve the generated low-risk artifact in the console, inspect the
shared trace in Grafana/Tempo, and call `POST /v1/simulator/cluster/reset`. The local deterministic test path
does not require Docker or hosted-model credentials; a live cluster and OTLP backend do.
