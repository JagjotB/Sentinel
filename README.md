# Sentinel

Sentinel is an evidence-backed reliability engineering platform that investigates reproducible incidents
across Kubernetes state, telemetry, logs, deployments, runbooks, and prior incidents. A custom durable
runtime coordinates specialized agents, enforces budgets and permissions, validates every diagnosis against
stored evidence, and requires human approval before any low-risk write.

> This repository is under active build. The deterministic local path never requires paid model access.

## Quick start

```bash
python -m venv .venv
.venv/Scripts/pip install -e ".[dev]"   # Windows
python -m simulator.bootstrap --materialize
python -m ml.telemetry_anomaly.train --quick
uvicorn api.main:app --reload
```

In another terminal:

```bash
cd frontend
npm install
npm run dev
```

Open `http://localhost:3000` for the operator dashboard and `http://localhost:8000/docs` for the API.

The complete architecture, evaluation methodology, safety model, demo script, measured benchmark results,
and repository map are developed in `docs/` as the implementation milestones land.

