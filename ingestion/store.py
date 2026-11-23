"""Bronze store (DuckDB). Append-only raw events + quarantine + batch ledger.

Idempotency: a `batch_id` can be ingested exactly once; re-ingesting it is a no-op.
"""

from __future__ import annotations

import threading
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import duckdb
import pandas as pd

from ingestion.contracts import EVENT_COLUMNS

DDL = [
    "CREATE SCHEMA IF NOT EXISTS bronze",
    """CREATE TABLE IF NOT EXISTS bronze.raw_game_events (
        event_id VARCHAR, event_name VARCHAR, user_id VARCHAR, session_id VARCHAR,
        event_timestamp VARCHAR, country VARCHAR, platform VARCHAR, app_version VARCHAR,
        campaign_id VARCHAR, level_id INTEGER, duration_seconds INTEGER,
        purchase_amount DOUBLE, ad_revenue DOUBLE,
        batch_id VARCHAR, source_file VARCHAR, ingested_at TIMESTAMP)""",
    """CREATE TABLE IF NOT EXISTS bronze.quarantine_events (
        batch_id VARCHAR, source_file VARCHAR, raw_payload VARCHAR, reason VARCHAR,
        ingested_at TIMESTAMP)""",
    """CREATE TABLE IF NOT EXISTS bronze.ingestion_batches (
        batch_id VARCHAR PRIMARY KEY, source_file VARCHAR, n_valid BIGINT,
        n_quarantined BIGINT, ingested_at TIMESTAMP)""",
    """CREATE TABLE IF NOT EXISTS bronze.raw_campaigns (
        campaign_id VARCHAR, country VARCHAR, spend DOUBLE, installs BIGINT)""",
]


class BronzeStore:
    def __init__(self, path: str | Path = "data/gamepulse.duckdb"):
        if str(path) != ":memory:":
            Path(path).parent.mkdir(parents=True, exist_ok=True)
        self._con = duckdb.connect(str(path))
        self._lock = threading.Lock()
        for stmt in DDL:
            self._con.execute(stmt)

    def ingest_batch(self, batch_id: str, source: str, valid: list[dict[str, Any]],
                     quarantined: list[tuple[str, str]]) -> dict[str, Any]:
        now = datetime.now(UTC).replace(tzinfo=None)
        with self._lock:
            if self._con.execute("SELECT 1 FROM bronze.ingestion_batches WHERE batch_id = ?",
                                 [batch_id]).fetchone():
                return {"batch_id": batch_id, "status": "duplicate_batch",
                        "accepted": 0, "quarantined": 0}
            self._con.execute("BEGIN")
            try:
                if valid:
                    df = pd.DataFrame(valid, columns=EVENT_COLUMNS)
                    df["level_id"] = df["level_id"].astype("Int64")
                    df["duration_seconds"] = df["duration_seconds"].astype("Int64")
                    df["batch_id"], df["source_file"], df["ingested_at"] = batch_id, source, now
                    self._con.register("_valid", df)
                    self._con.execute("INSERT INTO bronze.raw_game_events SELECT * FROM _valid")
                    self._con.unregister("_valid")
                if quarantined:
                    q = pd.DataFrame(quarantined, columns=["raw_payload", "reason"])
                    q.insert(0, "source_file", source)
                    q.insert(0, "batch_id", batch_id)
                    q["ingested_at"] = now
                    self._con.register("_q", q)
                    self._con.execute("INSERT INTO bronze.quarantine_events SELECT * FROM _q")
                    self._con.unregister("_q")
                self._con.execute("INSERT INTO bronze.ingestion_batches VALUES (?,?,?,?,?)",
                                  [batch_id, source, len(valid), len(quarantined), now])
                self._con.execute("COMMIT")
            except Exception:
                self._con.execute("ROLLBACK")
                raise
        return {"batch_id": batch_id, "status": "ingested", "accepted": len(valid),
                "quarantined": len(quarantined)}

    def load_campaigns(self, df: pd.DataFrame) -> int:
        with self._lock:
            self._con.execute("DELETE FROM bronze.raw_campaigns")  # tiny reference table: full refresh
            self._con.register("_c", df[["campaign_id", "country", "spend", "installs"]])
            self._con.execute("INSERT INTO bronze.raw_campaigns SELECT * FROM _c")
            self._con.unregister("_c")
        return len(df)

    def query(self, sql: str, params: list | None = None) -> list[tuple]:
        with self._lock:
            return self._con.execute(sql, params or []).fetchall()

    def close(self) -> None:
        self._con.close()
