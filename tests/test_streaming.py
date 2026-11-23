import json

from ingestion.batch.loader import clean_value
from ingestion.processing import process_batch
from ingestion.simulator.generator import SimConfig, generate_events
from ingestion.store import BronzeStore
from streaming.consumer.consumer import Message, process_messages
from streaming.producer.producer import iter_events


def msgs(events, start=0):
    return [Message("game-events", 0, start + i, json.dumps(e).encode()) for i, e in enumerate(events)]


def good(i):
    return {"event_id": f"e{i}", "event_name": "app_open", "user_id": "u1", "session_id": "s1",
            "event_timestamp": "2026-09-02T10:00:00Z", "country": "TR", "platform": "iOS",
            "app_version": "1.4.0"}


def test_consumer_validates_and_quarantines():
    store = BronzeStore(":memory:")
    m = msgs([good(1), {**good(2), "user_id": None}]) + [Message("game-events", 0, 2, b"{not json")]
    res = process_messages(store, m)
    assert res["accepted"] == 1 and res["quarantined"] == 2
    reasons = {r[0] for r in store.query("select reason from bronze.quarantine_events")}
    assert "missing_required_field:user_id" in reasons and "invalid_payload" in reasons


def test_replaying_same_offsets_is_idempotent():
    store = BronzeStore(":memory:")
    batch = msgs([good(i) for i in range(10)])
    process_messages(store, batch)
    again = process_messages(store, batch)  # consumer crash before commit -> redelivery
    assert again["status"] == "duplicate_batch"
    assert store.query("select count(*) from bronze.raw_game_events")[0][0] == 10


def test_batch_and_streaming_agree(tmp_path):
    events, _, _ = generate_events(SimConfig(n_users=200, seed=11))
    p = tmp_path / "e.parquet"
    events.to_parquet(p, index=False)
    records = list(iter_events(p, 3000))

    batch_store, stream_store = BronzeStore(":memory:"), BronzeStore(":memory:")
    process_batch(batch_store, "b1", "batch", records)
    for i in range(0, len(records), 500):
        process_messages(stream_store, msgs(records[i:i + 500], start=i))

    q = ("select count(*), count(distinct event_id), count(distinct user_id), "
         "sum(coalesce(purchase_amount, 0)) from bronze.raw_game_events")
    assert batch_store.query(q) == stream_store.query(q)
    assert (batch_store.query("select count(*) from bronze.quarantine_events")
            == stream_store.query("select count(*) from bronze.quarantine_events"))
    assert clean_value(None) is None
