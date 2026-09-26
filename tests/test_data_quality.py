"""
Data-quality contract tests over the modelled tables.

Run:  python -m pytest tests/ -v
Run src/03_clean.py and src/04_analysis.py first - these tests read the
tables they build in data/processed/retail.duckdb.

These test the DATA, not Python functions. Each one guards against a
specific way this analysis could be silently wrong.
"""
from pathlib import Path

import duckdb
import pytest

ROOT = Path(__file__).resolve().parents[1]
DB = ROOT / "data" / "processed" / "retail.duckdb"

# Real products whose stock codes fail the "starts with 5 digits" pattern
# (found in profiling: Q7 and Gap 2).
PRODUCT_CODE_EXCEPTIONS = (
    "upper(stock_code) LIKE 'DCGS%' "
    "OR upper(stock_code) LIKE 'SP%' "
    "OR upper(stock_code) = 'PADS'"
)


@pytest.fixture(scope="module")
def con():
    c = duckdb.connect(str(DB), read_only=True)
    yield c
    c.close()


def scalar(con, sql):
    return con.execute(sql).fetchone()[0]


# ---------------------------------------------------------------- 1. source

def test_raw_row_count_matches_uci_published_figure(con):
    """If this fails, the source file changed and every number is suspect."""
    assert scalar(con, "SELECT count(*) FROM raw_invoices") == 1_067_371


# ---------------------------------------------------------------- 2. cleaning

def test_exclusion_ledger_reconciles(con):
    """Every removed row is accounted for: flagged - removed = clean."""
    flagged = scalar(con, "SELECT count(*) FROM flagged_transactions")
    removed = scalar(con, """
        SELECT count(*) FROM flagged_transactions
        WHERE is_service_code OR is_writeoff OR is_nonpositive_price
    """)
    clean = scalar(con, "SELECT count(*) FROM clean_transactions")
    assert flagged - removed == clean


def test_no_duplicate_business_keys(con):
    """
    The two sheets overlap 1-9 Dec 2010. Checked at the SAME grain as the
    dedup key (timestamp, not date): products genuinely scanned twice one
    minute apart are not duplicates.
    """
    dupes = scalar(con, """
        SELECT count(*) FROM (
            SELECT invoice_no, stock_code, invoice_ts, quantity, unit_price
            FROM clean_transactions
            GROUP BY ALL HAVING count(*) > 1)
    """)
    assert dupes == 0, f"{dupes} duplicate business keys survived cleaning"


def test_december_2010_overlap_is_not_double_counted(con):
    """Daily revenue in the overlap window must not be ~2x the run-rate."""
    overlap = float(scalar(con, """
        SELECT sum(line_revenue) / 9 FROM clean_transactions
        WHERE invoice_date BETWEEN '2010-12-01' AND '2010-12-09'
    """))
    baseline = float(scalar(con, """
        SELECT sum(line_revenue) / 21 FROM clean_transactions
        WHERE invoice_date BETWEEN '2010-11-10' AND '2010-11-30'
    """))
    assert overlap < baseline * 1.8, (
        f"overlap window GBP{overlap:,.0f}/day vs baseline GBP{baseline:,.0f}/day")


def test_no_unknown_non_product_codes_survive(con):
    """
    Any code that fails the 5-digit pattern must be a KNOWN real product.
    This catches NEW junk codes that are not on the exclusion list yet.
    """
    bad = con.execute(f"""
        SELECT DISTINCT stock_code FROM clean_transactions
        WHERE NOT regexp_matches(stock_code, '^[0-9]{{5}}')
          AND NOT ({PRODUCT_CODE_EXCEPTIONS})
    """).fetchall()
    assert not bad, f"unexpected non-product codes in clean data: {bad}"


def test_no_writeoffs_survive(con):
    bad = scalar(con, """
        SELECT count(*) FROM clean_transactions
        WHERE quantity < 0 AND NOT is_cancellation AND customer_id IS NULL
    """)
    assert bad == 0


def test_all_prices_positive(con):
    assert scalar(con, "SELECT count(*) FROM clean_transactions WHERE unit_price <= 0") == 0


def test_line_revenue_is_decimal_not_float(con):
    """
    With DOUBLE, a fully returned basket nets to ~3.55e-14 instead of 0,
    passes a "> 0" filter, and creates phantom active months.
    """
    t = scalar(con, """
        SELECT data_type FROM information_schema.columns
        WHERE table_name = 'clean_transactions' AND column_name = 'line_revenue'
    """)
    assert "DECIMAL" in t.upper(), f"line_revenue is {t}, must be DECIMAL"


def test_no_float_residue(con):
    """A fully returned month must net to exactly zero, never 1e-14."""
    n = scalar(con, """
        SELECT count(*) FROM (
            SELECT customer_id, invoice_month, sum(line_revenue) AS r
            FROM clean_transactions WHERE customer_id IS NOT NULL
            GROUP BY 1, 2)
        WHERE r <> 0 AND abs(r) < 0.01
    """)
    assert n == 0, f"{n} customer-months have sub-penny residue"


# ---------------------------------------------------------------- 3. cohorts

def test_no_negative_period_numbers(con):
    assert scalar(con, "SELECT count(*) FROM cohort_retention WHERE period_number < 0") == 0


def test_period_zero_is_always_100_percent(con):
    assert scalar(con, """
        SELECT count(*) FROM cohort_retention
        WHERE period_number = 0 AND retention_pct <> 100
    """) == 0


def test_retention_never_exceeds_100(con):
    assert scalar(con, "SELECT count(*) FROM cohort_retention WHERE retention_pct > 100") == 0


def test_zero_activity_periods_are_present_not_missing(con):
    """Missing-zero bug: every cohort must have a row for EVERY period 0..max."""
    gaps = scalar(con, """
        SELECT count(*) FROM (
            SELECT cohort_month, max(period_number) AS mx, count(*) AS n
            FROM cohort_retention GROUP BY cohort_month)
        WHERE n <> mx + 1
    """)
    assert gaps == 0, "cohort x period grid has holes; zeros are missing"


def test_partial_last_month_is_excluded(con):
    """
    Data ends 2011-12-09, so December 2011 is only 9 days. No cohort period
    may fall in a month that is not complete in the data.
    """
    bad = scalar(con, """
        SELECT count(*) FROM cohort_retention
        WHERE last_day(cohort_month + to_months(period_number))
              > (SELECT max(invoice_date) FROM clean_transactions)
    """)
    assert bad == 0, f"{bad} cohort cells fall in an incomplete month"


# ---------------------------------------------------------------- 4. RFM

def test_rfm_scores_in_range(con):
    assert scalar(con, """
        SELECT count(*) FROM rfm
        WHERE r_score NOT BETWEEN 1 AND 5
           OR f_score NOT BETWEEN 1 AND 5
           OR m_score NOT BETWEEN 1 AND 5
    """) == 0


@pytest.mark.parametrize("value_col, score_col", [
    ("recency_days", "r_score"),
    ("frequency", "f_score"),
    ("monetary", "m_score"),
])
def test_rfm_tied_customers_get_the_same_score(con, value_col, score_col):
    """
    NTILE splits identical customers across scores by row order (1,599
    one-time buyers got f_score 1 OR 2). PERCENT_RANK must not.
    """
    bad = scalar(con, f"""
        SELECT count(*) FROM (
            SELECT {value_col} FROM rfm
            GROUP BY {value_col} HAVING count(DISTINCT {score_col}) > 1)
    """)
    assert bad == 0, f"{bad} tied {value_col} values got different {score_col}s"


def test_rfm_frequency_excludes_cancellations(con):
    """A cancellation invoice is not an order."""
    bad = scalar(con, """
        SELECT count(*) FROM rfm r
        JOIN (SELECT customer_id,
                     count(DISTINCT invoice_no) FILTER (WHERE NOT is_cancellation) AS purchases
              FROM clean_transactions WHERE customer_id IS NOT NULL
              GROUP BY customer_id) p USING (customer_id)
        WHERE r.frequency <> p.purchases
    """)
    assert bad == 0


def test_every_customer_appears_once(con):
    assert scalar(con, "SELECT count(*) FROM rfm") == \
           scalar(con, "SELECT count(DISTINCT customer_id) FROM rfm")


def test_rfm_monetary_is_strictly_positive(con):
    assert scalar(con, "SELECT count(*) FROM rfm WHERE monetary <= 0") == 0


# ---------------------------------------------------------------- 5. reconciliation

def test_concentration_deciles_sum_to_100(con):
    total = float(scalar(con, "SELECT sum(pct_of_total_revenue) FROM revenue_concentration"))
    assert abs(total - 100.0) < 0.15, f"deciles sum to {total}, not 100"


def test_rfm_revenue_reconciles_to_clean_table(con):
    rfm_total = scalar(con, "SELECT sum(monetary) FROM rfm")
    clean_total = scalar(con, """
        SELECT sum(r) FROM (
            SELECT customer_id, sum(line_revenue) AS r FROM clean_transactions
            WHERE customer_id IS NOT NULL
            GROUP BY customer_id HAVING sum(line_revenue) > 0)
    """)
    assert abs(float(rfm_total) - float(clean_total)) < 0.01


def test_kpi_customer_count_matches_rfm(con):
    assert scalar(con, "SELECT customers FROM kpis") == scalar(con, "SELECT count(*) FROM rfm")


def test_kpi_returns_reported_as_positive_percentage(con):
    assert scalar(con, "SELECT returns_pct_of_gross FROM kpis") >= 0