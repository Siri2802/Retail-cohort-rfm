-- =====================================================================
-- 04_revenue_concentration.sql - how concentrated is revenue?
-- Answers: "if we lost our top 10% of customers, what would we lose?"
--
-- Scope: customer-attributed revenue only (customers with an ID and
-- net-positive lifetime revenue - the same 5,832 customers as RFM).
-- Revenue with no customer ID cannot be ranked by customer; its share is
-- reported separately in the KPIs so the gap stays visible.
-- =====================================================================

CREATE OR REPLACE TABLE customer_revenue_ranked AS
WITH customer_revenue AS (
    SELECT customer_id, ROUND(SUM(line_revenue), 2) AS revenue
    FROM clean_transactions
    WHERE customer_id IS NOT NULL
    GROUP BY customer_id
    HAVING SUM(line_revenue) > 0
)
SELECT
    customer_id,
    revenue,
    ROW_NUMBER() OVER (ORDER BY revenue DESC, customer_id)            AS revenue_rank,
    NTILE(10)    OVER (ORDER BY revenue DESC, customer_id)            AS revenue_decile,
    ROUND(100.0 * ROW_NUMBER() OVER (ORDER BY revenue DESC, customer_id)
          / COUNT(*) OVER (), 4)                                      AS pct_of_customers,
    ROUND(100.0 * SUM(revenue) OVER (ORDER BY revenue DESC, customer_id
                                     ROWS BETWEEN UNBOUNDED PRECEDING AND CURRENT ROW)
          / SUM(revenue) OVER (), 4)                                  AS cumulative_pct_revenue
FROM customer_revenue
ORDER BY revenue_rank;

-- Decile summary (decile 1 = top 10% of customers by revenue).
CREATE OR REPLACE TABLE revenue_concentration AS
SELECT
    revenue_decile,
    COUNT(*)                                                         AS customers,
    ROUND(SUM(revenue), 2)                                           AS decile_revenue,
    ROUND(100.0 * SUM(revenue) / (SELECT SUM(revenue) FROM customer_revenue_ranked), 2)
                                                                     AS pct_of_total_revenue,
    ROUND(MAX(cumulative_pct_revenue), 2)                            AS cumulative_pct_of_revenue,
    ROUND(AVG(revenue), 2)                                           AS avg_revenue_per_customer,
    MIN(revenue)                                                     AS min_revenue,
    MAX(revenue)                                                     AS max_revenue
FROM customer_revenue_ranked
GROUP BY revenue_decile
ORDER BY revenue_decile;