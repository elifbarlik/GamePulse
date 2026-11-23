"""BigQuery adapter tests with a fake client (no network, no GCP project needed)."""

import pytest

pytest.importorskip("google.cloud.bigquery")

from storage.bigquery import BigQueryStore  # noqa: E402


class FakeJob:
    def __init__(self, rows=()):
        self._rows = rows

    def result(self):
        return self._rows


class FakeClient:
    project = "demo-project"

    def __init__(self, seen_batches=()):
        self.seen = set(seen_batches)
        self.loads = []

    def query(self, sql, job_config=None):
        batch = job_config.query_parameters[0].value
        return FakeJob([1] if batch in self.seen else [])

    def load_table_from_json(self, rows, table, job_config=None):
        self.loads.append((table, len(rows), job_config.write_disposition))
        return FakeJob()

    def close(self):
        pass


def test_new_batch_loads_events_quarantine_then_ledger_last():
    c = FakeClient()
    res = BigQueryStore(c).ingest_batch("b1", "api", [{"event_id": "e1"}], [("{}", "x")])
    assert res["status"] == "ingested" and res["accepted"] == 1
    assert [t.split(".")[-1] for t, *_ in c.loads] == ["raw_game_events", "quarantine_events", "ingestion_batches"]
    assert all(d == "WRITE_APPEND" for *_, d in c.loads)  # never truncates Bronze


def test_known_batch_is_noop():
    c = FakeClient(seen_batches={"b1"})
    res = BigQueryStore(c).ingest_batch("b1", "api", [{"event_id": "e1"}], [])
    assert res["status"] == "duplicate_batch" and c.loads == []
