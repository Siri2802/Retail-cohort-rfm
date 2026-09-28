"""
The interactive dashboard must agree with the pipeline.

app_logic.py recalculates retention and concentration so the dashboard can
filter. With NO filters, its numbers must equal the SQL tables exactly -
otherwise the project would have two sources of truth.
Run after src/04_analysis.py (reads outputs/tables/).
"""
import pytest

import app_logic


@pytest.fixture(scope="module")
def data():
    return app_logic.load()


def test_unfiltered_retention_grid_equals_pipeline(data):
    mine = app_logic.retention_grid(data["activity"])
    pipe = data["cohort_retention"]
    assert len(mine) == len(pipe)
    for col in ["period_number", "cohort_size", "active_customers"]:
        assert (mine[col].to_numpy() == pipe[col].to_numpy()).all(), f"{col} differs"
    assert (mine["retention_pct"] - pipe["retention_pct"]).abs().max() < 0.005


def test_unfiltered_deciles_equal_pipeline(data):
    import pandas as pd
    mine = app_logic.deciles(data["rfm"])
    pipe = pd.read_csv(app_logic.TABLES / "revenue_concentration.csv")
    assert (mine["customers"].to_numpy() == pipe["customers"].to_numpy()).all()
    assert (mine["pct_of_total_revenue"] - pipe["pct_of_total_revenue"]).abs().max() < 0.005


def test_unfiltered_summary_equals_kpis(data):
    s = app_logic.summary(data["rfm"], data["rfm"])
    k = data["kpis"]
    assert s["customers"] == k["customers"]
    assert abs(s["median_value"] - k["median_revenue_per_customer"]) < 0.01
    assert abs(s["one_time_pct"] - k["pct_one_time_buyers"]) < 0.01


def test_filters_only_narrow_never_add_customers(data):
    uk = app_logic.filter_customers(data["rfm"], "United Kingdom only",
                                    list(app_logic.SEGMENT_GROUP))
    rest = app_logic.filter_customers(data["rfm"], "Outside the UK",
                                      list(app_logic.SEGMENT_GROUP))
    assert len(uk) + len(rest) == len(data["rfm"])


def test_every_segment_has_a_colour_group(data):
    assert set(data["rfm"]["segment"]) <= set(app_logic.SEGMENT_GROUP)
