"""ASGI entrypoint. GP_STORE=duckdb (default, local) | bigquery (load jobs only)."""

from __future__ import annotations

import os

from ingestion.api.app import create_app


def build():
    if os.environ.get("GP_STORE", "duckdb") == "bigquery":
        from storage.bigquery import BigQueryStore

        store = BigQueryStore()
    else:
        from ingestion.store import BronzeStore

        store = BronzeStore(os.environ.get("GP_DUCKDB_PATH", "data/gamepulse.duckdb"))
    return create_app(store)


app = build() if os.environ.get("GAMEPULSE_API_KEY") else None  # uvicorn ingestion.api.main:app
