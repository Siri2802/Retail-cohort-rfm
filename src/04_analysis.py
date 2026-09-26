"""04_analysis.py - run the analysis SQL files and export result tables.

Grows step by step: cohort retention, RFM, then revenue concentration.
"""
from pathlib import Path

import duckdb

ROOT = Path(__file__).resolve().parents[1]
DB = ROOT / "data" / "processed" / "retail.duckdb"
SQLDIR = ROOT / "sql"
TBL = ROOT / "outputs" / "tables"

STEPS = ["02_cohort_retention.sql", "03_rfm.sql",
         "04_revenue_concentration.sql", "05_kpis.sql"]
EXPORTS = ["cohort_retention", "rfm", "customer_revenue_ranked",
           "revenue_concentration", "kpis"]

# Each check is a query that must return 0 (= number of bad rows).
CHECKS = {
    # --- cohort retention ---
    "cohort: no negative period_number":
        "SELECT count(*) FROM cohort_retention WHERE period_number < 0",
    "cohort: period 0 is always 100%":
        "SELECT count(*) FROM cohort_retention WHERE period_number = 0 AND retention_pct <> 100",
    "cohort: active never exceeds cohort size":
        "SELECT count(*) FROM cohort_retention WHERE active_customers > cohort_size",
    "cohort: grid stops at the last COMPLETE month":
        """SELECT CASE WHEN last_day((SELECT max(cohort_month + to_months(period_number))
                                     FROM cohort_retention))
                         <= (SELECT max(invoice_date) FROM clean_transactions)
                    THEN 0 ELSE 1 END""",
    # --- RFM ---
    "rfm: every customer has a last purchase date":
        "SELECT count(*) FROM rfm WHERE last_purchase IS NULL",
    "rfm: all scores between 1 and 5":
        """SELECT count(*) FROM rfm
           WHERE r_score NOT BETWEEN 1 AND 5
              OR f_score NOT BETWEEN 1 AND 5
              OR m_score NOT BETWEEN 1 AND 5""",
    "rfm: identical frequency always gets the same f_score":
        """SELECT count(*) FROM (SELECT frequency FROM rfm
                                 GROUP BY frequency HAVING count(DISTINCT f_score) > 1)""",
    # --- revenue concentration + KPIs ---
    "concentration: deciles cover every RFM customer":
        """SELECT abs((SELECT sum(customers) FROM revenue_concentration)
                      - (SELECT count(*) FROM rfm))""",
    "concentration: cumulative share ends at 100%":
        """SELECT count(*) FROM revenue_concentration
           WHERE revenue_decile = 10 AND cumulative_pct_of_revenue <> 100""",
    "kpis: customer count matches RFM":
        "SELECT abs(customers - (SELECT count(*) FROM rfm)) FROM kpis",
}


def run_checks(con) -> bool:
    ok = True
    for name, sql in CHECKS.items():
        bad = con.execute(sql).fetchone()[0]
        status = "OK  " if bad == 0 else "FAIL"
        print(f"  {status} {name}" + ("" if bad == 0 else f"  ({bad} bad rows)"))
        ok = ok and bad == 0
    return ok


def main() -> int:
    TBL.mkdir(parents=True, exist_ok=True)
    con = duckdb.connect(str(DB))

    for step in STEPS:
        con.execute((SQLDIR / step).read_text())
        print(f"  ran {step}")

    for t in EXPORTS:
        out = TBL / f"{t}.csv"
        con.execute(f"COPY {t} TO '{out}' (HEADER, DELIMITER ',')")
        n = con.execute(f"SELECT count(*) FROM {t}").fetchone()[0]
        print(f"  exported {t:<24} {n:>6,} rows -> {out.relative_to(ROOT)}")

    print("\n=== Checks ===")
    if not run_checks(con):
        return 1

    print("\n=== Retention curve (all cohorts pooled, months 0-12) ===")
    print(con.execute("""
        SELECT period_number,
               sum(active_customers)::BIGINT                              AS active,
               sum(cohort_size)::BIGINT                                   AS base,
               round(100.0 * sum(active_customers) / sum(cohort_size), 2) AS retention_pct
        FROM cohort_retention
        WHERE period_number <= 12
        GROUP BY period_number
        ORDER BY period_number
    """).df().to_string(index=False))

    print("\n=== RFM segments ===")
    print(con.execute("""
        SELECT segment,
               count(*)                                                     AS customers,
               round(100.0 * count(*) / sum(count(*)) OVER (), 1)           AS pct_customers,
               round(sum(monetary), 0)                                      AS revenue,
               round(100.0 * sum(monetary) / sum(sum(monetary)) OVER (), 1) AS pct_revenue,
               round(avg(recency_days), 0)                                  AS avg_recency_days,
               round(avg(frequency), 1)                                     AS avg_orders
        FROM rfm
        GROUP BY segment
        ORDER BY revenue DESC
    """).df().to_string(index=False))

    print("\n=== Revenue concentration (decile 1 = top 10% of customers) ===")
    print(con.execute("""
        SELECT revenue_decile, customers, decile_revenue,
               pct_of_total_revenue, cumulative_pct_of_revenue
        FROM revenue_concentration
        ORDER BY revenue_decile
    """).df().to_string(index=False))

    print("\n=== KPIs ===")
    kpis = con.execute("SELECT * FROM kpis").df().iloc[0]
    for name, value in kpis.items():
        print(f"  {name:<30} {value}")

    con.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())