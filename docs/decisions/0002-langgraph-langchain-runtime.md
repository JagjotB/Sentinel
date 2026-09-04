# ADR 0002: LangGraph orchestration and LangChain integration

- Status: accepted
- Date: 2026-09-04

## Context

Sentinel originally described a custom agent runtime, but the production workflow directly called a Python
supervisor loop. Model routing was exercised only by resilience tests, tool calls bypassed standard agent
tool interfaces, and framework experience could not be demonstrated honestly.

## Decision

The incident workflow is a compiled LangGraph `StateGraph` with explicit evidence, diagnosis, verification,
remediation, and abstention stages. Sentinel's checksummed SQL checkpoints remain the durable system of
record, with a graph stage and path stored after each node for restart routing.

Diagnosis and verification use LangChain prompt, chat-model, callback, and Pydantic output-parser interfaces.
Tool servers are exposed to agents as LangChain `StructuredTool` instances without weakening Sentinel's
authorization, budgets, persistence, or safety policies. A deterministic model provider remains the default
for reproducible offline tests; supported hosted providers can be enabled through configuration.

## Consequences

- Claims that Sentinel uses LangChain and LangGraph refer to the actual API execution path and are tested.
- The graph topology and conditional safety edge are inspectable independently of UI claims.
- Every diagnosis and verification model call produces an auditable database record and token metric.
- The deterministic provider proves orchestration and contracts, not hosted-model quality. Hosted-provider
  benchmark claims require separate, repeated evaluation runs.
