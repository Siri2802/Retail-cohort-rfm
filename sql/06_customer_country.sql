-- =====================================================================
-- 06_customer_country.sql - one country per customer, for dashboard filters.
--
-- A few customers ordered from more than one country. Each customer gets the
-- country they ordered from MOST often (ties broken alphabetically, so the
-- result is identical on every run).
-- =====================================================================

CREATE OR REPLACE TABLE customer_country AS
SELECT customer_id, country
FROM (
    SELECT customer_id,
           country,
           ROW_NUMBER() OVER (PARTITION BY customer_id
                              ORDER BY count(*) DESC, country) AS rn
    FROM clean_transactions
    WHERE customer_id IS NOT NULL
    GROUP BY customer_id, country
)
WHERE rn = 1
ORDER BY customer_id;
