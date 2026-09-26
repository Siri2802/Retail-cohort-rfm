-- =====================================================================
-- 05_kpis.sql - headline numbers for the README and dashboard.
--
-- Differences from a naive version:
-- - Orders count PURCHASE invoices only (cancellations are not orders),
--   so avg orders and % one-time buyers are not distorted by returns.
-- - Returns are reported as a POSITIVE % of gross sales.
-- - The share of revenue with no customer ID is reported explicitly.
-- =====================================================================

CREATE OR REPLACE TABLE kpis AS
WITH base AS (
    SELECT * FROM clean_transactions
),
cust AS (
    SELECT customer_id,
           SUM(line_revenue)                                             AS rev,
           COUNT(DISTINCT invoice_no) FILTER (WHERE NOT is_cancellation) AS orders
    FROM base
    WHERE customer_id IS NOT NULL
    GROUP BY customer_id
    HAVING SUM(line_revenue) > 0
)
SELECT
    (SELECT ROUND(SUM(line_revenue), 2) FROM base)                                  AS net_revenue,
    (SELECT ROUND(SUM(line_revenue) FILTER (WHERE NOT is_cancellation), 2) FROM base) AS gross_sales,
    (SELECT ROUND(-SUM(line_revenue) FILTER (WHERE is_cancellation), 2) FROM base)    AS returns_value,
    (SELECT ROUND(100.0 * -SUM(line_revenue) FILTER (WHERE is_cancellation)
                  / SUM(line_revenue) FILTER (WHERE NOT is_cancellation), 2) FROM base) AS returns_pct_of_gross,
    (SELECT COUNT(DISTINCT invoice_no) FILTER (WHERE NOT is_cancellation) FROM base)  AS orders,
    (SELECT COUNT(*) FROM cust)                                                     AS customers,
    (SELECT ROUND(AVG(rev), 2) FROM cust)                                           AS avg_revenue_per_customer,
    (SELECT ROUND(MEDIAN(rev), 2) FROM cust)                                        AS median_revenue_per_customer,
    (SELECT ROUND(AVG(orders), 2) FROM cust)                                        AS avg_orders_per_customer,
    (SELECT ROUND(100.0 * COUNT(*) FILTER (WHERE orders = 1) / COUNT(*), 2) FROM cust) AS pct_one_time_buyers,
    (SELECT ROUND(SUM(line_revenue), 2) FROM base WHERE customer_id IS NULL)        AS unattributed_revenue,
    (SELECT ROUND(100.0 * SUM(line_revenue) FILTER (WHERE customer_id IS NULL)
                  / SUM(line_revenue), 2) FROM base)                                AS pct_unattributed_revenue,
    (SELECT MIN(invoice_date) FROM base)                                            AS first_day,
    (SELECT MAX(invoice_date) FROM base)                                            AS last_day;