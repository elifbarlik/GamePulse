import ast
from pathlib import Path

DAG = Path(__file__).resolve().parent.parent / "orchestration" / "dags" / "gamepulse_daily.py"


def test_dag_is_valid_python_and_chain_is_ordered():
    src = DAG.read_text(encoding="utf-8")
    ast.parse(src)
    assert "ingest >> silver >> dq >> gold" in src
    assert "retries=0" in src  # DQ gate must not be retried into passing
    assert "catchup=False" in src and "max_active_runs=1" in src


def test_dag_imports_with_airflow_if_installed():
    import pytest

    pytest.importorskip("airflow")
    import importlib.util

    spec = importlib.util.spec_from_file_location("gp_dag", DAG)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    assert {t.task_id for t in mod.dag.tasks} == {"ingest", "dbt_silver", "data_quality_gate", "dbt_gold"}
