"""Render the 4 analytics dashboards as PNGs from the Gold marts (offline, no BI licence needed).

Usage: python -m dashboard.render_report [--db data/gamepulse.duckdb] [--out docs/img]
Looker Studio equivalents point at the same gold.* tables (see docs/looker_studio.md).
"""

from __future__ import annotations

import argparse
from pathlib import Path

import duckdb
import matplotlib
import pandas as pd

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402

C = {"blue": "#2f6fdb", "teal": "#1a9e8f", "orange": "#e0892b", "red": "#d1495b", "grey": "#8a8f98"}
BUG_DAY, OUTAGE_DAY = "2026-10-01", "2026-10-21"


def _style():
    plt.rcParams.update({"axes.spines.top": False, "axes.spines.right": False, "axes.grid": True,
                         "grid.alpha": 0.25, "font.size": 9, "axes.titlesize": 10,
                         "axes.titleweight": "bold", "figure.dpi": 110})


def _mark(ax, df_dates):
    for d, label in ((BUG_DAY, "v1.4.2 tracking bug"), (OUTAGE_DAY, "pipeline outage")):
        d = pd.Timestamp(d)
        ax.axvline(d, color=C["red"], ls="--", lw=0.8, alpha=0.7)
        ax.text(d, ax.get_ylim()[1], " " + label, color=C["red"], fontsize=7, va="top", rotation=90)


def game_performance(con, out: Path):
    dau = con.execute("select * from gold.mart_dau_wau_mau order by 1").df()
    ses = con.execute("select * from gold.mart_session_metrics order by 1").df()
    fig, ax = plt.subplots(2, 2, figsize=(12, 7))
    ax[0, 0].plot(dau.activity_date, dau.dau, color=C["blue"], label="DAU")
    ax[0, 0].plot(dau.activity_date, dau.wau / 7, color=C["teal"], label="WAU / 7")
    ax[0, 0].set(title="DAU and WAU (scaled) — drop on 21 Oct is a pipeline outage, not churn")
    ax[0, 0].legend(frameon=False)
    _mark(ax[0, 0], dau.activity_date)
    full = dau[dau.is_full_mau_window]
    ax[0, 1].plot(full.activity_date, full.stickiness * 100, color=C["orange"])
    ax[0, 1].set(title="Stickiness (DAU / MAU, %)", ylabel="%")
    ax[1, 0].plot(ses.activity_date, ses.avg_session_seconds / 60, color=C["blue"])
    ax[1, 0].set(title="Average session length (min)")
    ax[1, 1].plot(ses.activity_date, ses.level_completion_rate * 100, color=C["teal"])
    ax[1, 1].set(title="Level completion rate (%) — dip = v1.4.2 never emits level_completed")
    _mark(ax[1, 1], ses.activity_date)
    for a in ax.flat:
        a.tick_params(axis="x", rotation=30)
    fig.suptitle("GamePulse — Game Performance (simulated data)", fontweight="bold")
    fig.tight_layout()
    fig.savefig(out / "dashboard_1_game_performance.png")
    plt.close(fig)


def retention(con, out: Path):
    fig, ax = plt.subplots(1, 3, figsize=(13, 4.2))
    t = con.execute("""select day_n, tutorial_completed, sum(retained_users)*1.0/sum(cohort_users) r
        from gold.mart_retention group by 1,2 order by 1,2""").df()
    for i, (flag, color, lab) in enumerate(((True, C["teal"], "tutorial completed"),
                                            (False, C["grey"], "tutorial skipped"))):
        s = t[t.tutorial_completed == flag]
        ax[0].bar([x + i * 0.38 for x in range(len(s))], s.r * 100, 0.36, color=color, label=lab)
    ax[0].set_xticks([0.19, 1.19, 2.19], ["D1", "D7", "D30"])
    ax[0].set(title="Retention by tutorial completion (%)")
    ax[0].legend(frameon=False)
    c = con.execute("""select country, sum(retained_users)*1.0/sum(cohort_users) r
        from gold.mart_retention where day_n = 7 group by 1 order by 2 desc""").df()
    ax[1].bar(c.country, c.r * 100, color=C["blue"])
    ax[1].set(title="D7 retention by country (%)")
    p = con.execute("""select cohort_date, sum(retained_users)*1.0/sum(cohort_users) r
        from gold.mart_retention where day_n = 1 group by 1 order by 1""").df()
    ax[2].plot(p.cohort_date, p.r * 100, color=C["orange"])
    ax[2].set(title="D1 retention by signup cohort (%)")
    ax[2].tick_params(axis="x", rotation=30)
    fig.suptitle("GamePulse — Retention & Cohorts (simulated data)", fontweight="bold")
    fig.tight_layout()
    fig.savefig(out / "dashboard_2_retention.png")
    plt.close(fig)


def funnel(con, out: Path):
    f = con.execute("""select sum(app_open_users) a, sum(tutorial_started_users) b,
        sum(tutorial_completed_users) c, sum(level_1_completed_users) d, sum(purchase_users) e
        from gold.mart_funnel""").fetchone()
    names = ["app_open", "tutorial_started", "tutorial_completed", "level_1_completed", "purchase"]
    lv = con.execute("select * from gold.mart_level_dropoff where level_id <= 30 order by 1").df()
    fig, ax = plt.subplots(1, 2, figsize=(13, 4.6))
    ax[0].barh(names[::-1], [int(x) for x in f][::-1], color=C["blue"])
    for i, v in enumerate([int(x) for x in f][::-1]):
        ax[0].text(v, i, f" {v:,} ({v / f[0] * 100:.1f}%)", va="center", fontsize=8)
    ax[0].set(title="Order-aware per-user funnel", xlim=(0, f[0] * 1.25))
    ax[1].bar(lv.level_id, lv.churned_users, color=C["red"], alpha=0.8, label="users who stopped here")
    ax2 = ax[1].twinx()
    ax2.plot(lv.level_id, lv.completion_rate * 100, color=C["teal"], label="completion rate %")
    ax2.set_ylim(0, 100)
    ax2.grid(False)
    ax[1].set(title="Level drop-off (levels 1–30)", xlabel="level")
    h1, l1 = ax[1].get_legend_handles_labels()
    h2, l2 = ax2.get_legend_handles_labels()
    ax[1].legend(h1 + h2, l1 + l2, loc="upper right", frameon=False)
    fig.suptitle("GamePulse — Conversion Funnel (simulated data)", fontweight="bold")
    fig.tight_layout()
    fig.savefig(out / "dashboard_3_funnel.png")
    plt.close(fig)


def marketing(con, out: Path):
    m = con.execute("select * from gold.mart_campaign_performance order by roas desc").df()
    fig, ax = plt.subplots(1, 3, figsize=(14, 4.6))
    ax[0].barh(m.campaign_id[::-1], m.cpi[::-1], color=C["orange"])
    ax[0].set(title="CPI by campaign (USD)")
    colors = [C["teal"] if r >= 1 else C["red"] for r in m.roas[::-1]]
    ax[1].barh(m.campaign_id[::-1], m.roas[::-1], color=colors)
    ax[1].axvline(1, color="black", lw=0.8)
    ax[1].set(title="ROAS by campaign (1.0 = break-even)")
    ax[2].scatter(m.spend, m.revenue, color=C["blue"])
    for r in m.itertuples():
        ax[2].annotate(r.campaign_id.replace("camp_", ""), (r.spend, r.revenue), fontsize=7)
    lim = max(m.spend.max(), m.revenue.max())
    ax[2].plot([0, lim], [0, lim], color=C["grey"], ls="--", lw=0.8)
    ax[2].set(title="Spend vs revenue (USD)", xlabel="spend", ylabel="revenue")
    fig.suptitle("GamePulse — Marketing Performance (simulated data)", fontweight="bold")
    fig.tight_layout()
    fig.savefig(out / "dashboard_4_marketing.png")
    plt.close(fig)


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--db", default="data/gamepulse.duckdb")
    ap.add_argument("--out", type=Path, default=Path("docs/img"))
    a = ap.parse_args()
    a.out.mkdir(parents=True, exist_ok=True)
    _style()
    con = duckdb.connect(a.db, read_only=True)
    for fn in (game_performance, retention, funnel, marketing):
        fn(con, a.out)
    print("rendered 4 dashboards to", a.out)


if __name__ == "__main__":
    main()
