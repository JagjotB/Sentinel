# Architecture

Sentinel places a deterministic control plane around probabilistic or learned components.

```mermaid
flowchart TD
  A[Alert API] --> R[Durable Runtime]
  R --> S[Supervisor]
  S --> I[Infrastructure agent]
  S --> T[Telemetry agent]
  S --> C[Change agent]
  S --> K[Knowledge agent]
  I & T & C & K --> E[(Evidence store)]
  E --> D[Diagnosis]
  D --> V[Verifier]
  V -->|supported| P[Remediation planner]
  V -->|weak/contradictory| X[Abstain or escalate]
  P --> G[Policy gate]
  G --> H[Human approval]
  R --> O[Trace + metrics + audit]
```

## Boundaries

- `api/` exposes incident, evidence, trace, approval, simulator, and benchmark resources.
- `runtime/` owns state transitions, budgets, retries, checkpointing, context, tool policy, and tracing.
- `agents/` contains the supervisor and evidence-specialized roles.
- `mcp/` provides typed, MCP-shaped Kubernetes, observability, Git, and incident tools.
- `ml/` trains and serves anomaly, log-intelligence, and reranking components.
- `persistence/` is the only module allowed to mutate durable incident state.
- `safety/` validates proposed actions before and after model generation.

Every claim in a supported diagnosis references stable evidence IDs. Agent-generated text is data, never a
host command. All writes are classified before execution; destructive actions cannot be approved.

