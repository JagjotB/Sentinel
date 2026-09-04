# Kubernetes incident simulator

Sentinel's cluster simulator is a real kind workload, separate from the deterministic in-memory fixtures
used by fast tests. It contains four HTTP services, PostgreSQL, and a continuous traffic generator:

```text
traffic-generator -> checkout -> payments -> PostgreSQL
                  \-> worker (queue scenarios)
frontend -> externally reachable NodePort :30080
```

Every HTTP service emits structured JSON logs and Prometheus request, latency, readiness, and queue metrics.
The checkout-to-payments call and payments-to-PostgreSQL operation are real network/database operations.

## Bootstrap and lifecycle

Requirements: a running Docker daemon plus `kind` and `kubectl` on `PATH`.

```powershell
python -m simulator.cluster bootstrap
python -m simulator.cluster status
python -m simulator.cluster delete
```

Bootstrap creates the `sentinel` kind cluster when needed, builds both local images, loads them into kind,
applies the canonical manifests, and waits for every deployment and StatefulSet. Re-running bootstrap is
idempotent.

Fault and reset operations are confined to `sentinel-demo`; commands use argument arrays and never invoke a
shell. The controller resets the environment before each injection so trials do not inherit prior faults.

## Fault mapping

| Root cause | Real cluster mutation or behavior |
|---|---|
| `oom_killed` | 96 MiB payments limit plus a 192 MiB allocation under traffic |
| `cpu_throttling` | 20m checkout CPU limit plus CPU-bound work |
| `memory_leak` | bounded container plus retained allocations per request |
| `disk_pressure` | constrained worker ephemeral storage plus repeated writes |
| `bad_readiness_probe` | checkout readiness path patched to a nonexistent endpoint |
| `bad_configmap` | invalid payments URL applied through ConfigMap and rollout |
| `missing_secret` | payments references an absent Secret key |
| `image_pull_failure` | worker image patched to an unavailable tag |
| `selector_mismatch` | frontend Service selector patched away from its pods |
| `dns_failure` | checkout dependency hostname changed to an unresolvable name |
| `dependency_timeout` | payments delay exceeds checkout's client timeout |
| `network_policy_denied` | namespace-scoped checkout egress-deny NetworkPolicy |
| `db_pool_exhaustion` | one-connection payments pool held under concurrent traffic |
| `slow_query_lock` | PostgreSQL operations held with `pg_sleep` under traffic |
| `bad_environment` | invalid feature configuration makes checkout unready |
| `dependency_regression` | checkout rejects the traffic generator's v1 schema |
| `queue_saturation` | worker service slowed while traffic rate rises to 20 rps |
| `downstream_rate_limit` | payments enforces a two-request-per-second limit under 15 rps |

The 36 catalog scenarios resolve to 18 concrete, importable injector functions. Variant IDs use the same
mutation class with different deterministic evaluation data.

## API

Both endpoints require the configured Sentinel bearer token:

- `POST /v1/simulator/cluster/inject` with `{"scenario_id":"<catalog id>"}`
- `POST /v1/simulator/cluster/reset`

Injection returns a receipt containing the scenario, root cause, exact argv operations, and a post-injection
resource observation. Reset waits for the canonical workloads to become ready.
