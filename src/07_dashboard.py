"""07_dashboard.py - self-contained HTML dashboard (outputs/dashboard.html).

Adapted from the answer key. Changes: every number is computed (headline.py),
the retention story matches the benchmark (Dec 2009 excluded), and RFM is
described as percentile-rank scoring. No CDN, no build step: the figures are
embedded, so the single file opens anywhere.
"""
from pathlib import Path
import base64

import duckdb

from headline import headline

ROOT = Path(__file__).resolve().parents[1]
DB = ROOT / "data" / "processed" / "retail.duckdb"
FIG = ROOT / "outputs" / "figures"
OUT = ROOT / "outputs" / "dashboard.html"


def b64(p: Path) -> str:
    return base64.b64encode(p.read_bytes()).decode()


def table(df, cols, money=(), pct=()):
    head = "".join(f"<th>{c.replace('_', ' ').title()}</th>" for c in cols)
    body = ""
    for _, r in df.iterrows():
        cells = ""
        for c in cols:
            v = r[c]
            if c in money:
                s = f"£{v:,.0f}"
            elif c in pct:
                s = f"{v:.1f}%"
            elif isinstance(v, (int, float)):
                s = f"{v:,.0f}" if float(v).is_integer() else f"{v:,.1f}"
            else:
                s = str(v)
            cls = ' class="num"' if c != cols[0] else ""
            cells += f"<td{cls}>{s}</td>"
        body += f"<tr>{cells}</tr>"
    return f"<table><thead><tr>{head}</tr></thead><tbody>{body}</tbody></table>"


def main() -> int:
    con = duckdb.connect(str(DB), read_only=True)
    h = headline(con)
    k = h["kpis"]
    seg = con.execute("""
        SELECT segment, count(*) AS customers,
               round(100.0 * count(*) / sum(count(*)) OVER (), 1)           AS pct_customers,
               round(sum(monetary), 0)                                      AS revenue,
               round(100.0 * sum(monetary) / sum(sum(monetary)) OVER (), 1) AS pct_revenue,
               round(avg(recency_days), 0)                                  AS recency_days,
               round(avg(frequency), 1)                                     AS orders
        FROM rfm GROUP BY 1 ORDER BY revenue DESC""").df()
    conc = con.execute("SELECT * FROM revenue_concentration ORDER BY revenue_decile").df()
    con.close()
    figs = {p.stem: b64(p) for p in sorted(FIG.glob("*.png"))}

    trend = ("and keeps drifting down" if h["m10"] < h["m1"] - 2
             else "then stays roughly flat")
    tiles = [
        ("Net revenue", f"£{k.net_revenue / 1e6:,.2f}M", "net of returns"),
        ("Identified customers", f"{int(k.customers):,}", "with a customer ID"),
        ("Top 10% of customers", f"{h['top10_pct']:.1f}%", "of customer revenue"),
        ("Month-1 retention", f"{h['m1']:.1f}%", f"{trend} (benchmark)"),
        ("One-time buyers", f"{k.pct_one_time_buyers:.1f}%",
         f"{h['one_time_rev_pct']:.1f}% of customer revenue"),
        ("No customer ID", f"{k.pct_unattributed_revenue:.1f}%",
         f"£{k.unattributed_revenue / 1e6:,.2f}M of net revenue"),
    ]
    tiles_html = "".join(
        f'<div class="tile"><div class="tl">{a}</div><div class="tv">{b}</div>'
        f'<div class="tc">{c}</div></div>' for a, b, c in tiles)

    html = f"""<!DOCTYPE html><html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>Online Retail II - Customer Analysis</title><style>
:root{{color-scheme:light;--surface-1:#fcfcfb;--surface-2:#ffffff;--line:#e6e5e1;
--text-primary:#0b0b0b;--text-secondary:#52514e;--muted:#6f6e68;
--series-1:#2a78d6;--series-2:#c2521f;--accent-soft:#eef4fd}}
@media(prefers-color-scheme:dark){{:root:not([data-theme="light"]){{color-scheme:dark;
--surface-1:#1a1a19;--surface-2:#232322;--line:#33332f;--text-primary:#fff;
--text-secondary:#c3c2b7;--muted:#a3a29a;--series-1:#6da7ec;--series-2:#eb6834;
--accent-soft:#1b2440}}}}
*{{box-sizing:border-box}}
body{{margin:0;background:var(--surface-1);color:var(--text-primary);
font:15px/1.6 -apple-system,BlinkMacSystemFont,"Segoe UI",Roboto,Helvetica,Arial,sans-serif}}
.wrap{{max-width:1180px;margin:0 auto;padding:40px 16px 80px}}
h1{{font-size:28px;margin:0 0 6px;letter-spacing:-.02em}}
.sub{{color:var(--text-secondary);margin:0 0 28px;font-size:14px}}
h2{{font-size:19px;margin:44px 0 6px}}
.tiles{{display:grid;grid-template-columns:repeat(auto-fit,minmax(170px,1fr));gap:12px;margin:24px 0}}
.tile{{background:var(--surface-2);border:1px solid var(--line);border-radius:10px;padding:14px 16px}}
.tl{{font-size:11px;text-transform:uppercase;letter-spacing:.06em;color:var(--muted)}}
.tv{{font-size:26px;font-weight:700;margin:4px 0 2px;color:var(--text-primary)}}
.tc{{font-size:12px;color:var(--text-secondary)}}
figure{{margin:18px 0;background:#fff;border:1px solid var(--line);border-radius:10px;padding:14px}}
figure img{{width:100%;height:auto;display:block}}
figcaption{{font-size:13px;color:#52514e;margin-top:10px}}
.scroll{{overflow-x:auto}}
table{{width:100%;border-collapse:collapse;font-size:13.5px;margin:14px 0;
background:var(--surface-2);border:1px solid var(--line)}}
th{{text-align:left;font-size:11px;text-transform:uppercase;letter-spacing:.05em;
color:var(--muted);padding:10px;border-bottom:2px solid var(--line);white-space:nowrap}}
td{{padding:9px 10px;border-bottom:1px solid var(--line);white-space:nowrap}}
td.num,th:not(:first-child){{text-align:right}}
tbody tr:hover{{background:var(--accent-soft)}}
.note{{border-left:3px solid var(--series-2);background:var(--accent-soft);
padding:12px 16px;border-radius:0 8px 8px 0;font-size:14px;margin:16px 0}}
footer{{margin-top:56px;padding-top:18px;border-top:1px solid var(--line);
font-size:12.5px;color:var(--muted)}}
</style></head><body><div class="wrap">
<h1>Online Retail II - customer analysis</h1>
<p class="sub">UK gift wholesaler · {k.first_day:%d %b %Y} - {k.last_day:%d %b %Y} ·
{h['raw_rows']:,} raw rows → {h['clean_rows']:,} analysed · net of returns, GBP</p>

<div class="tiles">{tiles_html}</div>

<div class="note"><b>Read this first.</b> {k.pct_unattributed_revenue:.1f}% of net revenue
(£{k.unattributed_revenue:,.0f}) has no customer ID, so it is invisible to every
customer-level number on this page. Everything below covers {int(k.customers):,}
identified customers with net-positive lifetime revenue.</div>

<h2>1. Revenue concentration</h2>
<figure><img alt="Lorenz curve of lifetime net revenue per customer"
src="data:image/png;base64,{figs['03_revenue_pareto']}">
<figcaption>The top 10% of customers produce {h['top10_pct']:.1f}% of customer revenue and
the top 20% produce {h['top20_pct']:.1f}%; the bottom half produces {h['bottom50_pct']:.1f}%.
The single largest customer is {h['top_customer_pct']:.1f}% on their own.</figcaption></figure>
<div class="scroll">{table(conc, ['revenue_decile', 'customers', 'decile_revenue',
                          'pct_of_total_revenue', 'cumulative_pct_of_revenue',
                          'avg_revenue_per_customer'],
                     money=('decile_revenue', 'avg_revenue_per_customer'),
                     pct=('pct_of_total_revenue', 'cumulative_pct_of_revenue'))}</div>

<h2>2. Retention</h2>
<figure><img alt="Retention curve, benchmark vs all cohorts"
src="data:image/png;base64,{figs['02_retention_curve']}">
<figcaption>{100 - h['m1']:.0f}% of new customers do not come back the next month
(month-1 retention {h['m1']:.1f}%), and retention is {h['m10']:.1f}% by month 10. The
benchmark excludes the left-censored Dec 2009 cohort; the dashed line shows how much
it inflates a naive curve.</figcaption></figure>
<figure><img alt="Cohort retention heatmap"
src="data:image/png;base64,{figs['01_cohort_retention_heatmap']}">
<figcaption>Blank cells are months the data cannot observe yet - not zeros. December
2011 has only 9 days of data and is excluded.</figcaption></figure>

<div class="note"><b>Left-censoring.</b> The Dec 2009 cohort averages
{h['censored_avg']:.1f}% retention over months 1-12, against {h['later_avg']:.1f}% for every
later cohort. It is not a better cohort: it is the first month of data, so long-standing
customers who happened to order that month are labelled "new".</div>

<h2>3. RFM segments</h2>
<figure><img alt="RFM segment shares"
src="data:image/png;base64,{figs['04_rfm_segments']}">
<figcaption>Champions are {h['champ_cust_pct']:.1f}% of customers and
{h['champ_rev_pct']:.1f}% of customer revenue. The segment to act on is
<b>At Risk - High Value</b>: {int(h['arhv_customers']):,} customers worth
£{h['arhv_revenue']:,.0f}, averaging {h['arhv_orders']:.1f} orders but
{h['arhv_recency']:.0f} days since their last one. Scores are percentile ranks, so tied
customers always share a score; they are relative and must be refitted to compare
periods.</figcaption></figure>
<div class="scroll">{table(seg, ['segment', 'customers', 'pct_customers', 'revenue',
                         'pct_revenue', 'recency_days', 'orders'],
                    money=('revenue',), pct=('pct_customers', 'pct_revenue'))}</div>

<h2>4. What this analysis cannot tell you</h2>
<ul>
<li><b>{k.pct_unattributed_revenue:.1f}% of net revenue has no customer ID.</b> If those
buyers are systematically different (guest checkout, trade counter), every customer-level
conclusion is biased in an unknown direction.</li>
<li><b>Two years is not a lifetime.</b> Customers acquired in late 2011 are censored, so
cohort value comparisons across the period are not like-for-like.</li>
<li><b>No cost data.</b> Revenue is not margin.</li>
<li><b>No marketing or channel data.</b> Nothing here explains <em>why</em> customers
do not return; it only shows that they do not.</li>
<li><b>One retailer, 2009-2011.</b> Nothing here generalises to other businesses or to
today.</li>
</ul>

<footer>Source: UCI Machine Learning Repository, Online Retail II (CC BY 4.0).
{h['raw_rows']:,} raw rows, {h['clean_rows']:,} kept after a documented exclusion ledger.
Pipeline: DuckDB + SQL + Python, with data-contract tests in <code>tests/</code>.</footer>
</div></body></html>"""

    OUT.write_text(html)
    print(f"  wrote {OUT.relative_to(ROOT)} ({OUT.stat().st_size / 1e6:.2f} MB, self-contained)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
