# Evaluation protocol

Sentinel’s portfolio suite is an executable benchmark, not a manually curated table. The runner loads all
36 scenarios from `simulator/scenarios/catalog.json`, creates a fresh SQLite database, executes each
scenario through `InvestigationService`, and preserves each trace ID in the benchmark record. Baselines
and ablations operate on the same captured evidence so comparisons do not benefit from different faults.

## Dataset and trials

The catalog contains two seeded variants for each of 18 root causes. Variants differ in telemetry noise,
anomaly onset, and difficulty. All local providers are deterministic; therefore the checked-in run uses one
trial per independent variant and reports that choice rather than inventing variance. If a nondeterministic
model adapter is added, the runner must repeat every scenario across at least three seeds and report
dispersion.

The telemetry model separates scenario IDs before constructing training, validation, and held-out test
windows. The reranker trains on versioned corpus pairs and evaluates on held-out queries. Expected labels
are used only for scoring after a run.

## Systems compared

- `baseline_direct`: title/label overlap, no tools and no evidence.
- `baseline_react`: a small event/log/change subset and a single diagnosis pass.
- `baseline_graph`: multi-source deterministic graph without learned evidence, retrieval, or verifier.
- `sentinel_full`: complete runtime, dynamic agent hierarchy, learned components, verifier, sandbox, and
  approval boundary.
- Ablations remove the verifier, deep learning, retrieval, context engineering, or specialized subagents.

Metrics include root-cause accuracy, evidence precision/recall, unsupported supported-claim rate,
abstention, remediation correctness, policy safety, tool calls, wall-clock diagnosis time, provider tokens,
cost, and human approval-gate rate. Recovery and provider-failure behavior is tested under
`tests/resilience`.

## Results and limitations

Sentinel resolves 31 of 36 scenarios correctly (86.1%) and abstains on the other five; it records no wrong
supported claim in this run. Removing retrieval reduces accuracy to 61.1%, while removing learned evidence
reduces it to 80.6%. The full numeric report and raw rows are in `evals/reports/latest`.

The learned telemetry model reaches 0.917 held-out F1, while the z-score baseline reaches 0.962. Synthetic
faults are structurally simple, so this is a credible result rather than a reason to hide the baseline. The
neural model remains valuable for learned reconstruction, dimension attribution, and a clear production
extension point, but this benchmark does not prove production superiority. The simulator cannot represent
credential failures, real control-plane races, or organization-specific runbook quality.

Do not compare proportional replay timing for derived baselines with an independent service benchmark.
Only Sentinel’s wall-clock value executes the entire workflow; baseline timing describes replay work over
its captured trace. Re-run the suite on the target machine for capacity planning.
