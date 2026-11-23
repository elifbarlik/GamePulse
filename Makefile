PY ?= python

.PHONY: sim pipeline test lint report up demo bq-load

sim:        ## generate SIMULATED data (50k users, ~2.5M events)
	$(PY) -m ingestion.simulator.generator --users 50000 --out data/raw

pipeline:   ## ingest -> silver -> data-quality gate -> gold
	$(PY) -m orchestration.pipeline --step all

test:
	$(PY) -m pytest

lint:
	ruff check . && bandit -q -r ingestion streaming analytics orchestration storage

report:     ## render the 4 dashboards to docs/img
	$(PY) -m dashboard.render_report

up:         ## api + redpanda + consumer + prometheus + grafana (needs .env)
	docker compose up -d --build

demo: sim pipeline report

bq-load:    ## load Bronze to BigQuery (needs GCP_PROJECT_ID + gcloud ADC)
	$(PY) -m storage.bigquery --db data/gamepulse.duckdb
