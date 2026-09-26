-- =====================================================================
-- 01_clean.sql : raw_invoices -> flagged_transactions -> clean_transactions
--
-- Every removed row must be counted in the exclusion ledger (03_clean.py).
-- The rules are defined ONCE, here, as flag columns. The ledger counts
-- these flags, so the rules and the ledger can never disagree.
-- =====================================================================

-- Step 1+2: de-duplicate, then flag every row.
CREATE OR REPLACE TABLE flagged_transactions AS
WITH deduped AS (
    -- Business key: invoice + product + timestamp + quantity + price.
    -- NOT in the key:
    --   source_sheet -> so the 1-9 Dec 2010 sheet overlap collapses to one row
    --   description  -> the same product is sometimes renamed over time
    -- Which duplicate survives: the alphabetically first non-null
    -- description. Deterministic, and description is not used in analysis.
    SELECT * EXCLUDE (rn, source_sheet)
    FROM (
        SELECT *,
            ROW_NUMBER() OVER (
                PARTITION BY invoice_no, stock_code, invoice_date, quantity, unit_price
                ORDER BY description NULLS LAST
            ) AS rn
        FROM raw_invoices
    )
    WHERE rn = 1
)
SELECT
    *,
    invoice_no LIKE 'C%'  AS is_cancellation,

    -- Non-product codes: full list from checking ALL 28 non-5-digit codes.
    -- DCGS*, SP*, PADS are real products and are deliberately NOT here.
    (   upper(stock_code) IN (
            'POST', 'DOT', 'C2', 'C3',
            'M', 'ADJUST', 'ADJUST2', 'B',
            'AMAZONFEE', 'BANK CHARGES', 'CRUK',
            'D', 'S',
            'TEST001', 'TEST002',
            'GIFT'
        )
        OR lower(stock_code) LIKE 'gift\_0001\_%' ESCAPE '\'
    )                     AS is_service_code,

    -- Warehouse write-offs: negative qty, not a cancellation, no customer.
    (quantity < 0 AND invoice_no NOT LIKE 'C%' AND customer_id IS NULL)
                          AS is_writeoff,

    unit_price <= 0       AS is_nonpositive_price
FROM deduped;


-- Step 3: keep only rows that pass every rule, with clean types.
CREATE OR REPLACE TABLE clean_transactions AS
SELECT
    invoice_no,
    stock_code,
    description,
    quantity,
    CAST(invoice_date AS TIMESTAMP)                   AS invoice_ts,
    CAST(invoice_date AS DATE)                        AS invoice_date,
    date_trunc('month', CAST(invoice_date AS DATE))   AS invoice_month,
    CAST(unit_price AS DECIMAL(12,3))                 AS unit_price,
    CAST(customer_id AS BIGINT)                       AS customer_id,
    country,
    is_cancellation,
    -- Money as DECIMAL, not DOUBLE: exact arithmetic, so a full return nets to 0.
    CAST(ROUND(quantity * unit_price, 2) AS DECIMAL(18,2)) AS line_revenue
FROM flagged_transactions
WHERE NOT is_service_code
  AND NOT is_writeoff
  AND NOT is_nonpositive_price;