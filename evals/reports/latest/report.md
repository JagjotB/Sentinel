# Sentinel independent evaluation

Protocol `independent-v2` generated `2026-09-05T05:10:05.778814+00:00` from 36 scenarios and 324 isolated executions.
Each system received the same immutable alert/scenario input in a fresh repository. Runtime snapshots contained no root-cause, expected-evidence, remediation, or forbidden-action evaluator fields.

| System | Accuracy | Selective acc. | Evidence P/R | Abstain | ECE/Brier | Remediation | Tools mean/p95 | Total time mean/p95 ms | Tokens in/out | Cost |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| baseline_direct | 0.611 | 0.611 | 0.000/0.000 | 0.000 | 0.111/0.250 | 0.667 | 0.0/0.0 | 0.1/0.1 | 0/0 | $0.0000 |
| baseline_react | 0.111 | 1.000 | 0.263/0.889 | 0.889 | 0.477/0.229 | 1.000 | 4.9/5.0 | 450.2/562.7 | 0/0 | $0.0000 |
| baseline_graph | 0.278 | 0.714 | 0.267/0.889 | 0.611 | 0.329/0.225 | 0.714 | 8.8/11.0 | 378.2/477.4 | 416095/4106 | $0.0000 |
| sentinel_full | 0.778 | 0.903 | 0.290/0.880 | 0.139 | 0.156/0.089 | 0.903 | 8.8/11.0 | 449.7/514.1 | 172753/6034 | $0.0000 |
| ablation_no_verifier | 0.778 | 0.903 | 0.290/0.880 | 0.139 | 0.156/0.089 | 0.903 | 8.8/11.0 | 427.6/515.0 | 90658/4514 | $0.0000 |
| ablation_no_deep_learning | 0.750 | 0.964 | 0.306/0.861 | 0.222 | 0.177/0.083 | 0.964 | 8.8/11.0 | 431.0/491.2 | 132340/5844 | $0.0000 |
| ablation_no_retrieval | 0.389 | 0.583 | 0.260/0.852 | 0.333 | 0.286/0.244 | 0.667 | 8.8/11.0 | 442.0/568.6 | 155676/5864 | $0.0000 |
| ablation_no_context_engineering | 0.778 | 0.903 | 0.290/0.880 | 0.139 | 0.156/0.089 | 0.903 | 8.8/11.0 | 455.8/516.8 | 889332/6034 | $0.0000 |
| ablation_no_subagents | 0.778 | 0.903 | 0.290/0.880 | 0.139 | 0.156/0.089 | 0.903 | 8.8/11.0 | 437.4/509.2 | 172753/6034 | $0.0000 |

## Protocol integrity

- Scenario catalog canonical JSON SHA-256: `fc452bdf7aa3a38110fdf1b4e298502d95592d9923a84ea7bb4df632400b8313`
- Retrieval training corpus SHA-256: `f18ccae5a08a3afe191f2c3ee529873afd9117dba2e33929826ccc00205c8097`
- Retrieval split SHA-256: `a83b62dd0b610e1e26124f8dd801c944d734e4b0bf57951045f2bcb2695e0122`
- System configuration SHA-256: `aeb0acb75cf95e02f2c307aeebc17c15e57878d8ef5262cd36b4927070b05903`
- Source revision: `9e06325e9f4aaa7ec08d4cf644c7df1d9c3137ab`
- Every row has a unique OpenTelemetry trace ID and measured wall-clock duration.
- Token, retry, latency, and cost totals come from that row's own persisted calls.
- The deterministic model provider incurs zero API cost; zero is a measurement, not an estimate copied between systems.

## Interpretation

The direct baseline deliberately makes unsupported title-only claims, so evidence precision and recall are zero even when its taxonomy match is correct. The ReAct baseline performs its own bounded sequential tool loop. The graph baseline executes an actual reduced LangGraph without learned evidence, retrieval, context ranking, or verification. Each ablation executes the production graph from scratch with exactly one named feature disabled.

Human intervention means a governed approval gate was reached, not that diagnosis failed. ECE and Brier score expose calibration rather than treating confidence as decoration. Raw per-trial rows are in `raw-results.json` and `raw-results.csv`; observed errors and regression actions are in `failure-analysis.md`.
