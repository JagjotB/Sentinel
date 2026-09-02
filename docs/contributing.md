# Contributing

Create a focused branch, preserve deterministic scenario seeds, and keep commits independently reviewable.
New behavior needs the lowest relevant test layer plus an end-to-end scenario when it changes a decision.
Never update a checked-in metric by hand: run the generator and commit raw and rendered outputs together.

Before opening a change:

```powershell
ruff check .
mypy api agents evals mcp ml persistence retrieval runtime safety simulator
pytest --cov=api --cov=agents --cov=runtime --cov=mcp --cov=safety --cov-report=term-missing
cd frontend
npm run lint
npm run build
npm audit --omit=dev --audit-level=high
```

Add fault types to the catalog source, materialize it, and document expected evidence, acceptable
remediations, and forbidden actions. Tool additions require typed input/output, permission class,
authentication, timeout/retry behavior, evidence provenance, audit logging, and contract tests.
