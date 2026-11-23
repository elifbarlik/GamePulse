# GamePulse — Mobile Game Analytics & Data Platform

End-to-end data platform for a mobile game: validated event ingestion (API, batch, Kafka/Redpanda) → **Bronze / Silver / Gold** medallion layers built with **dbt** → advanced SQL analytics (DAU/MAU, retention cohorts, order-aware funnels, level drop-off, campaign ROAS) → **data-quality gate**, anomaly detection and observability.

> ⚠️ **All data is synthetic.** Events and campaign spend are produced by a seeded Python simulator (`ingestion/simulator`). Nothing is real company or player data, and the business conclusions in `docs/business_insights.md` illustrate the analysis method only.

![Game performance dashboard](docs/img/dashboard_1_game_performance.png)

## What it demonstrates
| Area | Implementation |
|---|---|
| Data contracts | Event dictionary (YAML) → Pydantic validation, per-event required fields, reason-coded quarantine |
| Ingestion | FastAPI (API key with constant-time compare, rate limit, body/batch limits), batch loader, Redpanda producer/consumer |
| Idempotency | Batch ledger committed with the data; `event_id` dedup; incremental upsert; Kafka offset-range batch ids |
| Modelling | dbt: staging → intermediate (LAG sessionization) → star-schema marts; DuckDB **and** BigQuery targets |
| Analytics SQL | CTEs, window functions, rolling distinct counts, cohort retention D1/D7/D30, funnel with event ordering |
| Data quality | Contract + 27 dbt tests + run-time gate (freshness, completeness, volume, tracking coverage); critical failure blocks Gold |
| Monitoring | z-score-of-change anomaly detection, `pipeline_issue` vs `real_user_loss` verdict, Prometheus metrics, Grafana dashboard |
| Orchestration | Airflow DAG (retries, backoff, DQ gate with `retries=0`, backfill-safe) sharing code with the local runner |
| Engineering | 54 tests, ruff + bandit, non-root Docker, CI, Dependabot, keyless (WIF) Cloud Run deploy workflow |

## Results on the simulated dataset (50k players, 2.5M events)
* Order-aware funnel: 49,997 → 49,135 → 35,097 → 30,029 → 1,270 purchasers.
* D7 retention 31.1 % (tutorial completed) vs 14.7 % (not completed).
* Injected tracking bug (v1.4.2 drops `level_completed`) and a 21 Oct ingestion outage are both detected and classified as `pipeline_issue`; ~1.5 % corrupt events never reach Gold.
* Retention query: 139.9 ms on raw events vs 2.4 ms on the Gold mart (`docs/query_optimization.md`).

## Quick start (free, local)
```bash
python -m venv .venv && . .venv/bin/activate          # Windows: .venv\Scripts\activate
pip install -e ".[dev,streaming]"
make demo        # = simulate data -> ingest -> dbt silver -> DQ gate -> dbt gold -> render dashboards
make test        # 54 tests, includes dbt golden-fixture + incremental tests
```
Without `make`: `python -m ingestion.simulator.generator`, `python -m orchestration.pipeline --step all`, `python -m dashboard.render_report`.

Ask the KPI assistant (allowlisted SQL only, shows the SQL it ran):
```bash
python -m analytics.assistant.assistant "d7 retention by country"
```

## Project status — what is verified and what is not
| Component | Status |
|---|---|
| Simulator, contract, Bronze, API, batch loader | ✅ built and tested; API smoke-tested over real HTTP |
| dbt Silver/Gold on DuckDB, DQ gate, anomaly detection, dashboards | ✅ run end-to-end on the full 2.5M-event dataset |
| Golden-fixture dbt test (hand-computed D1/D7/funnel/ROAS) and incremental test | ✅ |
| Kafka consumer/producer | ✅ processing logic unit-tested incl. replay idempotency and batch-vs-stream equivalence · ⚠️ not yet run against a live Redpanda container |
| Airflow DAG | ✅ structure tested · ⚠️ not run in an Airflow instance |
| BigQuery adapter + dbt BigQuery target, Cloud Run workflow, Looker Studio | ⚠️ implemented and unit-tested with a fake client; **not executed against a live GCP project** (see `docs/deployment.md`) |
| Docker image / compose / Grafana | ⚠️ files validated (`docker compose config`); containers not started in this environment |

## Repository layout
```
ingestion/   simulator · contracts · store · api · batch loader
streaming/   Redpanda/Kafka producer & consumer (Prometheus metrics)
storage/     event dictionary (YAML) · BigQuery adapter
dbt/         models (staging/intermediate/marts) · macros · singular tests · profiles (no secrets)
analytics/   dq checks · anomaly detection · KPI assistant · benchmark
orchestration/ pipeline runner + Airflow DAG       dashboard/  PNG dashboard renderer
monitoring/  Prometheus + Grafana provisioning     docs/       architecture, dictionary, DQ, insights
```
More: [architecture](docs/architecture.md) · [data dictionary](docs/data_dictionary.md) · [data quality](docs/data_quality.md) · [business insights](docs/business_insights.md) · [query optimisation](docs/query_optimization.md) · [deployment](docs/deployment.md) · [security](SECURITY.md)

## Resume bullets (only claims backed by this repo)
**GamePulse — End-to-End Game Analytics Data Platform** · *Python, SQL, dbt, BigQuery/DuckDB, Kafka (Redpanda), Airflow, FastAPI, Docker, GitHub Actions*
* Built an end-to-end analytics platform on simulated mobile-game data (50k players, 2.5M events) with batch, API and Kafka ingestion into a Bronze/Silver/Gold architecture modelled with dbt.
* Implemented schema-driven validation, reason-coded quarantine, idempotent batch processing and incremental upserts so retries and replays never double-count.
* Wrote advanced SQL (cohort retention, order-aware funnels, rolling MAU, LAG sessionization, ROAS) with hand-computed golden-dataset tests; cut retention-query time from 140 ms to 2.4 ms via layered modelling.
* Added a data-quality gate (freshness, completeness, tracking coverage, volume) that blocks Gold builds, plus change-based z-score anomaly detection that separates pipeline failures from real user loss.
* Shipped with CI (ruff, bandit, 54 tests), non-root containers, Prometheus/Grafana observability and keyless Cloud Run deployment config.
