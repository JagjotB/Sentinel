# Live investigation adapters

Sentinel can run the same LangGraph investigation against either deterministic simulator providers or
live, read-only infrastructure. Set `SENTINEL_TOOL_PROVIDER=live` to make ordinary simulator-run requests
use live tools, or call `POST /v1/simulator/cluster/investigate` to select them for one request.

## Configuration

| Setting | Purpose |
|---|---|
| `SENTINEL_KUBERNETES_NAMESPACE` | The only namespace the Kubernetes adapter may read |
| `SENTINEL_KUBECTL_CONTEXT` | Optional explicit kubeconfig context |
| `SENTINEL_PROMETHEUS_URL` | Prometheus HTTP API base URL |
| `SENTINEL_TEMPO_URL` | Optional Tempo HTTP API base URL for trace lookup |
| `SENTINEL_GIT_REPOSITORY_PATH` | Local Git working tree used for change evidence |
| `SENTINEL_GITHUB_REPOSITORY` | Optional `owner/repository` for pull-request metadata |
| `SENTINEL_GITHUB_TOKEN` | Optional GitHub API token; never place it in source control |

The Kubernetes adapter constructs argv arrays and invokes `kubectl` without a shell. Every request is
checked against the configured namespace before invocation. It exposes pod, event, deployment, rollout,
service, configuration, resource-limit, and namespace-health evidence.

The observability adapter executes instant and range PromQL queries through Prometheus, reads workload logs
with namespace-scoped `kubectl logs`, retrieves alerts and SLO inputs, and reads a trace from Tempo when it
is configured. A missing Tempo endpoint is returned as explicit partial evidence rather than fabricated
spans.

The Git adapter reads the configured local repository and optionally reads GitHub pull-request metadata.
Its only write creates a content-addressed patch proposal below `.sentinel/proposals`; it remains blocked
unless a tool context carries a valid approval decision. It does not apply, commit, push, merge, or execute
the proposal.

The incident adapter searches durable Sentinel incidents and checked-in runbooks. Neither live nor
simulator retrieval returns active scenario IDs, ground-truth root-cause labels, or evaluator metadata.

## Verification scope

Contract tests exercise provider responses, command construction, namespace denial, evidence provenance,
write approval, and evaluator-label isolation. A real cluster smoke test additionally requires Docker,
kind, and `kubectl`; run the cluster bootstrap in the simulator runbook before treating that environment as
live-validated.
