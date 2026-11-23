"""Rolling z-score anomaly detection + 'real user loss vs pipeline failure' classification."""

from __future__ import annotations

import numpy as np
import pandas as pd


def rolling_zscore(s: pd.Series, window: int = 14, min_periods: int = 7) -> pd.Series:
    """z-score of each point vs the PREVIOUS `window` points (shifted: no self-leak)."""
    prev = s.shift(1)
    mean = prev.rolling(window, min_periods=min_periods).mean()
    std = prev.rolling(window, min_periods=min_periods).std(ddof=0)
    z = (s - mean) / std.where(std > 0)
    return z


def change_zscore(s: pd.Series, window: int = 14) -> pd.Series:
    """z-score of the day-over-day log change: robust to slow trends (growth / decay)."""
    return rolling_zscore(np.log(s.astype(float)).diff(), window)


def detect_anomalies(df: pd.DataFrame, date_col: str, value_col: str, z_threshold: float = 3.0,
                     window: int = 14, on_change: bool = False) -> pd.DataFrame:
    out = df.sort_values(date_col).reset_index(drop=True).copy()
    vals = out[value_col].astype(float)
    out["z"] = change_zscore(vals, window) if on_change else rolling_zscore(vals, window)
    out["is_anomaly"] = out["z"].abs() > z_threshold
    return out


def _rel_drop(s: pd.Series, window: int = 0) -> pd.Series:
    """Fractional drop vs the previous day (positive = fell)."""
    return 1 - s / s.shift(1)


def classify_dau_drop(daily: pd.DataFrame, z_dau: float = -2.0, z_events: float = -3.0,
                      window: int = 14, min_drop: float = 0.10) -> pd.DataFrame:
    """Expects columns: date, dau, events. Returns flagged days with a verdict.

    * pipeline_issue : event volume AND events-per-active-user collapse together (data went missing
                       while the remaining users look 'thin') -> investigate ingestion first.
    * real_user_loss : DAU falls but events-per-user stays normal -> genuine audience decline.
    """
    d = daily.sort_values("date").reset_index(drop=True).copy()
    d["events_per_user"] = d["events"] / d["dau"]
    d["z_dau"] = change_zscore(d["dau"], window)
    d["z_events"] = change_zscore(d["events"], window)
    d["z_epu"] = change_zscore(d["events_per_user"], window)
    drop_dau = _rel_drop(d["dau"].astype(float), window) >= min_drop
    drop_ev = _rel_drop(d["events"].astype(float), window) >= min_drop
    # statistical AND material: avoids alarms on tiny-variance series
    flagged = d[((d["z_dau"] < z_dau) & drop_dau) | ((d["z_events"] < z_events) & drop_ev)].copy()
    flagged["verdict"] = [
        "pipeline_issue" if (r.z_events < z_events and r.z_epu < z_events) else "real_user_loss"
        for r in flagged.itertuples()
    ]
    return flagged[["date", "dau", "events", "z_dau", "z_events", "z_epu", "verdict"]]
