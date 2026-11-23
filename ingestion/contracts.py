"""Event data contract: Pydantic structural validation + dictionary-driven rules.

`validate_event` never raises; it returns (normalized_event, None) or (None, reason_code).
Reason codes are stable strings used in the quarantine table and metrics.
"""

from __future__ import annotations

from datetime import UTC, datetime
from functools import lru_cache
from pathlib import Path
from typing import Annotated, Any

import yaml
from pydantic import BaseModel, ConfigDict, Field, StringConstraints, ValidationError

DICTIONARY_PATH = Path(__file__).resolve().parent.parent / "storage" / "schemas" / "event_dictionary.yaml"

EVENT_COLUMNS = [
    "event_id",
    "event_name",
    "user_id",
    "session_id",
    "event_timestamp",
    "country",
    "platform",
    "app_version",
    "campaign_id",
    "level_id",
    "duration_seconds",
    "purchase_amount",
    "ad_revenue",
]

_Id = Annotated[str, StringConstraints(pattern=r"^[A-Za-z0-9_\-]{1,64}$")]
_Version = Annotated[str, StringConstraints(pattern=r"^\d{1,3}\.\d{1,3}\.\d{1,3}$")]


class EventIn(BaseModel):
    """Structural contract. Required-ness is enforced by the dictionary, not here."""

    model_config = ConfigDict(extra="forbid", strict=False)

    event_id: _Id | None = None
    event_name: str | None = None
    user_id: _Id | None = None
    session_id: _Id | None = None
    event_timestamp: datetime | None = None
    country: str | None = None
    platform: str | None = None
    app_version: _Version | None = None
    campaign_id: _Id | None = None
    level_id: int | None = Field(default=None, ge=1, le=500)
    duration_seconds: int | None = Field(default=None, ge=0, le=86_400)
    purchase_amount: float | None = Field(default=None, gt=0, le=1000)
    ad_revenue: float | None = Field(default=None, ge=0, le=10)


@lru_cache(maxsize=1)
def load_dictionary() -> dict[str, Any]:
    with DICTIONARY_PATH.open(encoding="utf-8") as fh:
        return yaml.safe_load(fh)


def event_names() -> list[str]:
    return list(load_dictionary()["events"])


def _reason_from_pydantic(err: ValidationError) -> str:
    first = err.errors()[0]
    field = ".".join(str(p) for p in first["loc"]) or "body"
    if first["type"] == "extra_forbidden":
        return f"unknown_field:{field}"
    return f"invalid_value:{field}"


def validate_event(raw: Any) -> tuple[dict[str, Any] | None, str | None]:
    if not isinstance(raw, dict):
        return None, "invalid_payload"
    spec = load_dictionary()
    name = raw.get("event_name")
    if name not in spec["events"]:
        return None, "unknown_event_name"
    try:
        ev = EventIn.model_validate(raw)
    except ValidationError as err:
        return None, _reason_from_pydantic(err)
    if ev.event_timestamp is not None and ev.event_timestamp.tzinfo is None:
        return None, "invalid_value:event_timestamp"

    data = ev.model_dump()
    required = spec["common_required"] + spec["events"][name]["required"]
    for col in required:
        if data[col] is None:
            return None, f"missing_required_field:{col}"
    allowed = set(required) | set(spec["common_optional"]) | set(spec["events"][name]["optional"])
    for col in EVENT_COLUMNS:
        if data[col] is not None and col not in allowed:
            return None, f"unexpected_field_for_event:{col}"
    for col, values in spec["enums"].items():
        if data[col] not in values:
            return None, f"invalid_value:{col}"

    data["event_timestamp"] = ev.event_timestamp.astimezone(UTC).strftime("%Y-%m-%dT%H:%M:%S.%fZ")
    return data, None
