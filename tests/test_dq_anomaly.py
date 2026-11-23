from datetime import datetime, timedelta

import duckdb
import numpy as np
import pandas as pd

from analytics.anomaly_detection.detector import classify_dau_drop, detect_anomalies, rolling_zscore
from analytics.dq import checks


def series(n=30, base=1000, noise=20, seed=0):
    rng = np.random.default_rng(seed)
    dates = pd.date_range("2026-09-01", periods=n)
    return pd.DataFrame({"date": dates, "dau": (base + rng.normal(0, noise, n)).round(),
                         "events": (base * 10 + rng.normal(0, noise * 10, n)).round()})


def test_zscore_has_no_self_leak_and_flags_drop():
    df = series()
    df.loc[25, "events"] = 2000  # -80 %
    out = detect_anomalies(df, "date", "events")
    assert 25 in list(out.index[out["is_anomaly"]])
    assert rolling_zscore(pd.Series([1.0, 1.0, 1.0])).isna().all()  # not enough history


def test_pipeline_issue_vs_real_user_loss():
    pipe = series()
    pipe.loc[25, ["dau", "events"]] = [700, 2000]  # events collapse far more than users
    v = classify_dau_drop(pipe)
    assert v.loc[v["date"] == pipe.loc[25, "date"], "verdict"].iloc[0] == "pipeline_issue"

    real = series()
    real.loc[25, ["dau", "events"]] = [500, 5000]  # users halve, events/user stays ~10
    v = classify_dau_drop(real)
    assert v.loc[v["date"] == pipe.loc[25, "date"], "verdict"].iloc[0] == "real_user_loss"


def test_no_false_alarm_on_stable_series():
    assert classify_dau_drop(series(noise=5)).empty


def make_db(ingested_hours_ago=1, broken_version=False, null_amount=False):
    con = duckdb.connect(":memory:")
    for s in ("bronze", "silver", "gold"):
        con.execute(f"create schema {s}")
    now = datetime(2026, 11, 1, 12)
    con.execute("create table bronze.raw_game_events (ingested_at timestamp)")
    con.execute("insert into bronze.raw_game_events values (?)", [now - timedelta(hours=ingested_hours_ago)])
    con.execute("create table bronze.quarantine_events (x int)")
    con.execute("create table silver.stg_rejected_events (x int)")
    con.execute("""create table silver.stg_game_events (event_date date, user_id varchar, session_id varchar,
        country varchar, event_name varchar, level_id int, purchase_amount double, ad_revenue double,
        app_version varchar)""")
    rows = []
    for i in range(300):
        rows.append(("2026-10-01", f"u{i}", "s", "TR", "level_started", 1, None, None, "1.4.2"))
        if not broken_version:
            rows.append(("2026-10-01", f"u{i}", "s", "TR", "level_completed", 1, None, None, "1.4.2"))
    if null_amount:
        rows.append(("2026-10-01", "u1", "s", "TR", "purchase_completed", None, None, None, "1.4.2"))
    con.executemany("insert into silver.stg_game_events values (?,?,?,?,?,?,?,?,?)", rows)
    return con, now


def test_freshness_pass_and_fail():
    con, now = make_db(ingested_hours_ago=2)
    assert checks.check_freshness(con, 24, now).status == "pass"
    con, now = make_db(ingested_hours_ago=48)
    assert checks.check_freshness(con, 24, now).status == "fail"


def test_version_coverage_detects_tracking_regression():
    con, _ = make_db(broken_version=True)
    r = checks.check_version_event_coverage(con)
    assert r.status == "fail" and "1.4.2" in r.detail
    con, _ = make_db()
    assert checks.check_version_event_coverage(con).status == "pass"


def test_completeness_flags_purchase_without_amount():
    con, _ = make_db(null_amount=True)
    assert checks.check_completeness(con).status == "fail"


def test_score_and_critical_gate():
    ok = checks.CheckResult("a", "critical", "pass", 0, "")
    warn = checks.CheckResult("b", "warning", "fail", 0, "")
    crit = checks.CheckResult("c", "critical", "fail", 0, "")
    assert checks.quality_score([ok, warn]) == 0.75
    assert not checks.has_critical_failure([ok, warn])
    assert checks.has_critical_failure([ok, crit])
