"""Golden-dataset test: tiny hand-computed fixture -> `dbt build` -> exact expected KPI values.

Fixture (all TR/Android, campaign c1 for A and B), cohort day = 2026-09-01:
  A: full funnel incl. purchase 4.99, active D1 and D7
  B: tutorial done, active D1
  C: tutorial started only
  D: app_open only
  E: reaches level 1 but its purchase happens BEFORE its app_open (order-aware funnel => no purchase step)
  F: only a future-timestamped event (must be quarantined, never a user)
  A also has a duplicate app_open event_id (must be de-duplicated).
Expected: D1 = 2/5, D7 = 1/5, funnel = 5,4,3,2,1, CPI = 5.0, ROAS = 0.499.
"""

import os
import subprocess
import sys
from pathlib import Path

import duckdb
import pandas as pd
import pytest

from ingestion.processing import process_batch
from ingestion.store import BronzeStore

ROOT = Path(__file__).resolve().parent.parent


def e(eid, name, user, ts, sess=None, camp=None, **kw):
    return {"event_id": eid, "event_name": name, "user_id": user, "session_id": sess or f"s_{user}",
            "event_timestamp": ts, "country": "TR", "platform": "Android", "app_version": "1.4.0",
            "campaign_id": camp, **kw}


D1, D2, D8 = "2026-09-01", "2026-09-02", "2026-09-08"


def fixture_events():
    ev = [
        e("a1", "app_open", "A", f"{D1}T10:00:00Z", camp="c1"),
        e("a1", "app_open", "A", f"{D1}T10:00:00Z", camp="c1"),  # duplicate event_id
        e("a2", "tutorial_started", "A", f"{D1}T10:01:00Z", camp="c1"),
        e("a3", "tutorial_completed", "A", f"{D1}T10:03:00Z", camp="c1", duration_seconds=100),
        e("a4", "level_completed", "A", f"{D1}T10:05:00Z", camp="c1", level_id=1, duration_seconds=60),
        e("a5", "purchase_completed", "A", f"{D1}T10:06:00Z", camp="c1", purchase_amount=4.99),
        e("a6", "app_open", "A", f"{D2}T10:00:00Z", sess="s_A2", camp="c1"),
        e("a7", "app_open", "A", f"{D8}T10:00:00Z", sess="s_A8", camp="c1"),
        e("b1", "app_open", "B", f"{D1}T11:00:00Z", camp="c1"),
        e("b2", "tutorial_started", "B", f"{D1}T11:01:00Z", camp="c1"),
        e("b3", "tutorial_completed", "B", f"{D1}T11:03:00Z", camp="c1", duration_seconds=90),
        e("b4", "app_open", "B", f"{D2}T11:00:00Z", sess="s_B2", camp="c1"),
        e("c1", "app_open", "C", f"{D1}T12:00:00Z"),
        e("c2", "tutorial_started", "C", f"{D1}T12:01:00Z"),
        e("d1", "app_open", "D", f"{D1}T13:00:00Z"),
        e("e0", "purchase_completed", "E", f"{D1}T09:00:00Z", purchase_amount=1.99),
        e("e1", "app_open", "E", f"{D1}T11:00:00Z"),
        e("e2", "tutorial_started", "E", f"{D1}T12:00:00Z"),
        e("e3", "tutorial_completed", "E", f"{D1}T13:00:00Z", duration_seconds=50),
        e("e4", "level_completed", "E", f"{D1}T14:00:00Z", level_id=1, duration_seconds=40),
        e("f1", "app_open", "F", "2030-01-01T00:00:00Z"),  # future
    ]
    return ev


@pytest.fixture(scope="module")
def gold(tmp_path_factory):
    db = tmp_path_factory.mktemp("golden") / "g.duckdb"
    store = BronzeStore(db)
    process_batch(store, "golden_1", "test", fixture_events())
    store.load_campaigns(pd.DataFrame([{"campaign_id": "c1", "country": "TR", "spend": 10.0, "installs": 2}]))
    store.close()
    env = {**os.environ, "GP_DUCKDB_PATH": str(db), "GP_DBT_TARGET": "duckdb"}
    res = subprocess.run(  # noqa: S603
        [sys.executable, "-m", "dbt.cli.main", "build", "--project-dir", str(ROOT / "dbt"),
         "--profiles-dir", str(ROOT / "dbt"), "--target-path", str(db.parent / "target"),
         "--log-path", str(db.parent / "logs")],
        env=env, capture_output=True, text=True, cwd=ROOT, check=False)
    assert res.returncode == 0, res.stdout[-3000:] + res.stderr[-1000:]
    con = duckdb.connect(str(db), read_only=True)
    yield con
    con.close()


def test_dedup_and_quarantine(gold):
    assert gold.execute("select count(*) from silver.stg_game_events where event_id='a1'").fetchone()[0] == 1
    reasons = {r[0] for r in gold.execute("select reason from silver.stg_rejected_events").fetchall()}
    assert {"future_timestamp", "duplicate_event_id"} <= reasons
    assert gold.execute("select count(*) from gold.dim_users where user_id='F'").fetchone()[0] == 0
    assert gold.execute("select count(*) from gold.dim_users").fetchone()[0] == 5


def test_retention(gold):
    d1, d7 = (gold.execute(
        "select sum(retained_users), sum(cohort_users) from gold.mart_retention where day_n=?", [n]
    ).fetchone() for n in (1, 7))
    assert d1 == (2, 5) and d7 == (1, 5)
    assert gold.execute("select count(*) from gold.mart_retention where day_n=30").fetchone()[0] == 0


def test_funnel_is_user_level_and_ordered(gold):
    row = gold.execute("select sum(app_open_users), sum(tutorial_started_users), "
                       "sum(tutorial_completed_users), sum(level_1_completed_users), "
                       "sum(purchase_users) from gold.mart_funnel").fetchone()
    assert tuple(int(x) for x in row) == (5, 4, 3, 2, 1)


def test_campaign_and_revenue(gold):
    cpi, roas, payers, users = gold.execute(
        "select cpi, roas, paying_users, attributed_users from gold.mart_campaign_performance").fetchone()
    assert cpi == pytest.approx(5.0) and roas == pytest.approx(0.499) and (payers, users) == (1, 2)


def test_dau_and_sessions(gold):
    dau = dict(gold.execute("select cast(activity_date as varchar), dau from gold.mart_dau_wau_mau").fetchall())
    assert dau == {D1: 5, D2: 2, D8: 1}
    sessions = gold.execute("select count(*) from silver.int_player_sessions").fetchone()[0]
    assert sessions == 8  # A:3, B:2, C:1, D:1, E:1
