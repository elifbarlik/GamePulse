"""Kafka/Redpanda consumer: micro-batches -> same validation as the API -> Bronze.

Delivery is at-least-once (offsets committed AFTER the Bronze write); the batch_id derived from
topic/partition/offset range makes replays idempotent, so the effective result is exactly-once.
"""

from __future__ import annotations

import json
import os
import time
from dataclasses import dataclass

from prometheus_client import Counter, Gauge, Histogram, start_http_server

from ingestion.processing import process_batch
from ingestion.store import BronzeStore

TOPIC = os.environ.get("GP_KAFKA_TOPIC", "game-events")

EVENTS = Counter("gp_consumer_events_total", "Consumed events by outcome", ["outcome"])
LAG = Gauge("gp_consumer_lag", "Messages behind the partition high watermark", ["partition"])
BATCH_SECONDS = Histogram("gp_consumer_batch_seconds", "Micro-batch processing time")
LAST_SUCCESS = Gauge("gp_consumer_last_success_timestamp", "Unix time of last stored batch")


@dataclass(frozen=True)
class Message:
    topic: str
    partition: int
    offset: int
    value: bytes


def process_messages(store: BronzeStore, messages: list[Message]) -> dict:
    """Pure-ish unit (no Kafka needed): decode, validate, store one micro-batch idempotently."""
    first, last = messages[0], messages[-1]
    batch_id = f"k_{first.topic}_{first.partition}_{first.offset}_{last.offset}"
    payloads = []
    for m in messages:
        try:
            payloads.append(json.loads(m.value))
        except (ValueError, UnicodeDecodeError):
            payloads.append(m.value[:200].decode("utf-8", "replace"))  # non-dict -> invalid_payload
    t0 = time.perf_counter()
    res = process_batch(store, batch_id, f"kafka:{first.topic}:{first.partition}", payloads)
    BATCH_SECONDS.observe(time.perf_counter() - t0)
    EVENTS.labels("accepted").inc(res["accepted"])
    EVENTS.labels("quarantined").inc(res["quarantined"])
    LAST_SUCCESS.set(time.time())
    return res


def run(db_path: str, batch_size: int = 500, poll_s: float = 1.0, metrics_port: int = 8001) -> None:
    from confluent_kafka import Consumer  # imported lazily so tests don't need a broker

    start_http_server(metrics_port, addr="127.0.0.1")
    store = BronzeStore(db_path)
    consumer = Consumer({
        "bootstrap.servers": os.environ.get("GP_KAFKA_BOOTSTRAP", "127.0.0.1:19092"),
        "group.id": "gamepulse-bronze-writer",
        "enable.auto.commit": False,
        "auto.offset.reset": "earliest",
    })
    consumer.subscribe([TOPIC])
    try:
        while True:
            msgs = consumer.consume(num_messages=batch_size, timeout=poll_s)
            batch: dict[int, list[Message]] = {}
            for m in msgs:
                if m.error():
                    EVENTS.labels("kafka_error").inc()
                    continue
                batch.setdefault(m.partition(), []).append(Message(m.topic(), m.partition(), m.offset(), m.value()))
            for part, items in batch.items():
                process_messages(store, items)
                _, high = consumer.get_watermark_offsets(
                    __import__("confluent_kafka").TopicPartition(TOPIC, part), timeout=2)
                LAG.labels(str(part)).set(max(0, high - (items[-1].offset + 1)))
            if msgs:
                consumer.commit(asynchronous=False)
    finally:
        consumer.close()
        store.close()


if __name__ == "__main__":
    run(os.environ.get("GP_STREAM_DUCKDB_PATH", "data/gamepulse_stream.duckdb"))
