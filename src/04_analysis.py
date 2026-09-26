"""04_analysis.py - run the analysis SQL files and export result tables.

Grows step by step: cohort retention now, RFM and concentration later.
"""
from pathlib import Path

import duckdb

ROOT = Path(__file__).resolve().parents[1]
DB = ROOT / "data" / "processed" / "retail.duckdb"
SQLDIR = ROOT / "sql"
TBL = ROOT / "outputs" / "tables"

STEPS = ["02_cohort_retention.sql"]
EXPORTS = ["cohort_retention"]


def check_cohorts(con) -> bool:
    """Sanity checks that catch the classic cohort bugs."""
    checks = {
        "no negative period_number":
            "SELECT count(*) FROM cohort_retention WHERE period_number < 0",
        "period 0 is always 100%":
            "SELECT count(*) FROM cohort_retention WHERE period_number = 0 AND retention_pct <> 100",
        "active never exceeds cohort size":
            "SELECT count(*) FROM cohort_retention WHERE active_customers > cohort_size",
        "grid stops at the last COMPLETE month":
            """SELECT CASE WHEN last_day((SELECT max(cohort_month + to_months(period_number))
                                         FROM cohort_retention))
                             <= (SELECT max(invoice_date) FROM clean_transactions)
                        THEN 0 ELSE 1 END""",
    }
    ok = True
    for name, sql in checks.items():
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
        print(f"  exported {t:<20} {n:>6,} rows -> {out.relative_to(ROOT)}")

    print("\n=== Cohort checks ===")
    if not check_cohorts(con):
        return 1

    print("\n=== Retention curve (all cohorts pooled, months 0-12) ===")
    print(con.execute("""
        SELECT period_number,
               sum(active_customers)::BIGINT                           AS active,
               sum(cohort_size)::BIGINT                                AS base,
               round(100.0 * sum(active_customers) / sum(cohort_size), 2) AS retention_pct
        FROM cohort_retention
        WHERE period_number <= 12
        GROUP BY period_number
        ORDER BY period_number
    """).df().to_string(index=False))

    con.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
