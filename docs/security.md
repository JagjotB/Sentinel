# Security and threat model

Sentinel assumes alerts, logs, metrics labels, traces, runbooks, retrieved documents, tool output, and model
output may be hostile. It assumes the API token, approval secret, database, host, and deployment pipeline
are trusted administrative boundaries. Local defaults are not production credentials.

## Enforced boundaries

1. Mutation endpoints require bearer authentication and idempotency keys.
2. Tools declare `read`, `low_risk_write`, or `destructive`. Reads are allowlisted, low-risk writes require
   scoped approval, and destructive tools are denied unconditionally.
3. Tool input is schema validated, size bounded, timed out, retried only when retryable, and logged with a
   request hash and stable evidence IDs.
4. Context assembly deduplicates evidence, caps tokens, strips secret patterns, and replaces instruction-like
   untrusted text before it reaches a model.
5. Supported diagnoses must cite IDs in their evidence collection. A verifier checks alternatives and may
   convert the result to `insufficient_evidence`.
6. Remediation output is only a patch or rollback proposal. The sandbox blocks traversal, shell payloads,
   binary content, namespace deletion, database deletion, and audit suppression.
7. Approval tokens bind actor, incident, remediation, expiry, and nonce. Decisions and policy denials enter
   the audit table.

## Deployment checklist

- Replace API token, approval secret, and database credentials with secret-manager values; never bake them
  into frontend code or container layers.
- Terminate TLS before the API, restrict CORS origins, and use the organization’s identity provider.
- Use the read-only Kubernetes service account in `infrastructure/kubernetes/namespace.yaml`.
- Encrypt database volumes, send audit logs to immutable storage, configure OTLP over TLS, and rotate keys.
- Re-run security tests, dependency audits, container scanning, and the complete evaluation before release.

Tests cover missing auth, forged/expired/mismatched approval tokens, prompt injection in logs, secret
redaction, traversal, destructive actions, oversized payloads, and forbidden shell content.
