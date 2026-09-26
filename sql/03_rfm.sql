-- =====================================================================
-- 03_rfm.sql - RFM segmentation (Recency, Frequency, Monetary)
--
-- Snapshot date = day AFTER the last transaction (so the most recent
-- customers have recency 1, not 0).
-- Only customers with net-positive lifetime revenue are scored.
--
-- Three deliberate differences from a naive RFM:
-- 1. Frequency counts PURCHASE invoices only. A cancellation invoice is
--    not an order.
-- 2. Recency uses the last PURCHASE date. A customer whose last activity
--    was a return has not "bought recently".
-- 3. Scores use PERCENT_RANK, not NTILE. NTILE splits by row count, so
--    customers with IDENTICAL values (e.g. the ~24% who ordered once) get
--    split across different scores arbitrarily. PERCENT_RANK gives ties
--    the same score. Trade-off: the 5 groups are no longer equal-sized.
--
-- Scores: 5 is always best. Recency is ordered DESC so fewer days = 5.
-- =====================================================================

CREATE OR REPLACE TABLE rfm AS

WITH snapshot AS (
    SELECT MAX(invoice_date) + INTERVAL 1 DAY AS snapshot_date
    FROM clean_transactions
),

customer_base AS (
    SELECT
        customer_id,
        MIN(invoice_date)                                             AS first_purchase,
        MAX(invoice_date) FILTER (WHERE NOT is_cancellation)          AS last_purchase,
        COUNT(DISTINCT invoice_no) FILTER (WHERE NOT is_cancellation) AS frequency,
        COUNT(DISTINCT invoice_no) FILTER (WHERE is_cancellation)     AS cancelled_orders,
        ROUND(SUM(line_revenue), 2)                                   AS monetary
    FROM clean_transactions
    WHERE customer_id IS NOT NULL
    GROUP BY customer_id
    HAVING SUM(line_revenue) > 0
),

with_recency AS (
    SELECT b.*,
           DATE_DIFF('day', b.last_purchase, s.snapshot_date)::INT AS recency_days
    FROM customer_base b CROSS JOIN snapshot s
),

scored AS (
    SELECT
        *,
        LEAST(5, 1 + FLOOR(5 * PERCENT_RANK() OVER (ORDER BY recency_days DESC)))::INT AS r_score,
        LEAST(5, 1 + FLOOR(5 * PERCENT_RANK() OVER (ORDER BY frequency    ASC )))::INT AS f_score,
        LEAST(5, 1 + FLOOR(5 * PERCENT_RANK() OVER (ORDER BY monetary     ASC )))::INT AS m_score
    FROM with_recency
)

SELECT
    *,
    CONCAT(r_score, f_score, m_score)  AS rfm_cell,
    r_score + f_score + m_score        AS rfm_total,
    CASE
        WHEN r_score >= 4 AND f_score >= 4 AND m_score >= 4 THEN 'Champions'
        WHEN r_score >= 3 AND f_score >= 4                  THEN 'Loyal'
        WHEN r_score >= 4 AND f_score <= 2                  THEN 'New / Promising'
        WHEN r_score = 3  AND f_score = 3                   THEN 'Needs Attention'
        WHEN r_score <= 2 AND f_score >= 4 AND m_score >= 4 THEN 'At Risk - High Value'
        WHEN r_score <= 2 AND f_score >= 3                  THEN 'At Risk'
        WHEN r_score <= 2 AND m_score >= 4                  THEN 'Cannot Lose Them'
        WHEN r_score = 1  AND f_score <= 2                  THEN 'Lost'
        ELSE 'Hibernating'
    END                                AS segment
FROM scored
ORDER BY monetary DESC;