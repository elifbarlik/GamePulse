import duckdb
import pytest

from analytics.assistant.assistant import TEMPLATES, answer, route


@pytest.fixture()
def con():
    c = duckdb.connect(":memory:")
    c.execute("create schema gold")
    c.execute("""create table gold.mart_retention as select * from (values
        (date '2026-09-01','TR','Android',true,7,10,5,0.5),
        (date '2026-09-01','TR','Android',false,7,10,2,0.2),
        (date '2026-09-01','DE','iOS',true,1,10,8,0.8))
        t(cohort_date,country,platform,tutorial_completed,day_n,cohort_users,retained_users,retention)""")
    return c


def test_routing_and_day_parameter():
    assert route("D7 retention neden düştü?") == ("retention", 7)
    assert route("what is d30 retention by country") == ("retention_by_country", 30)
    assert route("kampanya roas")[0] == "campaign"
    assert route("is tracking broken after the release?")[0] == "data_quality"
    assert route("tell me a joke")[0] is None


def test_answer_returns_verifiable_sql_and_rows(con):
    out = answer(con, "d7 retention")
    assert out["supported"] and out["params"] == [7] and "gold.mart_retention" in out["sources"]
    assert dict((r[0], r[1]) for r in out["rows"]) == {False: 0.2, True: 0.5}
    assert out["sql"].startswith("select")


def test_unsupported_question_runs_no_sql(con):
    out = answer(con, "drop everything; --")
    assert out["supported"] is False
    assert con.execute("select count(*) from gold.mart_retention").fetchone()[0] == 3


def test_injection_text_is_never_interpolated(con):
    out = answer(con, "d7 retention'; drop table gold.mart_retention; --")
    assert out["supported"] and con.execute("select count(*) from gold.mart_retention").fetchone()[0] == 3


def test_templates_are_static_read_only_selects():
    for t in TEMPLATES.values():
        s = " ".join(t.sql.lower().split())
        assert s.startswith("select") and ";" not in s
        assert not any(w in s for w in ("insert ", "update ", "delete ", "drop ", "create "))
