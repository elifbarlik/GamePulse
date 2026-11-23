"""Incremental Silver: a second run processes only new batches and never double-counts re-deliveries."""

import os
import subprocess
import sys

import duckdb

from ingestion.processing import process_batch
from ingestion.store import BronzeStore
from tests.test_dbt_golden import ROOT, e, fixture_events


def dbt(db, *args):
    env = {**os.environ, "GP_DUCKDB_PATH": str(db), "GP_DBT_TARGET": "duckdb"}
    res = subprocess.run(  # noqa: S603
        [sys.executable, "-m", "dbt.cli.main", *args, "--project-dir", str(ROOT / "dbt"),
         "--profiles-dir", str(ROOT / "dbt"), "--target-path", str(db.parent / "target"),
         "--log-path", str(db.parent / "logs")],
        env=env, capture_output=True, text=True, cwd=ROOT, check=False)
    assert res.returncode == 0, res.stdout[-2000:]


def count(db, sql):
    con = duckdb.connect(str(db), read_only=True)
    try:
        return con.execute(sql).fetchone()[0]
    finally:
        con.close()


def test_incremental_run_upserts_without_duplicates(tmp_path):
    db = tmp_path / "inc.duckdb"
    store = BronzeStore(db)
    process_batch(store, "batch_1", "test", fixture_events())
    store.close()
    dbt(db, "run", "--select", "stg_game_events")
    first = count(db, "select count(*) from silver.stg_game_events")

    store = BronzeStore(db)
    late = [e("g1", "app_open", "G", "2026-09-03T10:00:00Z"),
            e("a2", "tutorial_started", "A", "2026-09-01T10:01:00Z", camp="c1")]  # re-delivery of old id
    process_batch(store, "batch_2", "test", late)
    store.close()
    dbt(db, "run", "--select", "stg_game_events")

    assert count(db, "select count(*) from silver.stg_game_events") == first + 1  # only G is new
    assert count(db, "select count(*) from silver.stg_game_events where event_id = 'a2'") == 1
    assert count(db, "select count(distinct batch_id) from silver.stg_game_events") == 2
