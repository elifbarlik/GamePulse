import pandas as pd

from ingestion.contracts import event_names, validate_event
from ingestion.simulator.generator import BUGGY_VERSION, SimConfig, generate_events


def small():
    return generate_events(SimConfig(n_users=600, seed=7))


def test_deterministic():
    a, _, _ = small()
    b, _, _ = small()
    pd.testing.assert_frame_equal(a, b)


def test_defects_present_and_detectable():
    ev, camp, sc = small()
    assert sc["simulated"] is True
    assert ev["event_id"].duplicated().sum() > 0
    assert (ev["event_timestamp"] > pd.Timestamp("2027-06-01", tz="UTC")).sum() > 0
    assert ev["user_id"].isna().sum() > 0
    assert (~ev["event_name"].isin(event_names())).sum() > 0
    pur = ev[ev["event_name"] == "purchase_completed"]
    assert pur["purchase_amount"].isna().sum() > 0
    assert camp["installs"].sum() > 0 and (camp["spend"] > 0).all()


def test_tracking_bug_scenario():
    ev, _, _ = small()
    v = ev[ev["app_version"] == BUGGY_VERSION]
    assert len(v) > 0 and (v["event_name"] == "level_completed").sum() == 0
    assert (ev[ev["app_version"] != BUGGY_VERSION]["event_name"] == "level_completed").sum() > 0


def test_most_clean_rows_pass_contract():
    ev, _, _ = small()
    sample = ev.sample(500, random_state=1)
    rows = sample.astype(object).where(sample.notna(), None).to_dict("records")
    passed = sum(validate_event({**r, "event_timestamp": r["event_timestamp"].isoformat()})[1] is None
                 for r in rows)
    assert passed / len(rows) > 0.95
