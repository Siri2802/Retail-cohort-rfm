"""01_ingest.py - Load the raw Excel workbook into DuckDB, unchanged.

Rule: the raw layer is a faithful copy. No cleaning happens here.
"""
from pathlib import Path
import sys
import time

import duckdb
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
RAW_XLSX = ROOT / "data" / "raw" / "online_retail_II.xlsx"
PARQUET = ROOT / "data" / "processed" / "raw_invoices.parquet"
DB = ROOT / "data" / "processed" / "retail.duckdb"

SHEETS = ["Year 2009-2010", "Year 2010-2011"]
EXPECTED_ROWS = 1_067_371  # published by UCI

COLUMN_MAP = {
    "Invoice": "invoice_no",
    "StockCode": "stock_code",
    "Description": "description",
    "Quantity": "quantity",
    "InvoiceDate": "invoice_date",
    "Price": "unit_price",
    "Customer ID": "customer_id",
    "Country": "country",
}


def main() -> int:
    if not RAW_XLSX.exists():
        print(f"ERROR: {RAW_XLSX} not found. Run src/00_download.py first.", file=sys.stderr)
        return 1

    PARQUET.parent.mkdir(parents=True, exist_ok=True)

    frames = []
    for sheet in SHEETS:
        t0 = time.time()
        df = pd.read_excel(RAW_XLSX, sheet_name=sheet, engine="openpyxl")
        df = df.rename(columns=COLUMN_MAP)
        df["source_sheet"] = sheet

        # Excel gives mixed int/str here (85123 vs '85123A'). Force text.
        df["stock_code"] = df["stock_code"].astype(str).str.strip()
        df["invoice_no"] = df["invoice_no"].astype(str).str.strip()

        # Force text, but keep real nulls as None, not the string "nan".
        df["description"] = df["description"].astype("object").where(
            df["description"].notna(), None
        )
        df["description"] = df["description"].map(
            lambda v: None if v is None else str(v).strip()
        )
        df["country"] = df["country"].astype(str).str.strip()

        frames.append(df)
        print(f"  read {sheet:<16} {len(df):>9,} rows in {time.time() - t0:5.1f}s")

    raw = pd.concat(frames, ignore_index=True)
    print(f"  total raw rows: {len(raw):,}")

    raw.to_parquet(PARQUET, index=False)
    print(f"  wrote {PARQUET.relative_to(ROOT)} ({PARQUET.stat().st_size / 1e6:.1f} MB)")

    con = duckdb.connect(str(DB))
    con.execute("DROP TABLE IF EXISTS raw_invoices")
    con.execute(f"CREATE TABLE raw_invoices AS SELECT * FROM read_parquet('{PARQUET}')")
    n = con.execute("SELECT count(*) FROM raw_invoices").fetchone()[0]
    con.close()
    print(f"  loaded {n:,} rows into raw_invoices")

    if n != EXPECTED_ROWS:
        print(f"  FAIL: expected {EXPECTED_ROWS:,} rows, got {n:,}", file=sys.stderr)
        return 1
    print(f"  OK: row count matches UCI published figure ({EXPECTED_ROWS:,})")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())