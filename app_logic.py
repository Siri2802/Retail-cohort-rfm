"""app_logic.py - calculations behind the interactive dashboard (app.py).

Pure pandas, no Streamlit, so it can be tested (tests/test_dashboard.py).
It reads the CSVs the pipeline exports to outputs/tables/ and uses the SAME
definitions as the SQL:
- retention: net-positive months only, complete cohort x period grid with
  zeros filled in, capped at each cohort's last observable month
- concentration: customers ranked by revenue (ties by customer_id), split
  into ten groups exactly like SQL NTILE(10)
With no filters applied, every number here must equal the pipeline's.
"""
from pathlib import Path

import numpy as np
import pandas as pd

TABLES = Path(__file__).resolve().parent / "outputs" / "tables"
CENSORED_COHORT = pd.Timestamp("2009-12-01")   # first month of data (left-censored)

# RFM segments folded into 3 colour groups for the scatter plot
# (more than 3 colours on a scatter cannot all be told apart).
SEGMENT_GROUP = {
    "Champions": "Core (Champions, Loyal)",
    "Loyal": "Core (Champions, Loyal)",
    "At Risk - High Value": "At risk",
    "At Risk": "At risk",
    "Cannot Lose Them": "At risk",
    "Needs Attention": "At risk",
    "New / Promising": "New, hibernating or lost",
    "Hibernating": "New, hibernating or lost",
    "Lost": "New, hibernating or lost",
}


def load(tables: Path = TABLES) -> dict:
    rfm = pd.read_csv(tables / "rfm.csv", parse_dates=["first_purchase", "last_purchase"])
    country = pd.read_csv(tables / "customer_country.csv")
    rfm = rfm.merge(country, on="customer_id", how="left")
    return {
        "rfm": rfm,
        "activity": pd.read_csv(tables / "cohort_activity.csv",
                                parse_dates=["cohort_month", "invoice_month",
                                             "last_complete_month"]),
        "cohort_retention": pd.read_csv(tables / "cohort_retention.csv",
                                        parse_dates=["cohort_month"]),
        "kpis": pd.read_csv(tables / "kpis.csv").iloc[0],
        "ledger": pd.read_csv(tables / "exclusion_ledger.csv").iloc[0],
    }


def filter_customers(rfm: pd.DataFrame, country: str, segments: list) -> pd.DataFrame:
    """country: 'All countries', 'United Kingdom only', 'Outside the UK', or a country name."""
    out = rfm[rfm["segment"].isin(segments)]
    if country == "United Kingdom only":
        out = out[out["country"] == "United Kingdom"]
    elif country == "Outside the UK":
        out = out[out["country"] != "United Kingdom"]
    elif country != "All countries":
        out = out[out["country"] == country]
    return out


def retention_grid(activity: pd.DataFrame, customer_ids=None,
                   exclude_censored: bool = False,
                   cohort_from=None, cohort_to=None) -> pd.DataFrame:
    """Cohort x period grid for the chosen customers (same logic as the SQL)."""
    act = activity
    if customer_ids is not None:
        act = act[act["customer_id"].isin(set(customer_ids))]
    if exclude_censored:
        act = act[act["cohort_month"] != CENSORED_COHORT]
    if cohort_from is not None:
        act = act[act["cohort_month"] >= pd.Timestamp(cohort_from)]
    if cohort_to is not None:
        act = act[act["cohort_month"] <= pd.Timestamp(cohort_to)]
    cols = ["cohort_month", "period_number", "cohort_size",
            "active_customers", "retention_pct"]
    if act.empty:
        return pd.DataFrame(columns=cols)

    last = activity["last_complete_month"].iloc[0]
    sizes = (act[act["period_number"] == 0]
             .groupby("cohort_month")["customer_id"].nunique()
             .rename("cohort_size").reset_index())
    # Trap 1 + 2: every period from 0 to the last observable one, zeros kept.
    rows = []
    for c, n in zip(sizes["cohort_month"], sizes["cohort_size"]):
        max_p = (last.year - c.year) * 12 + (last.month - c.month)
        rows += [(c, p, n) for p in range(max_p + 1)]
    grid = pd.DataFrame(rows, columns=["cohort_month", "period_number", "cohort_size"])
    active = (act.groupby(["cohort_month", "period_number"])["customer_id"].nunique()
              .rename("active_customers").reset_index())
    grid = grid.merge(active, on=["cohort_month", "period_number"], how="left")
    grid["active_customers"] = grid["active_customers"].fillna(0).astype(int)
    grid["retention_pct"] = (100.0 * grid["active_customers"] / grid["cohort_size"]).round(2)
    return grid[cols].sort_values(["cohort_month", "period_number"]).reset_index(drop=True)


def pooled_curve(grid: pd.DataFrame, max_period: int = 12) -> pd.DataFrame:
    g = grid[grid["period_number"] <= max_period]
    out = (g.groupby("period_number")[["active_customers", "cohort_size"]].sum()
           .reset_index().rename(columns={"cohort_size": "base"}))
    out["retention_pct"] = 100.0 * out["active_customers"] / out["base"]
    return out


def deciles(rfm_subset: pd.DataFrame) -> pd.DataFrame:
    """Top-to-bottom revenue deciles, split exactly like SQL NTILE(10)."""
    d = (rfm_subset.sort_values(["monetary", "customer_id"], ascending=[False, True])
         .reset_index(drop=True))
    n = len(d)
    if n == 0:
        return pd.DataFrame(columns=["revenue_decile", "customers", "decile_revenue",
                                     "pct_of_total_revenue", "cumulative_pct_of_revenue"])
    groups = min(10, n)
    base, extra = divmod(n, groups)
    sizes = [base + (1 if i < extra else 0) for i in range(groups)]
    d["revenue_decile"] = np.repeat(np.arange(1, groups + 1), sizes)
    total = d["monetary"].sum()
    out = (d.groupby("revenue_decile")
           .agg(customers=("customer_id", "size"), decile_revenue=("monetary", "sum"))
           .reset_index())
    out["pct_of_total_revenue"] = (100.0 * out["decile_revenue"] / total).round(2)
    out["cumulative_pct_of_revenue"] = (100.0 * out["decile_revenue"].cumsum() / total).round(2)
    return out


def lorenz(rfm_subset: pd.DataFrame) -> pd.DataFrame:
    d = rfm_subset.sort_values(["monetary", "customer_id"], ascending=[False, True])
    n = len(d)
    return pd.DataFrame({
        "pct_of_customers": 100.0 * np.arange(1, n + 1) / n,
        "cumulative_pct_revenue": 100.0 * d["monetary"].cumsum().to_numpy() / d["monetary"].sum(),
    })


def share_at(curve: pd.DataFrame, pct: float) -> float:
    return float(np.interp(pct, curve["pct_of_customers"], curve["cumulative_pct_revenue"]))


def summary(rfm_subset: pd.DataFrame, rfm_all: pd.DataFrame) -> dict:
    return {
        "customers": len(rfm_subset),
        "revenue": float(rfm_subset["monetary"].sum()),
        "revenue_share": 100.0 * rfm_subset["monetary"].sum() / rfm_all["monetary"].sum(),
        "median_value": float(rfm_subset["monetary"].median()),
        "avg_orders": float(rfm_subset["frequency"].mean()),
        "one_time_pct": 100.0 * (rfm_subset["frequency"] == 1).mean(),
    }
