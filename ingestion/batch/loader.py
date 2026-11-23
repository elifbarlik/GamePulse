"""Batch loader: Parquet -> validate -> Bronze. Re-running the same file is a no-op."""

from __future__ import annotations

import argparse
import hashlib
import math
from datetime import datetime
from pathlib import Path

import pandas as pd
import pyarrow.parquet as pq

from ingestion.processing import process_batch
from ingestion.store import BronzeStore


def clean_value(v):
    if v is None or v is pd.NA or (isinstance(v, float) and math.isnan(v)):
        return None
    if isinstance(v, datetime):  # pd.Timestamp is a datetime subclass
        return v.isoformat()
    if hasattr(v, "item"):
        return v.item()
    return v


def file_digest(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as fh:
        for block in iter(lambda: fh.read(1 << 20), b""):
            h.update(block)
    return h.hexdigest()


def load_events(store: BronzeStore, path: Path, chunk_rows: int = 200_000) -> dict:
    digest = file_digest(path)[:16]
    totals = {"accepted": 0, "quarantined": 0, "skipped_batches": 0, "batches": 0}
    pf = pq.ParquetFile(path)
    for i, rb in enumerate(pf.iter_batches(batch_size=chunk_rows)):
        records = [{k: clean_value(v) for k, v in r.items()} for r in rb.to_pylist()]
        res = process_batch(store, f"f_{digest}_{i:05d}", path.name, records)
        totals["batches"] += 1
        if res["status"] == "duplicate_batch":
            totals["skipped_batches"] += 1
        totals["accepted"] += res["accepted"]
        totals["quarantined"] += res["quarantined"]
    return totals


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--raw-dir", type=Path, default=Path("data/raw"))
    ap.add_argument("--db", default="data/gamepulse.duckdb")
    a = ap.parse_args()
    store = BronzeStore(a.db)
    print(load_events(store, a.raw_dir / "events.parquet"))
    print("campaigns:", store.load_campaigns(pd.read_csv(a.raw_dir / "campaigns.csv")))
    store.close()


if __name__ == "__main__":
    main()
