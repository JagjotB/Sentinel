# Evaluation protocol

Sentinel's checked-in portfolio report uses protocol `independent-v2`. It loads all 36 scenarios from
`simulator/scenarios/catalog.json` and executes nine systems independently through the same evaluator:
three baselines, the full system, and five feature ablations. Every one of the 324 trials starts with a fresh
SQLite repository, receives the same immutable alert-time input, creates its own OpenTelemetry trace ID,
and records actual wall-clock duration and persisted tool/model usage. No full-system evidence is replayed
into another system.

The earlier 86.1% result is rejected historical output. It reused evidence from the full run and estimated
several replay latencies, so it must not be quoted.

## Dataset and trials

The catalog contains two seeded variants for each of 18 root causes. Variants differ in telemetry noise,
anomaly onset, and difficulty. All local providers are deterministic; therefore the checked-in run uses one
trial per independent variant and reports that choice rather than inventing variance. If a nondeterministic
model adapter is added, the runner must repeat every scenario across at least three seeds and report
dispersion.

The telemetry model separates scenario IDs before constructing training, validation, and held-out test
windows. The reranker now trains on variant-1 incidents and evaluates on variant-2 queries against a corpus
containing no held-out incident documents. Runtime retrieval excludes the active scenario. Queries are
constructed only from service and alert title; root cause, expected evidence, and remediation labels are not
available to query construction. The artifact records both split IDs and a training-corpus checksum.

## Systems compared

- `baseline_direct`: title/label overlap, no tools and no evidence.
- `baseline_react`: a small event/log/change subset and a single diagnosis pass.
- `baseline_graph`: multi-source deterministic graph without learned evidence, retrieval, or verifier.
- `sentinel_full`: complete runtime, dynamic agent hierarchy, learned components, verifier, sandbox, and
  approval boundary.
- Ablations remove the verifier, deep learning, retrieval, context engineering, or specialized subagents.

Metrics include overall and selective root-cause accuracy, evidence precision/recall, unsupported-claim
rate, abstention, calibration (ECE and Brier score), remediation correctness, policy safety, tool calls,
full-run and diagnosis-only wall time, provider tokens, retries, estimated cost, and approval-gate rate.
Recovery and provider-failure behavior is tested separately under `tests/resilience`.

## Current results

The current report was generated from source revision
`9e06325e9f4aaa7ec08d4cf644c7df1d9c3137ab`. Sentinel full-system results are:

| Measure | Result |
|---|---:|
| Overall root-cause accuracy | 77.8% (28/36) |
| Selective accuracy | 90.3% (28/31 non-abstained) |
| Abstention rate | 13.9% (5/36) |
| Evidence precision / recall | 29.0% / 88.0% |
| ECE / Brier score | 15.6% / 0.0889 |
| Remediation accuracy on supported diagnoses | 90.3% |
| Policy safety | 100% |
| Tool calls, mean / p95 | 8.78 / 11 |
| Total latency, mean / p95 | 449.71 ms / 514.11 ms |
| Diagnosis-task latency, mean / p95 | 118.73 ms / 142.93 ms |
| Model tokens, input / output | 172,753 / 6,034 |
| Model calls / measured API cost | 72 / $0.00 |

The direct, ReAct, and reduced-graph baselines measured 61.1%, 11.1%, and 27.8% overall accuracy. Retrieval
was the largest measured accuracy contributor: removing it reduced accuracy to 38.9%. Removing context
engineering did not change accuracy on this suite but increased input tokens from 172,753 to 889,332.
Removing the learned telemetry evidence reduced accuracy from 77.8% to 75.0%. The verifier and subagent
ablations matched aggregate accuracy, so this run does not support an accuracy-lift claim for those
components; they remain architectural controls for contradiction handling and execution topology.

## Reproducibility and limitations

Run `python -m evals.runner --suite portfolio` to replace `evals/reports/latest`. The manifest records source,
catalog, retrieval corpus, split, and system-configuration hashes. Raw JSON and CSV rows provide one trace
ID per trial; the report includes at least five concrete failure analyses.

The learned telemetry model reaches 0.917 held-out F1, while the z-score baseline reaches 0.962. Synthetic
faults are structurally simple, so this is a credible result rather than a reason to hide the baseline. The
neural model remains valuable for learned reconstruction, dimension attribution, and a clear production
extension point, but this benchmark does not prove production superiority. The simulator cannot represent
credential failures, real control-plane races, or organization-specific runbook quality.

Because the local providers are deterministic, the report uses one seeded trial for each independently
defined scenario variant and does not invent confidence intervals. A nondeterministic provider must use at
least three seeds and report dispersion. These results demonstrate this repository's synthetic benchmark;
they are not evidence of production incident accuracy or superiority over hosted models.
