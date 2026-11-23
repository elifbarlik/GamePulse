"""KPI assistant: maps a natural-language question to an ALLOWLISTED, parameterised SQL template.

Security model: the question text is never interpolated into SQL and no model writes SQL.
Only the template id and a validated integer parameter (retention horizon) are chosen from the text.
Every answer carries the exact SQL + source tables so a human can verify it. Read-only connection.
No LLM => no cost and no prompt-injection surface (an LLM can be added later ONLY as a router
that returns a template id from this same allowlist).
"""

from __future__ import annotations

import re
from dataclasses import dataclass

import duckdb


@dataclass(frozen=True)
class Template:
    sql: str
    sources: tuple[str, ...]
    keywords: tuple[str, ...]
    title: str


TEMPLATES: dict[str, Template] = {
    "retention": Template(
        """select tutorial_completed, round(sum(retained_users) * 1.0 / sum(cohort_users), 4) as retention,
                  sum(cohort_users) as cohort_users
           from gold.mart_retention where day_n = ? group by tutorial_completed order by 1""",
        ("gold.mart_retention",), ("retention", "retain", "tutma", "geri dön"),
        "Retention by tutorial completion"),
    "retention_by_country": Template(
        """select country, round(sum(retained_users) * 1.0 / sum(cohort_users), 4) as retention
           from gold.mart_retention where day_n = ? group by country order by retention desc""",
        ("gold.mart_retention",), ("country", "ülke", "ulke"), "Retention by country"),
    "dau": Template(
        """select activity_date, dau, round(stickiness, 4) as stickiness
           from gold.mart_dau_wau_mau order by activity_date desc limit 14""",
        ("gold.mart_dau_wau_mau",), ("dau", "active user", "aktif"), "Latest 14 days of DAU"),
    "funnel": Template(
        """select sum(app_open_users) as app_open, sum(tutorial_started_users) as tutorial_started,
                  sum(tutorial_completed_users) as tutorial_completed,
                  sum(level_1_completed_users) as level_1_completed, sum(purchase_users) as purchase
           from gold.mart_funnel""",
        ("gold.mart_funnel",), ("funnel", "conversion", "dönüşüm", "donusum"), "Order-aware funnel"),
    "campaign": Template(
        """select campaign_id, round(roas, 3) as roas, round(cpi, 3) as cpi, paying_users
           from gold.mart_campaign_performance order by roas desc""",
        ("gold.mart_campaign_performance",), ("campaign", "roas", "cpi", "kampanya"), "Campaign ROAS / CPI"),
    "data_quality": Template(
        """select check_name, status, detail from gold.dq_results
           where run_ts = (select max(run_ts) from gold.dq_results) order by status, check_name""",
        ("gold.dq_results",), ("quality", "pipeline", "veri kalitesi", "tracking", "bozuk"), "Latest data-quality run"),
}
# Order matters: more specific intents first.
ROUTING_ORDER = ["data_quality", "campaign", "funnel", "retention_by_country", "retention", "dau"]


def route(question: str) -> tuple[str | None, int]:
    q = question.lower()
    m = re.search(r"\bd(1|7|30)\b", q)
    day = int(m.group(1)) if m else 7
    for tid in ROUTING_ORDER:
        if any(k in q for k in TEMPLATES[tid].keywords):
            return tid, day
    return None, day


def answer(con: duckdb.DuckDBPyConnection, question: str) -> dict:
    tid, day = route(question[:300])
    if tid is None:
        return {"supported": False,
                "message": "Unsupported question. Ask about: " + ", ".join(t.title for t in TEMPLATES.values())}
    t = TEMPLATES[tid]
    params = [day] if "?" in t.sql else []
    cur = con.execute(t.sql, params)
    cols = [d[0] for d in cur.description]
    return {"supported": True, "template": tid, "title": t.title, "sql": " ".join(t.sql.split()),
            "params": params, "sources": list(t.sources), "columns": cols, "rows": cur.fetchall()}


if __name__ == "__main__":
    import sys

    c = duckdb.connect("data/gamepulse.duckdb", read_only=True)
    out = answer(c, " ".join(sys.argv[1:]) or "d7 retention")
    print(out.get("message") or {k: out[k] for k in ("title", "sql", "params", "columns", "rows")})
