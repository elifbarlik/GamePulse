FROM python:3.15-slim

ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 PIP_NO_CACHE_DIR=1
WORKDIR /app

# Runtime deps only (no dev tools). dbt-duckdb is needed by the pipeline image, not by the API.
COPY pyproject.toml ./
RUN pip install --no-cache-dir "pydantic>=2.7" "pyyaml>=6.0" "numpy>=1.26" "pandas>=2.2" "pyarrow>=16" \
    "fastapi>=0.111" "uvicorn>=0.30" "duckdb>=1.1" "prometheus-client>=0.20" "confluent-kafka>=2.5" \
    "google-cloud-bigquery>=3.25"

COPY ingestion ./ingestion
COPY streaming ./streaming
COPY storage ./storage

RUN useradd --system --uid 10001 --no-create-home gamepulse && mkdir -p /app/data && chown gamepulse /app/data
USER gamepulse
ENV PORT=8000
EXPOSE 8000

# $PORT can override the listen port; defaults to 8000.
CMD ["sh", "-c", "uvicorn ingestion.api.main:app --host 0.0.0.0 --port ${PORT}"]
