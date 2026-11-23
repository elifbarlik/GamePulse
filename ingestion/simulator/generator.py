"""Seeded synthetic mobile-game event simulator (ALL DATA IS SIMULATED).

Produces events.parquet, campaigns.csv and scenarios.json (ground truth for demos).
Embedded, documented scenarios:
  * app_version 1.4.2 (live days 30-41) silently drops `level_completed` (tracking bug)
  * pipeline outage on day 50: only ~25 % of that day's events arrive
  * ~1.5 % injected defects: duplicates, future timestamps, null user_id,
    purchase without amount, unknown event names
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from pathlib import Path

import numpy as np
import pandas as pd

START_DATE = datetime(2026, 9, 1, tzinfo=UTC)
N_DAYS = 60
INSTALL_DAYS = 45
COUNTRIES = ["TR", "DE", "US", "GB", "FR", "BR", "IN", "JP"]
COUNTRY_P = [0.18, 0.12, 0.25, 0.08, 0.07, 0.12, 0.13, 0.05]
# per-country quality multipliers (retention, purchase) and CPI in USD
COUNTRY_QUALITY = {"TR": (0.9, 0.7), "DE": (1.1, 1.2), "US": (1.1, 1.5), "GB": (1.05, 1.2),
                   "FR": (1.0, 1.0), "BR": (0.9, 0.7), "IN": (0.8, 0.4), "JP": (1.15, 1.4)}
COUNTRY_CPI = {"TR": 0.35, "DE": 1.6, "US": 2.4, "GB": 1.8, "FR": 1.3, "BR": 0.5, "IN": 0.2, "JP": 2.0}
VERSIONS = [("1.3.0", 0), ("1.4.0", 14), ("1.4.1", 24), ("1.4.2", 30), ("1.4.3", 42)]
BUGGY_VERSION = "1.4.2"
OUTAGE_DAY = 50
CAMPAIGNS_PER_COUNTRY = 2
ORGANIC_SHARE = 0.3


@dataclass(frozen=True)
class SimConfig:
    n_users: int = 50_000
    seed: int = 42
    defect_rate: float = 0.015


def _version_for_day(day: int) -> str:
    return [v for v, start in VERSIONS if start <= day][-1]


def _build_users(cfg: SimConfig, rng: np.random.Generator) -> pd.DataFrame:
    n = cfg.n_users
    install_day = np.minimum(rng.gamma(2.0, 9.0, n).astype(int), INSTALL_DAYS - 1)
    country = rng.choice(COUNTRIES, n, p=COUNTRY_P)
    platform = rng.choice(["Android", "iOS"], n, p=[0.68, 0.32])
    camp_idx = rng.integers(1, CAMPAIGNS_PER_COUNTRY + 1, n)
    organic = rng.random(n) < ORGANIC_SHARE
    campaign = np.where(organic, None, [f"camp_{c}_{i}" for c, i in zip(country, camp_idx, strict=True)])
    return pd.DataFrame({
        "user_id": [f"user_{i:06d}" for i in range(n)],
        "install_day": install_day,
        "country": country,
        "platform": platform,
        "campaign_id": campaign,
        "completes_tutorial": rng.random(n) < 0.72,
        "payer_propensity": rng.beta(1, 25, n),
        "skill": rng.beta(4, 3, n),
    })


def generate_events(cfg: SimConfig) -> tuple[pd.DataFrame, pd.DataFrame, dict]:
    rng = np.random.default_rng(cfg.seed)
    users = _build_users(cfg, rng)
    rows: list[tuple] = []
    eid = 0

    def add(name, user, sess, ts, country, platform, ver, camp, level=None, dur=None, amt=None, ad=None):
        nonlocal eid
        eid += 1
        rows.append((f"evt_{eid:08d}", name, user, sess, ts, country, platform, ver, camp,
                     level, dur, amt, ad))

    sess_no = 0
    for u in users.itertuples(index=False):
        q_ret, q_pay = COUNTRY_QUALITY[u.country]
        base = 0.42 * q_ret * (1.35 if u.completes_tutorial else 0.8)
        tau = 6.0 * q_ret * (1.5 if u.completes_tutorial else 1.0)
        max_level = 0
        for d in range(u.install_day, N_DAYS):
            age = d - u.install_day
            if age > 0 and rng.random() > min(0.95, base * np.exp(-(age - 1) / tau) + 0.02):
                continue
            version = _version_for_day(d)
            for s in range(1 + int(rng.random() < 0.3)):
                sess_no += 1
                sid = f"sess_{sess_no:08d}"
                t = START_DATE + timedelta(days=d, seconds=int(rng.integers(6 * 3600, 23 * 3600)))
                common = (u.user_id, sid, u.country, u.platform, version, u.campaign_id)

                def emit(name, dt, **kw):
                    ts = t + timedelta(seconds=dt)
                    add(name, common[0], common[1], ts, *common[2:], **kw)

                emit("app_open", 0)
                cur = 3
                if age == 0 and s == 0:
                    emit("tutorial_started", cur)
                    cur += 5
                    if u.completes_tutorial:
                        dur = int(rng.integers(40, 180))
                        cur += dur
                        emit("tutorial_completed", cur, dur=dur)
                    else:
                        continue
                elif not u.completes_tutorial and age == 0:
                    continue
                for _ in range(max(1, int(rng.poisson(2.5)))):
                    lvl = max_level + 1
                    emit("level_started", cur, level=lvl)
                    dur = int(rng.integers(30, 240))
                    cur += dur
                    p_win = np.clip(u.skill * 1.1 - lvl * 0.012, 0.1, 0.95)
                    if rng.random() < p_win:
                        max_level = lvl
                        if not (version == BUGGY_VERSION):
                            emit("level_completed", cur, level=lvl, dur=dur)
                    else:
                        emit("level_failed", cur, level=lvl, dur=dur)
                    cur += 2
                    if lvl > 8 and rng.random() < 0.06 * (lvl - 8) ** 0.5:
                        break  # difficulty wall -> session ends early
                if rng.random() < 0.55:
                    emit("ad_watched", cur, ad=round(float(rng.uniform(0.005, 0.05)), 4))
                    cur += 30
                if rng.random() < u.payer_propensity * q_pay * 0.6:
                    amt = float(rng.choice([0.99, 1.99, 4.99, 9.99, 19.99], p=[.4, .25, .2, .1, .05]))
                    emit("purchase_completed", cur, amt=amt)

    cols = ["event_id", "event_name", "user_id", "session_id", "event_timestamp", "country",
            "platform", "app_version", "campaign_id", "level_id", "duration_seconds",
            "purchase_amount", "ad_revenue"]
    ev = pd.DataFrame(rows, columns=cols)
    ev["level_id"] = ev["level_id"].astype("Int64")
    ev["duration_seconds"] = ev["duration_seconds"].astype("Int64")

    # Outage scenario: drop 75 % of events on OUTAGE_DAY
    outage_start = START_DATE + timedelta(days=OUTAGE_DAY)
    in_outage = (ev["event_timestamp"] >= outage_start) & (ev["event_timestamp"] < outage_start + timedelta(days=1))
    drop = in_outage & (rng.random(len(ev)) < 0.75)
    ev = ev[~drop].reset_index(drop=True)

    ev = inject_defects(ev, cfg, rng)
    campaigns = build_campaigns(users, rng)
    scenarios = {
        "simulated": True,
        "seed": cfg.seed,
        "start_date": START_DATE.date().isoformat(),
        "buggy_version": BUGGY_VERSION,
        "buggy_version_live_days": [30, 41],
        "tracking_bug": f"{BUGGY_VERSION} never emits level_completed",
        "outage_date": (START_DATE + timedelta(days=OUTAGE_DAY)).date().isoformat(),
        "outage_event_loss_pct": 75,
        "n_users": cfg.n_users,
        "n_events": int(len(ev)),
    }
    return ev, campaigns, scenarios


def inject_defects(ev: pd.DataFrame, cfg: SimConfig, rng: np.random.Generator) -> pd.DataFrame:
    n = len(ev)
    k = max(1, int(n * cfg.defect_rate / 5))
    ev = ev.copy()
    idx = rng.choice(n, size=4 * k, replace=False)
    fut, nul, noamt_pool, unk = idx[:k], idx[k:2 * k], idx[2 * k:3 * k], idx[3 * k:]
    ev.loc[fut, "event_timestamp"] = ev.loc[fut, "event_timestamp"] + pd.Timedelta(days=400)
    ev.loc[nul, "user_id"] = None
    purchases = ev.index[ev["event_name"] == "purchase_completed"]
    kill = rng.choice(purchases, size=min(k, len(purchases)), replace=False)
    ev.loc[kill, "purchase_amount"] = np.nan
    ev.loc[unk, "event_name"] = "level_skipped"
    dup = ev.iloc[rng.choice(n, size=k, replace=False)]
    return pd.concat([ev, dup], ignore_index=True).sample(frac=1.0, random_state=cfg.seed).reset_index(drop=True)


def build_campaigns(users: pd.DataFrame, rng: np.random.Generator) -> pd.DataFrame:
    paid = users[users["campaign_id"].notna()]
    g = paid.groupby(["campaign_id", "country"]).size().reset_index(name="installs")
    cpi = g["country"].map(COUNTRY_CPI) * rng.uniform(0.8, 1.25, len(g))
    g["spend"] = (g["installs"] * cpi).round(2)
    return g[["campaign_id", "country", "spend", "installs"]].sort_values("campaign_id").reset_index(drop=True)


def write_dataset(cfg: SimConfig, out_dir: Path) -> dict:
    out_dir.mkdir(parents=True, exist_ok=True)
    ev, campaigns, scenarios = generate_events(cfg)
    ev.to_parquet(out_dir / "events.parquet", index=False)
    campaigns.to_csv(out_dir / "campaigns.csv", index=False)
    (out_dir / "scenarios.json").write_text(json.dumps(scenarios, indent=2), encoding="utf-8")
    return scenarios


if __name__ == "__main__":
    import argparse

    ap = argparse.ArgumentParser(description="Generate SIMULATED GamePulse data")
    ap.add_argument("--users", type=int, default=50_000)
    ap.add_argument("--seed", type=int, default=42)
    ap.add_argument("--out", type=Path, default=Path("data/raw"))
    a = ap.parse_args()
    print(json.dumps(write_dataset(SimConfig(a.users, a.seed), a.out), indent=2))
