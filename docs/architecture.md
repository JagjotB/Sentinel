# Architecture

Sentinel places a deterministic, auditable control plane around probabilistic or learned components.

```mermaid
flowchart TD
  A[Alert API] --> R[Durable Runtime]
  R --> LG[LangGraph state machine]
  LG --> S[Supervisor]
  S --> I[Infrastructure agent]
  S --> T[Telemetry agent]
  S --> C[Change agent]
  S --> K[Knowledge agent]
  I & T & C & K --> E[(Evidence store)]
  E --> D[LangChain diagnosis chain]
  D --> V[LangChain verifier chain]
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

## Orchestration and model path

`SupervisorAgent` compiles a real LangGraph `StateGraph` named `sentinel-investigation`. Its nodes are
`initialize`, `collect_evidence`, `diagnose`, `verify`, `remediate`, and `abstain`. Verification uses a
conditional edge, so unsupported diagnoses cannot reach remediation. Infrastructure, telemetry,
change-analysis, and retrieval specialists execute concurrently inside the evidence-collection stage.

After every graph node, Sentinel writes its validated `RuntimeState` to the checksummed checkpoint store and
records `graph_stage` plus the traversed path. An interrupted execution re-enters the compiled graph at the
node following the last durable stage instead of replaying the full investigation.

Diagnosis and verification use LangChain Expression Language pipelines:

```text
ChatPromptTemplate -> RoutedChatModel -> PydanticOutputParser -> policy/provenance validation
```

The default `RoutedChatModel` delegates to Sentinel's deterministic provider for reproducible offline tests.
The same `ModelRouter` can initialize any supported LangChain chat provider, including Google Vertex AI and
OpenAI integrations installed through the `models` extra. Provider failures route to the explicit,
auditable deterministic fallback. Model identity, prompt version, input/output tokens, cost, duration, and
retry count are stored for every call.

All investigation tools cross a LangChain `StructuredTool` boundary before reaching `ToolRegistry`. Pydantic
input schemas, Sentinel authorization, call budgets, persistence, evidence provenance, and the destructive
action deny policy remain authoritative; LangChain never bypasses those controls.
