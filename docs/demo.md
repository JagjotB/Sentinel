# Five-minute demo

1. Start the API and console using the README quick start. For the cluster-backed demo, run
   `python -m simulator.cluster bootstrap` first and confirm all workloads are ready.
2. Call `GET /v1/simulator/scenarios` and select `oom_killed_001`.
3. Call `POST /v1/simulator/run` with the local bearer token and body
   `{"scenario_id":"oom_killed_001"}`. The response should be `waiting_approval`, not resolved.
   To create the real Kubernetes failure first, call `POST /v1/simulator/cluster/inject` with the same
   payload, then inspect the resulting pod restart and OOM event with kubectl.
4. In the console, select the incident and show the API-backed task tree, evidence IDs, anomaly and
   clustered-log evidence, deployment diff, verifier result, actual budget usage, and proposed patch.
5. Attempt a mutation without auth and point out the 401. Explain that destructive actions cannot be
   approved, while a low-risk proposal needs a scoped five-minute, single-use token and an actor decision.
   Approve the memory patch in the console and show the content-addressed artifact path; explain that
   Sentinel materializes the proposal but never applies or merges it automatically.
6. Open the benchmark view and show the `independent-v2` badge. Explain that the report contains 324
   isolated executions with unique trace IDs and measured timing. Sentinel reaches 77.8% overall and 90.3%
   selective root-cause accuracy at 13.9% abstention; the earlier 86.1% claim is rejected.
7. Run `pytest tests/resilience -q` to demonstrate durable checkpoints, timeout retry, circuit breaking, and
   deterministic provider fallback.
8. Call `POST /v1/simulator/cluster/reset` and show that canonical images, probes, selectors, resource
   limits, configuration, traffic rate, secrets, and network policies are restored.

Useful proof points:

```powershell
pytest tests/e2e tests/security tests/resilience -q
python -m evals.runner --suite portfolio
docker compose config --quiet
```

For the evidence behind the numbers, open `evals/reports/latest/report.html`, then drill into
`raw-results.csv` and `failure-analysis.md`. For a cluster-backed run, also open the matching trace in Tempo
through Grafana and correlate it with the incident's persisted task/tool records.
