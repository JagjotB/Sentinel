FROM python:3.12-slim AS runtime
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1
WORKDIR /app
RUN groupadd --gid 10001 sentinel \
    && useradd --uid 10001 --gid sentinel --no-create-home --shell /usr/sbin/nologin sentinel
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
USER 10001:10001
EXPOSE 8000
CMD ["uvicorn", "api.main:app", "--host", "0.0.0.0", "--port", "8000"]
