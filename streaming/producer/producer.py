"""Replay the simulated dataset into Kafka/Redpanda as JSON, keyed by user_id (per-user ordering)."""

from __future__ import annotations

import argparse
import json
import os
from pathlib import Path

import pyarrow.parquet as pq

from ingestion.batch.loader import clean_value


def iter_events(path: Path, limit: int | None):
    sent = 0
    for rb in pq.ParquetFile(path).iter_batches(batch_size=50_000):
        for r in rb.to_pylist():
            yield {k: clean_value(v) for k, v in r.items()}
            sent += 1
            if limit and sent >= limit:
                return


def main() -> None:
    from confluent_kafka import Producer

    ap = argparse.ArgumentParser()
    ap.add_argument("--file", type=Path, default=Path("data/raw/events.parquet"))
    ap.add_argument("--limit", type=int, default=100_000)
    ap.add_argument("--topic", default=os.environ.get("GP_KAFKA_TOPIC", "game-events"))
    a = ap.parse_args()
    p = Producer({"bootstrap.servers": os.environ.get("GP_KAFKA_BOOTSTRAP", "127.0.0.1:19092"),
                  "enable.idempotence": True})
    n = 0
    for ev in iter_events(a.file, a.limit):
        key = (ev.get("user_id") or "unknown").encode()
        while True:
            try:
                p.produce(a.topic, json.dumps(ev).encode(), key=key)
                break
            except BufferError:
                p.poll(0.5)
        n += 1
        if n % 10_000 == 0:
            p.poll(0)
    p.flush()
    print(f"produced {n} events to {a.topic}")


if __name__ == "__main__":
    main()
