FROM python:3.12-slim AS runtime
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1
WORKDIR /app
RUN addgroup --system sentinel && adduser --system --ingroup sentinel sentinel
COPY pyproject.toml README.md ./
COPY simulator ./simulator
RUN pip install --no-cache-dir .
USER sentinel
CMD ["python", "-m", "simulator.traffic"]
