"""BigQuery adapters (free-tier friendly: batch LOAD jobs only, no streaming inserts / DML).

* BigQueryStore  - same ingest_batch interface as the DuckDB BronzeStore (optional API backend).
* export_duckdb_to_bigquery - one-shot loader of the local Bronze tables (WRITE_TRUNCATE => idempotent).

NOTE: written against the public google-cloud-bigquery API and unit-tested with a fake client;
it has not been executed against a live GCP project in this repository's CI.
"""

from __future__ import annotations

import json
import os
import tempfile
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

BRONZE_TABLES = ["raw_game_events", "quarantine_events", "ingestion_batches", "raw_campaigns"]


def _client(project: str | None = None):
    from google.cloud import bigquery  # lazy: optional dependency

    return bigquery.Client(project=project or os.environ["GCP_PROJECT_ID"])


class BigQueryStore:
    def __init__(self, client=None, dataset: str = "bronze"):
        self.client = client or _client()
        self.dataset = dataset

    def _table(self, name: str) -> str:
        return f"{self.client.project}.{self.dataset}.{name}"

    def _load_json(self, table: str, rows: list[dict[str, Any]]) -> None:
        from google.cloud import bigquery

        cfg = bigquery.LoadJobConfig(write_disposition="WRITE_APPEND",
                                     source_format=bigquery.SourceFormat.NEWLINE_DELIMITED_JSON,
                                     autodetect=False,
                                     schema_update_options=[])
        self.client.load_table_from_json(rows, self._table(table), job_config=cfg).result()

    def ingest_batch(self, batch_id: str, source: str, valid: list[dict[str, Any]],
                     quarantined: list[tuple[str, str]]) -> dict[str, Any]:
        """Ledger is written LAST: a crash in between only causes a re-load whose duplicates Silver removes."""
        from google.cloud import bigquery

        q = f"SELECT 1 FROM `{self._table('ingestion_batches')}` WHERE batch_id = @b LIMIT 1"  # noqa: S608 - identifier from config, value is a query parameter  # nosec B608
        job = self.client.query(q, job_config=bigquery.QueryJobConfig(
            query_parameters=[bigquery.ScalarQueryParameter("b", "STRING", batch_id)]))
        if list(job.result()):
            return {"batch_id": batch_id, "status": "duplicate_batch", "accepted": 0, "quarantined": 0}
        now = datetime.now(UTC).isoformat()
        if valid:
            self._load_json("raw_game_events",
                            [{**r, "batch_id": batch_id, "source_file": source, "ingested_at": now} for r in valid])
        if quarantined:
            self._load_json("quarantine_events",
                            [{"batch_id": batch_id, "source_file": source, "raw_payload": p, "reason": r,
                              "ingested_at": now} for p, r in quarantined])
        self._load_json("ingestion_batches", [{"batch_id": batch_id, "source_file": source,
                                               "n_valid": len(valid), "n_quarantined": len(quarantined),
                                               "ingested_at": now}])
        return {"batch_id": batch_id, "status": "ingested", "accepted": len(valid),
                "quarantined": len(quarantined)}

    def close(self) -> None:
        self.client.close()


def export_duckdb_to_bigquery(db_path: str, client=None, dataset: str = "bronze") -> dict[str, int]:
    import duckdb
    from google.cloud import bigquery

    client = client or _client()
    client.create_dataset(bigquery.Dataset(f"{client.project}.{dataset}"), exists_ok=True)
    con = duckdb.connect(db_path, read_only=True)
    loaded: dict[str, int] = {}
    with tempfile.TemporaryDirectory() as tmp:
        for t in BRONZE_TABLES:
            f = Path(tmp) / f"{t}.parquet"
            con.execute(f"COPY bronze.{t} TO '{f.as_posix()}' (FORMAT PARQUET)")  # noqa: S608
            cfg = bigquery.LoadJobConfig(source_format=bigquery.SourceFormat.PARQUET,
                                         write_disposition="WRITE_TRUNCATE")
            with f.open("rb") as fh:
                client.load_table_from_file(fh, f"{client.project}.{dataset}.{t}", job_config=cfg).result()
            loaded[t] = con.execute(f"select count(*) from bronze.{t}").fetchone()[0]  # noqa: S608  # nosec B608
    con.close()
    return loaded


if __name__ == "__main__":
    import argparse

    ap = argparse.ArgumentParser(description="Load local Bronze tables into BigQuery (needs GCP_PROJECT_ID + ADC)")
    ap.add_argument("--db", default="data/gamepulse.duckdb")
    print(json.dumps(export_duckdb_to_bigquery(ap.parse_args().db), indent=2))
