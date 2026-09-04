.PHONY: install bootstrap cluster-up cluster-status cluster-reset cluster-down api ui test lint typecheck eval train clean

install:
	python -m pip install -e ".[dev,postgres]"

bootstrap:
	python -m simulator.bootstrap --materialize
	python -m ml.telemetry_anomaly.train --quick

cluster-up:
	python -m simulator.cluster bootstrap

cluster-status:
	python -m simulator.cluster status

cluster-reset:
	python -c "from simulator.faults.kubernetes import KubernetesFaultController; KubernetesFaultController().reset()"

cluster-down:
	python -m simulator.cluster delete

api:
	uvicorn api.main:app --reload --port 8000

ui:
	cd frontend && npm run dev

test:
	pytest

lint:
	ruff check .

typecheck:
	mypy api agents evals mcp ml persistence retrieval runtime safety simulator

eval:
	python -m evals.runner --suite portfolio

train:
	python -m ml.telemetry_anomaly.train

clean:
	python scripts/clean.py
