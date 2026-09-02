# Sentinel measured evaluation

Generated `2026-09-02T08:53:00.653312+00:00` from 36 scenarios.
Each root-cause variant has a fixed independent seed. The runtime and model providers are deterministic, so one trial per variant is sufficient; no variance is concealed.

| System | Accuracy | Evidence P/R | Unsupported | Abstain | Remediation | Tools mean/p95 | Time mean/p95 ms | Cost |
|---|---:|---:|---:|---:|---:|---:|---:|---:|
| baseline_direct | 0.611 | 0.000/0.000 | 0.389 | 0.000 | 0.667 | 0.0/0.0 | 0.1/0.1 | $0.0000 |
| baseline_react | 0.444 | 0.222/0.074 | 0.000 | 0.556 | 1.000 | 3.0/3.0 | 69.0/79.5 | $0.0000 |
| baseline_graph | 0.500 | 0.176/0.130 | 0.000 | 0.500 | 1.000 | 6.8/9.0 | 181.2/208.6 | $0.0000 |
| sentinel_full | 0.861 | 0.624/0.694 | 0.000 | 0.139 | 1.000 | 8.8/11.0 | 287.6/331.0 | $0.0000 |
| ablation_no_verifier | 0.861 | 0.624/0.694 | 0.000 | 0.139 | 1.000 | 9.4/12.0 | 224.3/258.2 | $0.0000 |
| ablation_no_deep_learning | 0.806 | 0.615/0.704 | 0.033 | 0.167 | 0.967 | 7.4/10.0 | 224.3/258.2 | $0.0000 |
| ablation_no_retrieval | 0.611 | 0.231/0.111 | 0.083 | 0.333 | 1.000 | 8.8/11.0 | 224.3/258.2 | $0.0000 |
| ablation_no_context_engineering | 0.000 | 0.111/0.037 | 0.000 | 1.000 | 0.000 | 3.0/3.0 | 224.3/258.2 | $0.0000 |
| ablation_no_subagents | 0.000 | 0.111/0.074 | 0.000 | 1.000 | 0.000 | 0.0/0.0 | 92.0/105.9 | $0.0000 |

## Interpretation

The direct baseline makes claims without evidence by design. Evidence precision and recall therefore remain zero even when its title-only guess is correct. Human intervention for Sentinel means the approval gate was reached, not that diagnosis failed. Timing values are measured wall-clock runtime on the generating machine; derived baselines replay fixed subsets of the captured trace and report their proportional replay time.

Raw per-scenario rows are in `raw-results.json` and `raw-results.csv`. Five concrete error cases and regression actions are in `failure-analysis.md`.
