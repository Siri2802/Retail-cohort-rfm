"""02_profile.py - profile the RAW data and write docs/profile_raw.md.

Every finding that drives a cleaning rule in sql/01_clean.sql is produced
here, so anyone can reproduce the evidence. Runs on raw_invoices only -
no cleaning applied. Interpretation lives in docs/profile_notes.md.
"""
from pathlib import Path

import duckdb

ROOT = Path(__file__).resolve().parents[1]
DB = ROOT / "data" / "processed" / "retail.duckdb"
OUT = ROOT / "docs" / "profile_raw.md"

# (section title, SQL). Every query has a full ORDER BY so the output is
# identical on every run. min(description) is used instead of any_value(),
# which returns an arbitrary row and can change between runs.
QUERIES = [
    ("Q1 Shape and date range", """
        SELECT count(*)                    AS rows,
               count(DISTINCT invoice_no)  AS invoices,
               count(DISTINCT customer_id) AS customers,
               count(DISTINCT stock_code)  AS stock_codes,
               count(DISTINCT country)     AS countries,
               min(invoice_date)           AS first_date,
               max(invoice_date)           AS last_date
        FROM raw_invoices"""),

    ("Q2 Missing values", """
        SELECT count(*) - count(customer_id)                                AS null_customer,
               round(100.0 * (count(*) - count(customer_id)) / count(*), 2) AS pct_null_customer,
               count(*) - count(description)                                AS null_description,
               round(100.0 * (count(*) - count(description)) / count(*), 2) AS pct_null_description
        FROM raw_invoices"""),

    ("Q3 Negative quantity", """
        SELECT sum(CASE WHEN quantity < 0 THEN 1 ELSE 0 END)                              AS negative_rows,
               round(100.0 * sum(CASE WHEN quantity < 0 THEN 1 ELSE 0 END) / count(*), 2) AS pct
        FROM raw_invoices"""),

    ("Q4 Cancellation invoices (C prefix)", """
        SELECT count(*) AS rows, count(DISTINCT invoice_no) AS invoices
        FROM raw_invoices
        WHERE invoice_no LIKE 'C%'"""),

    ("Q5a C-invoice vs negative quantity", """
        SELECT invoice_no LIKE 'C%' AS is_cancellation,
               quantity < 0         AS is_negative_qty,
               count(*)             AS rows
        FROM raw_invoices
        GROUP BY 1, 2
        ORDER BY 1, 2"""),

    ("Q5b Negative quantity but NOT a C-invoice: all write-offs?", """
        SELECT count(*)                                             AS rows,
               sum(CASE WHEN unit_price = 0 THEN 1 ELSE 0 END)      AS price_zero,
               sum(CASE WHEN customer_id IS NULL THEN 1 ELSE 0 END) AS no_customer
        FROM raw_invoices
        WHERE invoice_no NOT LIKE 'C%' AND quantity < 0"""),

    ("Q5c C-invoice with positive quantity", """
        SELECT invoice_no, stock_code, description, quantity, unit_price, customer_id
        FROM raw_invoices
        WHERE invoice_no LIKE 'C%' AND quantity >= 0
        ORDER BY invoice_no"""),

    ("Q6a Price classes", """
        SELECT CASE WHEN unit_price > 0 THEN 'positive'
                    WHEN unit_price = 0 THEN 'zero'
                    ELSE 'negative' END AS price_class,
               count(*)                 AS rows,
               min(unit_price)          AS min_price,
               max(unit_price)          AS max_price
        FROM raw_invoices
        GROUP BY 1
        ORDER BY rows DESC"""),

    ("Q6b Zero-price rows: who are they?", """
        SELECT customer_id IS NULL AS no_customer,
               quantity < 0        AS is_negative_qty,
               count(*)            AS rows
        FROM raw_invoices
        WHERE unit_price = 0
        GROUP BY 1, 2
        ORDER BY 1, 2"""),

    ("Q6c Bad-debt adjustments (stock code B), in time order", """
        SELECT invoice_no, invoice_date, unit_price, customer_id
        FROM raw_invoices
        WHERE stock_code = 'B'
        ORDER BY invoice_date, invoice_no"""),

    ("Q7a ALL stock codes that do not start with 5 digits (excluding DCGS*)", """
        SELECT stock_code,
               min(description)                     AS example_description,
               count(*)                             AS rows,
               round(sum(quantity * unit_price), 2) AS total_value
        FROM raw_invoices
        WHERE NOT regexp_matches(stock_code, '^[0-9]{5}')
          AND upper(stock_code) NOT LIKE 'DCGS%'
        GROUP BY stock_code
        ORDER BY rows DESC, stock_code"""),

    ("Q7b DCGS codes (real products that fail the 5-digit rule)", """
        SELECT stock_code, min(description) AS example_description, count(*) AS rows
        FROM raw_invoices
        WHERE upper(stock_code) LIKE 'DCGS%'
        GROUP BY stock_code
        ORDER BY rows DESC, stock_code"""),

    ("Q7c Ten highest unit prices", """
        SELECT invoice_no, stock_code, description, quantity, unit_price, customer_id
        FROM raw_invoices
        ORDER BY unit_price DESC, invoice_no
        LIMIT 10"""),

    ("Rows per country (top 12)", """
        SELECT country,
               count(*)                                      AS rows,
               count(DISTINCT customer_id)                   AS customers,
               round(count(*) / count(DISTINCT customer_id)) AS rows_per_customer
        FROM raw_invoices
        GROUP BY country
        ORDER BY rows DESC, country
        LIMIT 12"""),

    ("Q8a Date range of each sheet", """
        SELECT source_sheet, min(invoice_date) AS first_date,
               max(invoice_date) AS last_date, count(*) AS rows
        FROM raw_invoices
        GROUP BY source_sheet
        ORDER BY source_sheet"""),

    ("Q8b Invoices that appear in BOTH sheets", """
        SELECT count(*) AS invoices_in_both_sheets
        FROM (SELECT invoice_no FROM raw_invoices
              GROUP BY invoice_no
              HAVING count(DISTINCT source_sheet) = 2)"""),

    ("Q8c Duplicate rows on the business key", """
        WITH total AS (
            SELECT count(*) AS n FROM raw_invoices),
        uniq AS (
            SELECT count(*) AS n FROM (
                SELECT DISTINCT invoice_no, stock_code, invoice_date, quantity, unit_price
                FROM raw_invoices)),
        within_sheet AS (
            SELECT coalesce(sum(n - 1), 0) AS n FROM (
                SELECT count(*) AS n FROM raw_invoices
                GROUP BY invoice_no, stock_code, invoice_date, quantity, unit_price, source_sheet
                HAVING count(*) > 1))
        SELECT total.n - uniq.n                   AS duplicate_rows_total,
               within_sheet.n                     AS within_same_sheet,
               total.n - uniq.n - within_sheet.n  AS from_sheet_overlap
        FROM total, uniq, within_sheet"""),
]


def to_markdown(cols, rows) -> str:
    """Render a result as a Markdown table (no extra dependency needed)."""
    def fmt(v):
        return "" if v is None else str(v)
    lines = ["| " + " | ".join(cols) + " |",
             "|" + "|".join("---" for _ in cols) + "|"]
    lines += ["| " + " | ".join(fmt(v) for v in row) + " |" for row in rows]
    return "\n".join(lines)


def main() -> int:
    con = duckdb.connect(str(DB), read_only=True)
    parts = ["# Raw data profile",
             "",
             "Generated by `src/02_profile.py` from `raw_invoices` (no cleaning applied).",
             "Interpretation of every finding: `docs/profile_notes.md`.",
             ""]
    for title, sql in QUERIES:
        cur = con.execute(sql)
        cols = [d[0] for d in cur.description]
        rows = cur.fetchall()
        parts += [f"## {title}", "", to_markdown(cols, rows), ""]
        print(f"  {title:<72} {len(rows):>3} rows")
    con.close()

    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text("\n".join(parts))
    print(f"\n  wrote {OUT.relative_to(ROOT)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())