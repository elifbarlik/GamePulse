"""Pipeline steps shared by the Airflow DAG and the local demo.

Order: ingest -> silver (dbt) -> data quality gate -> gold (dbt) -> notify.
A critical DQ failure stops the run BEFORE Gold is rebuilt (exit code 2).
"""

from __future__ import annotations

import argparse
import json
import os
import subprocess  # nosec B404 - fixed argv only
import sys
import urllib.request
from pathlib import Path
from urllib.parse import urlparse

import duckdb
import pandas as pd

from analytics.dq.checks import CheckResult, has_critical_failure, quality_score, run_all
from ingestion.batch.loader import load_events
from ingestion.store import BronzeStore

ROOT = Path(__file__).resolve().parent.parent
DB = os.environ.get("GP_DUCKDB_PATH", str(ROOT / "data" / "gamepulse.duckdb"))
RAW = Path(os.environ.get("GP_RAW_DIR", ROOT / "data" / "raw"))


def _dbt(*args: str) -> None:
    cmd = [sys.executable, "-m", "dbt.cli.main", *args, "--project-dir", str(ROOT / "dbt"),
           "--profiles-dir", str(ROOT / "dbt")]
    subprocess.run(cmd, check=True, env={**os.environ, "GP_DUCKDB_PATH": DB})  # noqa: S603 # nosec B603


def ingest() -> dict:
    store = BronzeStore(DB)
    try:
        res = load_events(store, RAW / "events.parquet")
        store.load_campaigns(pd.read_csv(RAW / "campaigns.csv"))
    finally:
        store.close()
    return res


def build_silver() -> None:
    _dbt("build", "--select", "path:models/staging", "path:models/intermediate")


def data_quality() -> list[CheckResult]:
    con = duckdb.connect(DB)
    try:
        return run_all(con)
    finally:
        con.close()


def build_gold() -> None:
    _dbt("build", "--select", "path:models/marts", "path:tests")


def notify(results: list[CheckResult]) -> None:
    failed = [r for r in results if r.status == "fail"]
    text = f"GamePulse run: quality score {quality_score(results)}; {len(failed)} failing check(s)\n" + \
        "\n".join(f"- [{r.severity}] {r.check}: {r.detail}" for r in failed)
    print(text)
    url = os.environ.get("ALERT_WEBHOOK_URL", "")
    if url and failed:
        if urlparse(url).scheme != "https":
            raise ValueError("ALERT_WEBHOOK_URL must be https")
        req = urllib.request.Request(url, data=json.dumps({"content": text[:1900]}).encode(),  # noqa: S310
                                     headers={"Content-Type": "application/json"})
        urllib.request.urlopen(req, timeout=10)  # noqa: S310 # nosec B310 - https enforced above


def run_all_steps() -> int:
    print("ingest:", ingest())
    build_silver()
    results = data_quality()
    notify(results)
    if has_critical_failure(results):
        print("CRITICAL data-quality failure: Gold build skipped")
        return 2
    build_gold()
    return 0


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--step", choices=["ingest", "silver", "dq", "gold", "all"], default="all")
    a = ap.parse_args()
    if a.step == "all":
        sys.exit(run_all_steps())
    if a.step == "ingest":
        print(ingest())
    elif a.step == "silver":
        build_silver()
    elif a.step == "dq":
        res = data_quality()
        notify(res)
        sys.exit(2 if has_critical_failure(res) else 0)
    elif a.step == "gold":
        build_gold()
