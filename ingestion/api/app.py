"""FastAPI ingestion service: API-key auth, size/rate limits, strict validation, idempotent batches."""

from __future__ import annotations

import hmac
import os
import time
from collections import defaultdict, deque

from fastapi import Depends, FastAPI, Header, HTTPException, Request, Response
from prometheus_client import CONTENT_TYPE_LATEST, CollectorRegistry, Counter, generate_latest
from pydantic import BaseModel, ConfigDict, Field

from ingestion.processing import content_batch_id, process_batch
from ingestion.store import BronzeStore

MAX_BATCH = 1000
MAX_BODY_BYTES = 1_000_000


class BatchIn(BaseModel):
    model_config = ConfigDict(extra="forbid")
    events: list[dict] = Field(min_length=1, max_length=MAX_BATCH)
    batch_id: str | None = Field(default=None, pattern=r"^[A-Za-z0-9_\-]{1,64}$")


class RateLimiter:
    """Sliding-window limiter per client key (in-memory; fine for a single instance)."""

    def __init__(self, limit: int, window_s: float = 60.0):
        self.limit, self.window = limit, window_s
        self.hits: dict[str, deque[float]] = defaultdict(deque)

    def allow(self, key: str) -> bool:
        now = time.monotonic()
        q = self.hits[key]
        while q and now - q[0] > self.window:
            q.popleft()
        if len(q) >= self.limit:
            return False
        q.append(now)
        return True


def create_app(store: BronzeStore, api_key: str | None = None, rate_limit_per_min: int = 120) -> FastAPI:
    key = api_key or os.environ.get("GAMEPULSE_API_KEY", "")
    if len(key) < 16:
        raise RuntimeError("GAMEPULSE_API_KEY must be set and at least 16 characters")
    limiter = RateLimiter(rate_limit_per_min)
    registry = CollectorRegistry()
    m_events = Counter("gp_ingest_events_total", "Events by outcome", ["outcome"], registry=registry)
    m_batches = Counter("gp_ingest_batches_total", "Batches by status", ["status"], registry=registry)

    app = FastAPI(title="GamePulse Ingestion", docs_url=None, redoc_url=None, openapi_url=None)

    @app.middleware("http")
    async def limit_body(request: Request, call_next):
        cl = request.headers.get("content-length")
        if cl and cl.isdigit() and int(cl) > MAX_BODY_BYTES:
            return Response("payload too large", status_code=413)
        return await call_next(request)

    def auth(x_api_key: str = Header(default="")):
        if not hmac.compare_digest(x_api_key.encode(), key.encode()):
            raise HTTPException(status_code=401, detail="invalid api key")
        return x_api_key

    @app.get("/healthz")
    def healthz():
        return {"status": "ok"}

    @app.get("/metrics")
    def metrics():
        return Response(generate_latest(registry), media_type=CONTENT_TYPE_LATEST)

    @app.post("/v1/events", status_code=200)
    def ingest(body: BatchIn, client_key: str = Depends(auth)):
        if not limiter.allow(client_key):
            raise HTTPException(status_code=429, detail="rate limit exceeded")
        batch_id = body.batch_id or content_batch_id(body.events)
        res = process_batch(store, batch_id, "api", body.events)
        m_batches.labels(res["status"]).inc()
        m_events.labels("accepted").inc(res["accepted"])
        m_events.labels("quarantined").inc(res["quarantined"])
        return res

    return app
