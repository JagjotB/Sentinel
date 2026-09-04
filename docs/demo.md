# Five-minute demo

1. Start the API and console using the README quick start. For the cluster-backed demo, run
   `python -m simulator.cluster bootstrap` first and confirm all workloads are ready.
2. Call `GET /v1/simulator/scenarios` and select `oom_killed_001`.
3. Call `POST /v1/simulator/run` with the local bearer token and body
   `{"scenario_id":"oom_killed_001"}`. The response should be `waiting_approval`, not resolved.
   To create the real Kubernetes failure first, call `POST /v1/simulator/cluster/inject` with the same
   payload, then inspect the resulting pod restart and OOM event with kubectl.
4. Show the task tree, evidence IDs, anomaly and clustered-log evidence, deployment diff, verifier result,
   and proposed memory-limit patch. Use evidence, tasks, and trace endpoints to show provenance.
5. Attempt a mutation without auth and point out the 401. Explain that destructive actions cannot be
   approved, while a low-risk proposal needs a scoped five-minute token and an actor decision.
6. Inspect `graph_path`, diagnosis/verifier model-call records, and typed tool calls. Explain that the legacy
   portfolio report is quarantined from resume claims until independent baselines are regenerated.
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
