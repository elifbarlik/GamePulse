"""Reproducible query benchmark: D1 retention computed from raw events vs from the modeled grain.

Shows why the Gold layer exists: same answer, far less data scanned.
Usage: python -m analytics.benchmark [--db data/gamepulse.duckdb] [--runs 5]
"""

from __future__ import annotations

import argparse
import statistics
import time

import duckdb

RAW_SQL = """
WITH first_activity AS (
    SELECT user_id, MIN(CAST(try_cast(replace(event_timestamp,'Z','') AS timestamp) AS date)) AS cohort_date
    FROM bronze.raw_game_events WHERE event_name = 'app_open' AND user_id IS NOT NULL GROUP BY user_id),
daily_activity AS (
    SELECT DISTINCT user_id, CAST(try_cast(replace(event_timestamp,'Z','') AS timestamp) AS date) AS d
    FROM bronze.raw_game_events WHERE event_name = 'app_open' AND user_id IS NOT NULL)
SELECT f.cohort_date, COUNT(DISTINCT f.user_id) AS cohort_users, COUNT(DISTINCT d.user_id) AS retained
FROM first_activity f LEFT JOIN daily_activity d
  ON f.user_id = d.user_id AND d.d = f.cohort_date + INTERVAL 1 DAY
GROUP BY f.cohort_date ORDER BY 1"""

SILVER_SQL = RAW_SQL.replace("bronze.raw_game_events", "silver.stg_game_events") \
    .replace("CAST(try_cast(replace(event_timestamp,'Z','') AS timestamp) AS date)", "event_date")

GOLD_SQL = """
SELECT cohort_date, SUM(cohort_users) AS cohort_users, SUM(retained_users) AS retained
FROM gold.mart_retention WHERE day_n = 1 GROUP BY cohort_date ORDER BY 1"""


def timeit(con, sql: str, runs: int) -> float:
    times = []
    for _ in range(runs):
        t = time.perf_counter()
        con.execute(sql).fetchall()
        times.append(time.perf_counter() - t)
    return statistics.median(times) * 1000


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--db", default="data/gamepulse.duckdb")
    ap.add_argument("--runs", type=int, default=5)
    a = ap.parse_args()
    con = duckdb.connect(a.db, read_only=True)
    rows = {"bronze": "bronze.raw_game_events", "silver": "silver.stg_game_events",
            "gold": "gold.mart_retention"}
    print(f"{'layer':8} {'rows in source':>15} {'median ms':>10}")
    for name, sql in (("bronze", RAW_SQL), ("silver", SILVER_SQL), ("gold", GOLD_SQL)):
        n = con.execute(f"select count(*) from {rows[name]}").fetchone()[0]  # noqa: S608  # nosec B608 - fixed table names
        print(f"{name:8} {n:>15,} {timeit(con, sql, a.runs):>10.1f}")


if __name__ == "__main__":
    main()
