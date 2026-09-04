FROM python:3.12-slim AS runtime
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1
WORKDIR /app
RUN addgroup --system sentinel && adduser --system --ingroup sentinel sentinel
COPY pyproject.toml README.md ./
COPY api ./api
COPY agents ./agents
COPY evals ./evals
COPY mcp ./mcp
COPY ml ./ml
COPY persistence ./persistence
COPY retrieval ./retrieval
COPY runtime ./runtime
COPY safety ./safety
COPY simulator ./simulator
RUN pip install --no-cache-dir ".[postgres]"
USER sentinel
EXPOSE 8080
CMD ["uvicorn", "simulator.services.demo_app:app", "--host", "0.0.0.0", "--port", "8080"]
