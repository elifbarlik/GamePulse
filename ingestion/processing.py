"""Shared validate-and-store logic for API, batch loader and streaming consumer."""

from __future__ import annotations

import hashlib
import json
from collections.abc import Iterable
from typing import Any

from ingestion.contracts import validate_event
from ingestion.store import BronzeStore


def content_batch_id(payloads: Iterable[Any]) -> str:
    h = hashlib.sha256()
    for p in payloads:
        h.update(json.dumps(p, sort_keys=True, default=str).encode())
    return "b_" + h.hexdigest()[:24]


def process_batch(store: BronzeStore, batch_id: str, source: str, raw_events: list[Any]) -> dict:
    valid, quarantined = [], []
    reasons: dict[str, int] = {}
    for raw in raw_events:
        ev, reason = validate_event(raw)
        if ev is not None:
            valid.append(ev)
        else:
            quarantined.append((json.dumps(raw, default=str)[:4000], reason))
            reasons[reason] = reasons.get(reason, 0) + 1
    result = store.ingest_batch(batch_id, source, valid, quarantined)
    result["quarantine_reasons"] = reasons
    return result
