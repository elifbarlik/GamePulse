"""Data-quality framework (DuckDB). Results are persisted to gold.dq_results.

severity 'critical' failures block the Gold build; 'warning' failures only alert.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime

import duckdb
import pandas as pd

from analytics.anomaly_detection.detector import classify_dau_drop, detect_anomalies


@dataclass
class CheckResult:
    check: str
    severity: str  # critical | warning
    status: str  # pass | fail
    value: float | None
    detail: str


def check_freshness(con, max_age_hours: float = 24.0, now: datetime | None = None) -> CheckResult:
    now = now or datetime.now(UTC).replace(tzinfo=None)
    last = con.execute("select max(ingested_at) from bronze.raw_game_events").fetchone()[0]
    if last is None:
        return CheckResult("freshness", "critical", "fail", None, "no data ingested")
    age = (now - last).total_seconds() / 3600
    return CheckResult("freshness", "critical", "pass" if age <= max_age_hours else "fail", round(age, 2),
                       f"last ingestion {age:.1f}h ago (max {max_age_hours}h)")


def check_reject_ratio(con, max_ratio: float = 0.10) -> CheckResult:
    total, rejected = con.execute(
        "select (select count(*) from bronze.raw_game_events) + (select count(*) from bronze.quarantine_events),"
        " (select count(*) from silver.stg_rejected_events)").fetchone()
    ratio = rejected / total if total else 1.0
    return CheckResult("reject_ratio", "critical", "pass" if ratio <= max_ratio else "fail", round(ratio, 4),
                       f"{rejected} of {total} events rejected (max {max_ratio:.0%})")


def check_completeness(con) -> CheckResult:
    bad = con.execute("""
        select count(*) from silver.stg_game_events where
          user_id is null or session_id is null or country is null
          or (event_name in ('level_started','level_completed','level_failed') and level_id is null)
          or (event_name = 'purchase_completed' and purchase_amount is null)
          or (event_name = 'ad_watched' and ad_revenue is null)""").fetchone()[0]
    return CheckResult("completeness", "critical", "pass" if bad == 0 else "fail", float(bad),
                       f"{bad} silver rows missing required fields")


def check_version_event_coverage(con, min_ratio: float = 0.2) -> CheckResult:
    """Catches tracking regressions: level_completed vs level_started per app_version."""
    rows = con.execute("""
        select app_version,
               sum(case when event_name = 'level_started' then 1 else 0 end) as started,
               sum(case when event_name = 'level_completed' then 1 else 0 end) as completed
        from silver.stg_game_events group by app_version""").fetchall()
    broken = [v for v, s, c in rows if s > 100 and c / s < min_ratio]
    return CheckResult("version_event_coverage", "warning", "pass" if not broken else "fail",
                       float(len(broken)),
                       "tracking looks broken for app_version(s): " + ", ".join(sorted(broken)) if broken
                       else "all versions emit level_completed")


def daily_series(con) -> pd.DataFrame:
    return con.execute("""
        select event_date as date, count(distinct user_id) as dau, count(*) as events
        from silver.stg_game_events group by event_date order by 1""").df()


def check_volume(con, z_threshold: float = 3.0) -> CheckResult:
    s = detect_anomalies(daily_series(con), "date", "events", z_threshold, on_change=True)
    bad = s[s["is_anomaly"] & (s["z"] < 0)]  # only drops matter for volume
    days = ", ".join(str(d)[:10] for d in bad["date"])
    return CheckResult("daily_volume", "warning", "pass" if bad.empty else "fail", float(len(bad)),
                       f"anomalous event volume on: {days}" if len(bad) else "volume within expected range")


def check_dau_drops(con) -> list[CheckResult]:
    f = classify_dau_drop(daily_series(con))
    return [CheckResult("dau_drop", "warning", "fail", float(r.dau),
                        f"{str(r.date)[:10]}: {r.verdict} (z_dau={r.z_dau:.1f}, z_events={r.z_events:.1f})")
            for r in f.itertuples()]


def run_all(con: duckdb.DuckDBPyConnection, persist: bool = True) -> list[CheckResult]:
    results = [check_freshness(con), check_reject_ratio(con), check_completeness(con),
               check_version_event_coverage(con), check_volume(con), *check_dau_drops(con)]
    if persist:
        con.execute("create schema if not exists gold")
        con.execute("""create table if not exists gold.dq_results (
            run_ts timestamp, check_name varchar, severity varchar, status varchar,
            value double, detail varchar)""")
        now = datetime.now(UTC).replace(tzinfo=None)
        con.executemany("insert into gold.dq_results values (?,?,?,?,?,?)",
                        [(now, r.check, r.severity, r.status, r.value, r.detail) for r in results])
    return results


def quality_score(results: list[CheckResult]) -> float:
    """Share of checks passed (critical weighted x3)."""
    w = {"critical": 3, "warning": 1}
    total = sum(w[r.severity] for r in results)
    ok = sum(w[r.severity] for r in results if r.status == "pass")
    return round(ok / total, 3) if total else 0.0


def has_critical_failure(results: list[CheckResult]) -> bool:
    return any(r.severity == "critical" and r.status == "fail" for r in results)
