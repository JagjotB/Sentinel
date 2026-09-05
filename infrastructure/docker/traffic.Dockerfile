FROM python:3.12-slim AS runtime
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1
WORKDIR /app
RUN groupadd --gid 10001 sentinel \
    && useradd --uid 10001 --gid sentinel --no-create-home --shell /usr/sbin/nologin sentinel
COPY pyproject.toml README.md ./
COPY simulator ./simulator
RUN pip install --no-cache-dir .
USER 10001:10001
CMD ["python", "-m", "simulator.traffic"]
