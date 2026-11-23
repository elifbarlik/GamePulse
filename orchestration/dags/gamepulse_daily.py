"""Daily GamePulse DAG: ingest -> silver -> DQ gate -> gold.

Each task shells out to `orchestration.pipeline` so the exact same code runs locally and in Airflow.
DQ exit code 2 (critical failure) fails the task, so Gold is never rebuilt on bad data.
Backfill: `airflow dags backfill gamepulse_daily -s 2026-09-01 -e 2026-09-07` (ingest is idempotent).
"""

from datetime import datetime, timedelta

from airflow import DAG
from airflow.operators.bash import BashOperator

default_args = {
    "owner": "data-eng",
    "retries": 2,
    "retry_delay": timedelta(minutes=5),
    "retry_exponential_backoff": True,
}

with DAG(
    dag_id="gamepulse_daily",
    start_date=datetime(2026, 9, 1),
    schedule="@daily",
    catchup=False,
    max_active_runs=1,
    dagrun_timeout=timedelta(hours=2),
    default_args=default_args,
    tags=["gamepulse"],
) as dag:
    step = "cd /opt/gamepulse && python -m orchestration.pipeline --step"
    ingest = BashOperator(task_id="ingest", bash_command=f"{step} ingest")
    silver = BashOperator(task_id="dbt_silver", bash_command=f"{step} silver")
    dq = BashOperator(task_id="data_quality_gate", bash_command=f"{step} dq", retries=0)
    gold = BashOperator(task_id="dbt_gold", bash_command=f"{step} gold")
    ingest >> silver >> dq >> gold
