# Deployment & cloud setup (free-tier oriented)

Everything runs locally for free (`make demo`). The steps below add the cloud pieces. **Status: written but not executed against a live GCP project in this repository** — verify each step on your own project.

## 1. BigQuery (Sandbox — no billing account)
1. Create a GCP project, open BigQuery (Sandbox mode: 10 GB storage, 1 TB queries/month, tables expire after 60 days).
2. `gcloud auth application-default login` (no key files).
3. `export GCP_PROJECT_ID=<id>` and `pip install -e ".[bigquery]"`.
4. Load Bronze: `make bq-load` (batch load jobs → free).
5. Build Silver/Gold: `GP_DBT_TARGET=bigquery GP_BQ_SANDBOX=1 dbt build --project-dir dbt --profiles-dir dbt`.
   `GP_BQ_SANDBOX=1` makes Silver a plain table (CREATE OR REPLACE) instead of incremental `MERGE`, because DML may be restricted in the Sandbox. With billing enabled leave it unset to use the incremental `merge` strategy.
6. Budget safety: set a budget alert (Billing → Budgets) even if you stay in the Sandbox.

## 2. Looker Studio dashboards
Create a data source per Gold table (`gold.mart_dau_wau_mau`, `mart_retention`, `mart_funnel`, `mart_level_dropoff`, `mart_session_metrics`, `mart_campaign_performance`). The four PNGs in `docs/img/` show the intended layout; each chart maps 1:1 to a mart column. Keep the report private or share view-only; it contains only simulated data.

## 3. Cloud Run ingestion API (billing required; stays in the free tier at demo scale)
* Workflow: `.github/workflows/deploy-cloud-run.yml` (manual). **Keyless** auth through Workload Identity Federation.
* One-time setup: create a service account with only `roles/run.admin`, `roles/iam.serviceAccountUser`, `roles/cloudbuild.builds.editor`; create a runtime service account with `roles/bigquery.dataEditor` on the `bronze` dataset + `roles/bigquery.jobUser`; store the API key in Secret Manager (`gamepulse-api-key`).
* Container: non-root, `min-instances=0` (scales to zero), `max-instances=2`, key from Secret Manager (never baked into the image).
* Create a **$1 budget alert**, and delete the service after the demo (`gcloud run services delete gamepulse-ingestion`). The in-memory rate limiter is per instance — fine for a demo, use Cloud Armor/API Gateway for real traffic.

## 4. Local stack
```
cp .env.example .env     # set GAMEPULSE_API_KEY (>=16 chars) and GRAFANA_ADMIN_PASSWORD
docker compose up -d --build            # api, redpanda, consumer, prometheus, grafana (127.0.0.1 only)
python -m streaming.producer.producer --limit 100000
docker compose --profile airflow up -d  # optional Airflow UI on :8080 (password printed in logs)
```
Grafana → http://127.0.0.1:3000 → dashboard *GamePulse – Pipeline Observability*.
