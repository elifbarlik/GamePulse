import pandas as pd
import pytest
from fastapi.testclient import TestClient

from ingestion.api.app import MAX_BATCH, create_app
from ingestion.batch.loader import load_events
from ingestion.store import BronzeStore

KEY = "k" * 20
H = {"X-API-Key": KEY}


def ev(i, **kw):
    base = {"event_id": f"e{i}", "event_name": "app_open", "user_id": "u1", "session_id": "s1",
            "event_timestamp": "2026-09-02T10:00:00Z", "country": "TR", "platform": "iOS",
            "app_version": "1.4.0"}
    return {**base, **kw}


@pytest.fixture()
def env():
    store = BronzeStore(":memory:")
    yield store, TestClient(create_app(store, KEY, rate_limit_per_min=5))
    store.close()


def test_requires_api_key(env):
    _, c = env
    assert c.post("/v1/events", json={"events": [ev(1)]}).status_code == 401
    assert c.post("/v1/events", json={"events": [ev(1)]}, headers={"X-API-Key": "x"}).status_code == 401


def test_weak_key_refused():
    with pytest.raises(RuntimeError):
        create_app(BronzeStore(":memory:"), "short")


def test_valid_and_quarantine(env):
    store, c = env
    r = c.post("/v1/events", headers=H, json={"events": [ev(1), ev(2, user_id=None), ev(3, country="ZZ")]})
    assert r.status_code == 200
    j = r.json()
    assert j["accepted"] == 1 and j["quarantined"] == 2
    assert store.query("select count(*) from bronze.raw_game_events")[0][0] == 1
    reasons = {x[0] for x in store.query("select reason from bronze.quarantine_events")}
    assert reasons == {"missing_required_field:user_id", "invalid_value:country"}


def test_same_batch_twice_is_idempotent(env):
    store, c = env
    body = {"events": [ev(1), ev(2)]}
    assert c.post("/v1/events", headers=H, json=body).json()["status"] == "ingested"
    assert c.post("/v1/events", headers=H, json=body).json()["status"] == "duplicate_batch"
    assert store.query("select count(*) from bronze.raw_game_events")[0][0] == 2


def test_batch_size_limit_and_unknown_fields(env):
    _, c = env
    assert c.post("/v1/events", headers=H, json={"events": [ev(i) for i in range(MAX_BATCH + 1)]}).status_code == 422
    assert c.post("/v1/events", headers=H, json={"events": [ev(1)], "x": 1}).status_code == 422
    assert c.post("/v1/events", headers=H, json={"events": []}).status_code == 422


def test_rate_limit(env):
    _, c = env
    codes = [c.post("/v1/events", headers=H, json={"events": [ev(i)]}).status_code for i in range(7)]
    assert codes[:5] == [200] * 5 and codes[5] == 429


def test_body_too_large(env):
    _, c = env
    r = c.post("/v1/events", headers={**H, "content-length": "99999999"}, content=b"{}")
    assert r.status_code == 413


def test_metrics_and_health(env):
    _, c = env
    c.post("/v1/events", headers=H, json={"events": [ev(1)]})
    assert c.get("/healthz").json() == {"status": "ok"}
    assert "gp_ingest_events_total" in c.get("/metrics").text


def test_batch_loader_idempotent(tmp_path):
    from ingestion.simulator.generator import SimConfig, generate_events

    events, camps, _ = generate_events(SimConfig(n_users=300, seed=3))
    p = tmp_path / "events.parquet"
    events.to_parquet(p, index=False)
    store = BronzeStore(":memory:")
    first = load_events(store, p, chunk_rows=2000)
    n1 = store.query("select count(*) from bronze.raw_game_events")[0][0]
    second = load_events(store, p, chunk_rows=2000)
    n2 = store.query("select count(*) from bronze.raw_game_events")[0][0]
    assert first["accepted"] + first["quarantined"] == len(events)
    assert second["skipped_batches"] == second["batches"] and n1 == n2
    assert first["quarantined"] > 0
    assert store.load_campaigns(pd.DataFrame(camps)) == len(camps)
