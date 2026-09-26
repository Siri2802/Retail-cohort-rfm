-- =====================================================================
-- 02_cohort_retention.sql - monthly acquisition cohorts and retention
--
-- cohort_month  = customer's first NET-POSITIVE month
-- period_number = whole months since cohort_month
-- retained      = net-positive spend that month (returns-only month = not retained)
-- denominator   = cohort size at period 0, held fixed
-- Customers with no customer_id are excluded (cannot be tracked).
-- =====================================================================

CREATE OR REPLACE TABLE cohort_retention AS

WITH bounds AS (
    -- TRAP 3: last COMPLETE month. Data ends 2011-12-09, so Dec 2011 has
    -- only 9 days and would look like a sudden drop for every cohort.
    -- If the last date is not the last day of its month, drop that month.
    SELECT CASE
        WHEN max(invoice_date) = last_day(max(invoice_date))
            THEN date_trunc('month', max(invoice_date))
        ELSE date_trunc('month', max(invoice_date)) - INTERVAL 1 MONTH
    END AS last_month
    FROM clean_transactions
),

customer_months AS (
    -- One row per customer per month where they spent net-positive.
    -- line_revenue is DECIMAL, so "> 0" is exact (TRAP 4).
    SELECT customer_id, invoice_month, SUM(line_revenue) AS month_revenue
    FROM clean_transactions
    WHERE customer_id IS NOT NULL
      AND invoice_month <= (SELECT last_month FROM bounds)
    GROUP BY customer_id, invoice_month
    HAVING SUM(line_revenue) > 0
),

cohorts AS (
    -- Window function: stamp each row with the customer's first month.
    SELECT customer_id, invoice_month, month_revenue,
           MIN(invoice_month) OVER (PARTITION BY customer_id) AS cohort_month
    FROM customer_months
),

indexed AS (
    SELECT cohort_month, customer_id, invoice_month, month_revenue,
           DATE_DIFF('month', cohort_month, invoice_month)::INT AS period_number
    FROM cohorts
),

cohort_sizes AS (
    -- TRAP 2: how many months each cohort can actually be observed for.
    SELECT cohort_month,
           COUNT(DISTINCT customer_id) AS cohort_size,
           DATE_DIFF('month', cohort_month, (SELECT last_month FROM bounds))::INT
               AS max_observable_period
    FROM indexed
    WHERE period_number = 0
    GROUP BY cohort_month
),

grid AS (
    -- TRAP 1: complete cohort x period grid, so zero-activity months get a row.
    SELECT s.cohort_month, s.cohort_size, p.period_number
    FROM cohort_sizes s
    CROSS JOIN LATERAL (
        SELECT UNNEST(range(0, s.max_observable_period + 1)) AS period_number
    ) p
),

activity AS (
    SELECT cohort_month, period_number,
           COUNT(DISTINCT customer_id) AS active_customers,
           SUM(month_revenue)          AS period_revenue
    FROM indexed
    GROUP BY cohort_month, period_number
)

SELECT
    g.cohort_month,
    g.period_number,
    g.cohort_size,
    COALESCE(a.active_customers, 0)                                   AS active_customers,
    ROUND(100.0 * COALESCE(a.active_customers, 0) / g.cohort_size, 2) AS retention_pct,
    COALESCE(a.period_revenue, 0)                                     AS period_revenue,
    ROUND(COALESCE(a.period_revenue, 0) / g.cohort_size, 2)           AS revenue_per_cohort_member,
    -- Window function: cumulative revenue per acquired customer.
    ROUND(SUM(COALESCE(a.period_revenue, 0)) OVER (
              PARTITION BY g.cohort_month
              ORDER BY g.period_number
              ROWS BETWEEN UNBOUNDED PRECEDING AND CURRENT ROW
          ) / g.cohort_size, 2)                                       AS cumulative_revenue_per_member
FROM grid g
LEFT JOIN activity a
       ON a.cohort_month = g.cohort_month
      AND a.period_number = g.period_number
ORDER BY g.cohort_month, g.period_number;