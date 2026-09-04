# Five-minute demo

1. Start the API and console using the README quick start. Open the console and API docs side by side.
2. Call `GET /v1/simulator/scenarios` and select `oom_killed_001`.
3. Call `POST /v1/simulator/run` with the local bearer token and body
   `{"scenario_id":"oom_killed_001"}`. The response should be `waiting_approval`, not resolved.
4. Show the task tree, evidence IDs, anomaly and clustered-log evidence, deployment diff, verifier result,
   and proposed memory-limit patch. Use evidence, tasks, and trace endpoints to show provenance.
5. Attempt a mutation without auth and point out the 401. Explain that destructive actions cannot be
   approved, while a low-risk proposal needs a scoped five-minute token and an actor decision.
6. Inspect `graph_path`, diagnosis/verifier model-call records, and typed tool calls. Explain that the legacy
   portfolio report is quarantined from resume claims until independent baselines are regenerated.
7. Run `pytest tests/resilience -q` to demonstrate durable checkpoints, timeout retry, circuit breaking, and
   deterministic provider fallback.

Useful proof points:

```powershell
pytest tests/e2e tests/security tests/resilience -q
python -m evals.runner --suite portfolio
docker compose config --quiet
```
