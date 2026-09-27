"""06_excel.py - the Excel deliverable (outputs/online_retail_customer_analysis.xlsx).

Adapted from the answer key. Changes: every finding on the Summary sheet is
computed (headline.py), orders exclude cancellations, and the retention curve
sheet shows the benchmark (Dec 2009 excluded) next to the naive curve.
A manager should be able to read the Summary without scrolling and pivot
the Customer detail sheet themselves.
"""
from pathlib import Path

import duckdb
import pandas as pd

from headline import CENSORED_COHORT, headline

ROOT = Path(__file__).resolve().parents[1]
DB = ROOT / "data" / "processed" / "retail.duckdb"
LEDGER = ROOT / "outputs" / "tables" / "exclusion_ledger.csv"
OUT = ROOT / "outputs" / "online_retail_customer_analysis.xlsx"

BLUE_DARK, BLUE_MID, INK, MUTED = "#184F95", "#2A78D6", "#0B0B0B", "#52514E"


def main() -> int:
    con = duckdb.connect(str(DB), read_only=True)
    h = headline(con)
    k = h["kpis"]
    ledger = pd.read_csv(LEDGER)
    conc = con.execute("SELECT * FROM revenue_concentration ORDER BY revenue_decile").df()
    seg = con.execute("""
        SELECT segment, count(*) AS customers,
               round(100.0 * count(*) / sum(count(*)) OVER (), 1)           AS pct_customers,
               round(sum(monetary), 2)                                      AS net_revenue,
               round(100.0 * sum(monetary) / sum(sum(monetary)) OVER (), 1) AS pct_revenue,
               round(avg(recency_days), 0)                                  AS avg_recency_days,
               round(avg(frequency), 1)                                     AS avg_orders,
               round(avg(monetary), 2)                                      AS avg_customer_value
        FROM rfm GROUP BY 1 ORDER BY net_revenue DESC""").df()
    curve = con.execute(f"""
        SELECT period_number AS months_since_first_purchase,
               round(100.0 * sum(active_customers) FILTER (WHERE cohort_month > '{CENSORED_COHORT}')
                           / sum(cohort_size)      FILTER (WHERE cohort_month > '{CENSORED_COHORT}'), 2)
                   AS benchmark_retention_pct,
               round(100.0 * sum(active_customers) / sum(cohort_size), 2)
                   AS all_cohorts_retention_pct
        FROM cohort_retention WHERE period_number <= 12
        GROUP BY 1 ORDER BY 1""").df()
    cohort = con.execute("""
        SELECT cohort_month, period_number, retention_pct
        FROM cohort_retention WHERE period_number <= 12 ORDER BY 1, 2""").df()
    pivot = cohort.pivot(index="cohort_month", columns="period_number", values="retention_pct")
    pivot.columns = [f"M{c}" for c in pivot.columns]
    pivot = pivot.reset_index()
    detail = con.execute("""
        SELECT customer_id, segment, r_score, f_score, m_score, rfm_cell,
               recency_days, frequency AS orders, monetary AS net_revenue,
               first_purchase, last_purchase, cancelled_orders
        FROM rfm ORDER BY monetary DESC""").df()
    con.close()

    findings = [
        f"The top 10% of customers produce {h['top10_pct']:.1f}% of customer revenue; "
        f"the top 20% produce {h['top20_pct']:.1f}%. The bottom half produces {h['bottom50_pct']:.1f}%.",
        f"{100 - h['m1']:.0f}% of new customers do not return the next month (month-1 retention "
        f"{h['m1']:.1f}%); " + (f"retention keeps drifting down to {h['m10']:.1f}% by month 10."
                                 if h["m10"] < h["m1"] - 2 else
                                 f"after that it stays roughly flat ({h['m10']:.1f}% at month 10)."),
        f"Champions ({h['champ_cust_pct']:.1f}% of customers) generate {h['champ_rev_pct']:.1f}% "
        f"of customer revenue.",
        f"At Risk - High Value: {int(h['arhv_customers']):,} customers worth "
        f"GBP {h['arhv_revenue']:,.0f}, averaging {h['arhv_orders']:.1f} orders but "
        f"{h['arhv_recency']:.0f} days since their last one - the win-back target.",
        f"{k.pct_one_time_buyers:.1f}% of customers ordered exactly once; they contribute "
        f"{h['one_time_rev_pct']:.1f}% of customer revenue.",
        f"{k.pct_unattributed_revenue:.1f}% of net revenue has no customer ID and is invisible "
        f"to every customer-level number in this file.",
        f"The Dec 2009 cohort is left-censored (first month of data): it averages "
        f"{h['censored_avg']:.1f}% retention over months 1-12 vs {h['later_avg']:.1f}% for later "
        f"cohorts. It is excluded from the retention benchmark.",
    ]

    OUT.parent.mkdir(parents=True, exist_ok=True)
    with pd.ExcelWriter(OUT, engine="xlsxwriter") as xl:
        wb = xl.book
        f_title = wb.add_format({"bold": True, "font_size": 16, "font_color": INK})
        f_sub = wb.add_format({"font_size": 10, "font_color": MUTED})
        f_h = wb.add_format({"bold": True, "font_color": "white", "bg_color": BLUE_DARK,
                             "border": 1, "border_color": "#FFFFFF", "align": "center",
                             "valign": "vcenter", "text_wrap": True})
        f_lbl = wb.add_format({"font_color": MUTED, "font_size": 10})
        f_big = {
            "gbp": wb.add_format({"bold": True, "font_size": 18, "font_color": BLUE_DARK,
                                  "num_format": "£#,##0", "align": "left"}),
            "int": wb.add_format({"bold": True, "font_size": 18, "font_color": BLUE_DARK,
                                  "num_format": "#,##0", "align": "left"}),
            "dec": wb.add_format({"bold": True, "font_size": 18, "font_color": BLUE_DARK,
                                  "num_format": "0.0", "align": "left"}),
            "pct": wb.add_format({"bold": True, "font_size": 18, "font_color": BLUE_DARK,
                                  "num_format": '0.0"%"', "align": "left"}),
        }
        f_gbp = wb.add_format({"num_format": "£#,##0"})
        f_gbp2 = wb.add_format({"num_format": "£#,##0.00"})
        f_int = wb.add_format({"num_format": "#,##0"})
        f_note = wb.add_format({"font_size": 10, "font_color": INK, "text_wrap": True,
                                "valign": "top"})

        # ---------- Summary ----------
        ws = wb.add_worksheet("Summary")
        xl.sheets["Summary"] = ws
        ws.hide_gridlines(2)
        ws.set_column("A:A", 2)
        ws.set_column("B:G", 22)
        ws.write("B2", "Online Retail II - customer analysis", f_title)
        ws.write("B3", f"UK gift wholesaler · {k.first_day:%d %b %Y} - {k.last_day:%d %b %Y} "
                       f"· net of returns · GBP", f_sub)
        tiles = [
            ("Net revenue", float(k.net_revenue), "gbp"),
            ("Identified customers", int(k.customers), "int"),
            ("Orders (excl. cancellations)", int(k.orders), "int"),
            ("Median customer value", float(k.median_revenue_per_customer), "gbp"),
            ("Avg orders per customer", float(k.avg_orders_per_customer), "dec"),
            ("One-time buyers", float(k.pct_one_time_buyers), "pct"),
        ]
        for i, (label, val, kind) in enumerate(tiles):
            r = 4 + (i // 3) * 3
            c = 1 + (i % 3) * 2
            ws.write(r, c, label, f_lbl)
            ws.write(r + 1, c, val, f_big[kind])

        row = 11
        ws.write(row, 1, "Headline findings",
                 wb.add_format({"bold": True, "font_size": 12, "font_color": INK}))
        for i, text in enumerate(findings):
            ws.merge_range(row + 1 + i, 1, row + 1 + i, 6, f"{i + 1}. {text}", f_note)
            ws.set_row(row + 1 + i, 32)

        # ---------- data sheets ----------
        def sheet(df, name, widths=None, fmts=None, note=None):
            df.to_excel(xl, sheet_name=name, index=False, startrow=1)
            w = xl.sheets[name]
            w.hide_gridlines(2)
            for j, col in enumerate(df.columns):
                w.write(1, j, str(col).replace("_", " ").title(), f_h)
                width = (widths or {}).get(col, max(12, min(26, len(str(col)) + 4)))
                w.set_column(j, j, width, (fmts or {}).get(col))
            w.set_row(1, 30)
            w.freeze_panes(2, 0)
            if note:
                w.write(0, 0, note, f_sub)
            return w

        sheet(ledger.T.reset_index().rename(columns={"index": "step", 0: "rows"}),
              "Exclusion ledger", widths={"step": 34, "rows": 14}, fmts={"rows": f_int},
              note="Every row removed between the raw workbook and the analysed table.")

        w = sheet(conc, "Revenue concentration",
                  fmts={"decile_revenue": f_gbp, "avg_revenue_per_customer": f_gbp,
                        "min_revenue": f_gbp, "max_revenue": f_gbp, "customers": f_int},
                  note="Identified customers ranked by lifetime net revenue, in ten equal groups.")
        w.conditional_format(2, 3, 2 + len(conc) - 1, 3,
                             {"type": "data_bar", "bar_color": BLUE_MID})

        w = sheet(seg, "RFM segments", widths={"segment": 22},
                  fmts={"net_revenue": f_gbp, "avg_customer_value": f_gbp, "customers": f_int},
                  note="Percentile-rank R, F, M scores (tied customers share a score).")
        w.conditional_format(2, 4, 2 + len(seg) - 1, 4,
                             {"type": "data_bar", "bar_color": BLUE_MID})

        w = sheet(pivot, "Cohort heatmap", widths={"cohort_month": 16},
                  note="Retention %. Blank = not observable yet (not zero). "
                       "Dec 2009 row is left-censored.")
        w.conditional_format(2, 1, 2 + len(pivot) - 1, len(pivot.columns) - 1,
                             {"type": "3_color_scale", "min_color": "#FFFFFF",
                              "mid_color": "#9EC5F4", "max_color": "#184F95"})

        sheet(curve, "Retention curve", widths={"months_since_first_purchase": 16},
              note="Benchmark excludes the left-censored Dec 2009 cohort. "
                   "Pooled, weighted by cohort size.")

        sheet(detail, "Customer detail",
              fmts={"net_revenue": f_gbp2, "recency_days": f_int, "orders": f_int},
              note="One row per customer. Insert a PivotTable over this sheet.")

    print(f"  wrote {OUT.relative_to(ROOT)} ({OUT.stat().st_size / 1e6:.2f} MB)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
