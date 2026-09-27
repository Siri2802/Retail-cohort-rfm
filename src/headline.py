"""headline.py - every number quoted in the figures, Excel file and dashboard.

Nothing is typed in by hand. If the data or a cleaning rule changes, every
caption and finding changes with it. (The answer key hard-coded numbers
like "22.8%" into its captions, so they silently went stale.)
"""

# First month of data: its "new" customers include long-standing ones
# (left-censored), so it is excluded from every retention benchmark.
CENSORED_COHORT = "2009-12-01"


def headline(con) -> dict:
    def one(sql):
        return con.execute(sql).fetchone()

    h = {"kpis": con.execute("SELECT * FROM kpis").df().iloc[0]}

    h["raw_rows"], h["clean_rows"] = one("""
        SELECT (SELECT count(*) FROM raw_invoices),
               (SELECT count(*) FROM clean_transactions)""")

    # Revenue concentration
    h["top10_pct"], h["top20_pct"], h["top50_pct"] = one("""
        SELECT max(cumulative_pct_of_revenue) FILTER (WHERE revenue_decile = 1),
               max(cumulative_pct_of_revenue) FILTER (WHERE revenue_decile = 2),
               max(cumulative_pct_of_revenue) FILTER (WHERE revenue_decile = 5)
        FROM revenue_concentration""")
    h["bottom50_pct"] = 100 - h["top50_pct"]
    h["top_customer_pct"] = one(
        "SELECT 100.0 * max(revenue) / sum(revenue) FROM customer_revenue_ranked")[0]

    # Retention benchmark (Dec 2009 excluded)
    h["m1"], h["m10"], h["m12"] = one(f"""
        SELECT
          100.0 * sum(active_customers) FILTER (WHERE period_number = 1)
                / sum(cohort_size)      FILTER (WHERE period_number = 1),
          100.0 * sum(active_customers) FILTER (WHERE period_number = 10)
                / sum(cohort_size)      FILTER (WHERE period_number = 10),
          100.0 * sum(active_customers) FILTER (WHERE period_number = 12)
                / sum(cohort_size)      FILTER (WHERE period_number = 12)
        FROM cohort_retention
        WHERE cohort_month > '{CENSORED_COHORT}'""")
    h["censored_avg"], h["later_avg"] = one(f"""
        SELECT
          100.0 * sum(active_customers) FILTER (WHERE cohort_month = '{CENSORED_COHORT}')
                / sum(cohort_size)      FILTER (WHERE cohort_month = '{CENSORED_COHORT}'),
          100.0 * sum(active_customers) FILTER (WHERE cohort_month > '{CENSORED_COHORT}')
                / sum(cohort_size)      FILTER (WHERE cohort_month > '{CENSORED_COHORT}')
        FROM cohort_retention
        WHERE period_number BETWEEN 1 AND 12""")

    # RFM
    h["champ_cust_pct"], h["champ_rev_pct"] = one("""
        SELECT 100.0 * count(*) FILTER (WHERE segment = 'Champions') / count(*),
               100.0 * sum(monetary) FILTER (WHERE segment = 'Champions') / sum(monetary)
        FROM rfm""")
    (h["arhv_customers"], h["arhv_revenue"],
     h["arhv_orders"], h["arhv_recency"]) = one("""
        SELECT count(*), sum(monetary), avg(frequency), avg(recency_days)
        FROM rfm WHERE segment = 'At Risk - High Value'""")
    h["one_time_rev_pct"] = one("""
        SELECT 100.0 * sum(monetary) FILTER (WHERE frequency = 1) / sum(monetary)
        FROM rfm""")[0]
    return h
