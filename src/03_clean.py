"""03_clean.py - run sql/01_clean.sql and print a reconciling exclusion ledger.

The ledger is the deliverable: it shows exactly how the raw rows became the
clean rows, with every deduction named. If it does not add up, the script fails.
"""
from pathlib import Path
import sys

import duckdb

ROOT = Path(__file__).resolve().parents[1]
DB = ROOT / "data" / "processed" / "retail.duckdb"
SQL = ROOT / "sql" / "01_clean.sql"
OUT = ROOT / "outputs" / "tables" / "exclusion_ledger.csv"

# Counts come from the flag columns the SQL created - rules are not repeated here.
# Waterfall order: each row is counted under the FIRST rule that removes it.
LEDGER_SQL = """
SELECT
    (SELECT count(*) FROM raw_invoices)                                    AS raw_rows,
    (SELECT count(*) FROM raw_invoices) - count(*)                         AS removed_duplicates,
    count(*) FILTER (WHERE is_service_code)                                AS removed_service_codes,
    count(*) FILTER (WHERE NOT is_service_code AND is_writeoff)            AS removed_writeoffs,
    count(*) FILTER (WHERE NOT is_service_code AND NOT is_writeoff
                       AND is_nonpositive_price)                           AS removed_nonpositive_price,
    (SELECT count(*) FROM clean_transactions)                              AS clean_rows
FROM flagged_transactions
"""


def main() -> int:
    con = duckdb.connect(str(DB))
    con.execute(SQL.read_text())

    cur = con.execute(LEDGER_SQL)
    cols = [d[0] for d in cur.description]
    led = dict(zip(cols, cur.fetchone()))

    rows = [
        ("Raw rows loaded",                  led["raw_rows"]),
        ("- Duplicate rows (business key)",  -led["removed_duplicates"]),
        ("- Non-product / service codes",    -led["removed_service_codes"]),
        ("- Warehouse write-offs",           -led["removed_writeoffs"]),
        ("- Zero or negative price",         -led["removed_nonpositive_price"]),
        ("= Clean rows",                     led["clean_rows"]),
    ]
    print("\n=== EXCLUSION LEDGER ===")
    for name, val in rows:
        print(f"  {name:<34} {val:>12,}")

    expected = (led["raw_rows"] - led["removed_duplicates"] - led["removed_service_codes"]
                - led["removed_writeoffs"] - led["removed_nonpositive_price"])
    if expected != led["clean_rows"]:
        print(f"\n  FAIL: ledger does not reconcile ({expected:,} != {led['clean_rows']:,})",
              file=sys.stderr)
        return 1

    pct = 100.0 * led["clean_rows"] / led["raw_rows"]
    print(f"\n  OK: ledger reconciles exactly. {pct:.2f}% of raw rows kept.")

    OUT.parent.mkdir(parents=True, exist_ok=True)
    con.execute(f"COPY ({LEDGER_SQL}) TO '{OUT}' (HEADER, DELIMITER ',')")
    print(f"  wrote {OUT.relative_to(ROOT)}")
    con.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())