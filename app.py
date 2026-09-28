"""app.py - interactive dashboard for the Online Retail II customer analysis.

Run locally:   streamlit run app.py
Reads only the CSVs in outputs/tables/ (built by the pipeline), so it always
shows the same numbers as the SQL. Calculations live in app_logic.py and are
tested in tests/test_dashboard.py.
"""
import pandas as pd
import plotly.graph_objects as go
import streamlit as st

import app_logic as L

# Palette: categorical slots 1-3 (validated), one sequential blue ramp.
S1, S2, S3 = "#2a78d6", "#eb6834", "#1baf7a"
INK, INK2, MUTED, GRID = "#0b0b0b", "#52514e", "#8a8880", "#e6e5e1"
BLUES = ["#f4f8fe", "#cde2fb", "#9ec5f4", "#6da7ec", "#3987e5", "#256abf", "#184f95", "#0d366b"]
GROUP_COLOUR = {"Core (Champions, Loyal)": S1, "At risk": S2, "New, hibernating or lost": S3}
SMALL_SAMPLE = 100   # warn when a retention base is smaller than this

st.set_page_config(page_title="Online Retail II - Customer Analysis", layout="wide")


@st.cache_data
def get_data():
    return L.load()


def style(fig, height=420, title=None):
    fig.update_layout(template="plotly_white", height=height,
                      margin=dict(l=10, r=10, t=50 if title else 20, b=10),
                      title=dict(text=title, x=0, font=dict(size=15, color=INK)) if title else None,
                      font=dict(color=INK2), hoverlabel=dict(bgcolor="white"),
                      legend=dict(orientation="h", y=-0.2))
    fig.update_xaxes(gridcolor=GRID, zeroline=False)
    fig.update_yaxes(gridcolor=GRID, zeroline=False)
    return fig


data = get_data()
rfm_all, activity, kpis = data["rfm"], data["activity"], data["kpis"]
segments_all = (rfm_all.groupby("segment")["monetary"].sum()
                .sort_values(ascending=False).index.tolist())

# ------------------------------------------------------------------ sidebar
st.sidebar.header("Filters")
country_counts = rfm_all["country"].value_counts()
country_options = (["All countries", "United Kingdom only", "Outside the UK"]
                   + [c for c in country_counts.index if c != "United Kingdom"])
country = st.sidebar.selectbox(
    "Country", country_options,
    format_func=lambda c: f"{c} ({country_counts[c]:,})" if c in country_counts else c)
segments = st.sidebar.multiselect("RFM segments", segments_all, default=segments_all)

cohort_months = sorted(activity["cohort_month"].unique())
c_from, c_to = st.sidebar.select_slider(
    "Cohorts (first-purchase month)", options=cohort_months,
    value=(cohort_months[0], cohort_months[-1]),
    format_func=lambda d: pd.Timestamp(d).strftime("%b %Y"))
exclude_censored = st.sidebar.checkbox(
    "Exclude Dec 2009 cohort", value=True,
    help="December 2009 is the first month of data, so long-standing customers who "
         "ordered that month look 'new'. It retains about twice as well as every later "
         "cohort, which inflates retention. Excluded from the benchmark by default.")
st.sidebar.caption("Filters choose which customers are shown. RFM scores are always "
                   "ranked against all customers, so a customer's segment never "
                   "changes with the filters.")

sel = L.filter_customers(rfm_all, country, segments)

# ------------------------------------------------------------------ header
st.title("Online Retail II - customer analysis")
st.caption(f"UK online gift wholesaler · {kpis['first_day'][:10]} to {kpis['last_day'][:10]} · "
           f"{int(data['ledger']['raw_rows']):,} raw rows → "
           f"{int(data['ledger']['clean_rows']):,} analysed · net of returns, GBP")
st.info(f"**Read this first:** {kpis['pct_unattributed_revenue']:.1f}% of net revenue "
        f"(£{kpis['unattributed_revenue']:,.0f}) has no customer ID, so no customer-level "
        f"number here can include it.")

if sel.empty:
    st.warning("No customers match these filters. Widen the country or segment selection.")
    st.stop()

grid = L.retention_grid(activity, sel["customer_id"], exclude_censored, c_from, c_to)
curve = L.pooled_curve(grid) if not grid.empty else pd.DataFrame()
bench = L.pooled_curve(L.retention_grid(activity, exclude_censored=True))
s = L.summary(sel, rfm_all)

tab_over, tab_ret, tab_rfm, tab_conc, tab_dq = st.tabs(
    ["Overview", "Retention", "Customers (RFM)", "Revenue concentration", "Data quality"])

# ------------------------------------------------------------------ overview
with tab_over:
    m1 = curve.loc[curve["period_number"] == 1] if not curve.empty else pd.DataFrame()
    m1_value = f"{m1['retention_pct'].iloc[0]:.1f}%" if len(m1) else "n/a"
    m1_base = int(m1["base"].iloc[0]) if len(m1) else 0
    tiles = [
        ("Customers selected", f"{s['customers']:,}", f"of {len(rfm_all):,} identified customers"),
        ("Customer revenue", f"£{s['revenue']:,.0f}",
         f"{s['revenue_share']:.1f}% of all customer revenue"),
        ("Month-1 retention", m1_value, f"base: {m1_base:,} customers"),
        ("Median customer value", f"£{s['median_value']:,.0f}",
         "median, not mean: revenue is heavily skewed"),
        ("Avg orders per customer", f"{s['avg_orders']:.1f}",
         "purchases only, cancellations excluded"),
        ("One-time buyers", f"{s['one_time_pct']:.1f}%", "ordered exactly once"),
    ]
    for row in (tiles[:3], tiles[3:]):
        cols = st.columns(3)
        for col, (label, value, note) in zip(cols, row):
            col.metric(label, value)
            col.caption(note)
    if 0 < m1_base < SMALL_SAMPLE:
        st.warning(f"Only {m1_base} customers in the month-1 base - retention for this "
                   f"selection is too small to trust.")

# ------------------------------------------------------------------ retention
with tab_ret:
    if grid.empty:
        st.warning("No cohorts match these filters.")
    else:
        g12 = grid[grid["period_number"].between(1, 12)]
        piv = g12.pivot(index="cohort_month", columns="period_number", values="retention_pct")
        act = g12.pivot(index="cohort_month", columns="period_number", values="active_customers")
        sizes = grid[grid["period_number"] == 0].set_index("cohort_month")["cohort_size"]
        ylab = [f"{d:%b %Y} (n={sizes[d]:,})" for d in piv.index]
        custom = [[f"{int(a):,} of {sizes[d]:,}" if pd.notna(a) else "" for a in act.loc[d]]
                  for d in piv.index]
        heat = go.Figure(go.Heatmap(
            z=piv.values, x=[f"M{p}" for p in piv.columns], y=ylab,
            colorscale=[[i / (len(BLUES) - 1), b] for i, b in enumerate(BLUES)],
            zmin=0, zmax=40, customdata=custom,
            text=[["" if pd.isna(v) else f"{v:.0f}" for v in r] for r in piv.values],
            texttemplate="%{text}", textfont=dict(size=10),
            hovertemplate="%{y}<br>%{x}: %{z:.1f}% retained (%{customdata})<extra></extra>",
            colorbar=dict(title="Retention %")))
        heat.update_yaxes(autorange="reversed")
        style(heat, height=max(360, 28 * len(piv) + 80),
              title="Cohort retention: % of each cohort active N months after first purchase")
        st.plotly_chart(heat, width="stretch")
        st.caption("Blank cells are months the data cannot observe yet - not zeros. "
                   "December 2011 has only 9 days of data and is excluded. "
                   "Colour is capped at 40%; hover for exact values.")

        line = go.Figure()
        line.add_trace(go.Scatter(
            x=bench["period_number"], y=bench["retention_pct"], name="All customers (benchmark)",
            line=dict(color=MUTED, width=2, dash="dash"),
            hovertemplate="Month %{x}: %{y:.1f}%<extra>benchmark</extra>"))
        line.add_trace(go.Scatter(
            x=curve["period_number"], y=curve["retention_pct"], name="Your selection",
            mode="lines+markers", line=dict(color=S1, width=2), marker=dict(size=8),
            customdata=curve[["active_customers", "base"]],
            hovertemplate="Month %{x}: %{y:.1f}% (%{customdata[0]:,} of %{customdata[1]:,})"
                          "<extra>selection</extra>"))
        line.update_yaxes(range=[0, 105], title="Customers still active (%)")
        line.update_xaxes(dtick=1, title="Months since first purchase")
        style(line, title="Retention curve, pooled across cohorts (weighted by cohort size)")
        st.plotly_chart(line, width="stretch")
        small = curve[(curve["period_number"] >= 1) & (curve["base"] < SMALL_SAMPLE)]
        if len(small):
            st.warning(f"From month {int(small['period_number'].min())} the base is under "
                       f"{SMALL_SAMPLE} customers - treat those points as noise.")

# ------------------------------------------------------------------ RFM
with tab_rfm:
    seg = (sel.groupby("segment")
           .agg(customers=("customer_id", "size"), revenue=("monetary", "sum"),
                avg_orders=("frequency", "mean"), avg_recency=("recency_days", "mean"))
           .reindex([x for x in segments_all if x in set(sel["segment"])]).reset_index())
    seg["pct_customers"] = 100 * seg["customers"] / seg["customers"].sum()
    seg["pct_revenue"] = 100 * seg["revenue"] / seg["revenue"].sum()

    left, right = st.columns(2)
    for col, field, colour, label in ((left, "pct_customers", S3, "Share of customers (%)"),
                                      (right, "pct_revenue", S1, "Share of revenue (%)")):
        bar = go.Figure(go.Bar(
            x=seg[field], y=seg["segment"], orientation="h", marker_color=colour,
            text=seg[field].map(lambda v: f"{v:.1f}%"), textposition="outside",
            customdata=seg[["customers", "revenue"]],
            hovertemplate="%{y}<br>%{x:.1f}% · %{customdata[0]:,} customers · "
                          "£%{customdata[1]:,.0f}<extra></extra>"))
        bar.update_yaxes(autorange="reversed")
        bar.update_xaxes(title=label, range=[0, seg[field].max() * 1.25])
        col.plotly_chart(style(bar, height=380), width="stretch")

    arhv = sel[sel["segment"] == "At Risk - High Value"]
    if len(arhv):
        st.markdown(f"**Win-back target - At Risk - High Value:** {len(arhv):,} customers "
                    f"worth £{arhv['monetary'].sum():,.0f}, averaging "
                    f"{arhv['frequency'].mean():.1f} orders but "
                    f"{arhv['recency_days'].mean():.0f} days since their last one.")

    sc = go.Figure()
    for grp, colour in GROUP_COLOUR.items():
        d = sel[sel["segment"].map(L.SEGMENT_GROUP) == grp]
        if d.empty:
            continue
        sc.add_trace(go.Scattergl(
            x=d["recency_days"], y=d["monetary"], mode="markers", name=grp,
            marker=dict(color=colour, size=7, opacity=0.7, line=dict(width=0.5, color="white")),
            customdata=d[["customer_id", "segment", "frequency"]],
            hovertemplate="Customer %{customdata[0]}<br>%{customdata[1]}<br>"
                          "%{customdata[2]} orders · £%{y:,.0f} · %{x} days since last order"
                          "<extra></extra>"))
    sc.update_xaxes(title="Days since last purchase (recency)")
    sc.update_yaxes(title="Lifetime net revenue (log scale)", type="log", dtick=1,
                    tickprefix="£", tickformat=",.0f")
    st.plotly_chart(style(sc, height=460, title="Every customer: recency vs value"),
                    width="stretch")

    st.subheader("Customer list")
    query = st.text_input("Find a customer ID", "")
    table = sel[["customer_id", "country", "segment", "rfm_cell", "recency_days",
                 "frequency", "monetary", "first_purchase", "last_purchase"]].rename(
        columns={"frequency": "orders", "monetary": "net_revenue_gbp"})
    if query.strip():
        table = table[table["customer_id"].astype(str).str.contains(query.strip())]
    st.dataframe(table.sort_values("net_revenue_gbp", ascending=False),
                 width="stretch", hide_index=True, height=360)
    st.download_button("Download this list (CSV)", table.to_csv(index=False),
                       file_name="customers_filtered.csv", mime="text/csv")

# ------------------------------------------------------------------ concentration
with tab_conc:
    lc = L.lorenz(sel)
    fig = go.Figure()
    fig.add_trace(go.Scatter(x=[0, 100], y=[0, 100], name="Perfect equality",
                             line=dict(color=MUTED, dash="dot", width=1.5), hoverinfo="skip"))
    fig.add_trace(go.Scatter(
        x=lc["pct_of_customers"], y=lc["cumulative_pct_revenue"], name="Your selection",
        line=dict(color=S1, width=2), fill="tozeroy", fillcolor="rgba(42,120,214,0.08)",
        hovertemplate="Top %{x:.1f}% of customers = %{y:.1f}% of revenue<extra></extra>"))
    for pct in (10, 20):
        y = L.share_at(lc, pct)
        fig.add_trace(go.Scatter(
            x=[pct], y=[y], mode="markers+text", showlegend=False,
            marker=dict(color=S2, size=10, line=dict(color="white", width=1.5)),
            text=[f"top {pct}% = {y:.1f}%"], textposition="middle right",
            hovertemplate=f"Top {pct}% of customers = %{{y:.1f}}% of revenue<extra></extra>"))
    fig.update_xaxes(title="Customers, ranked by lifetime net revenue (%)", range=[0, 100])
    fig.update_yaxes(title="Cumulative share of revenue (%)", range=[0, 102])
    st.plotly_chart(style(fig, height=460, title="How concentrated is revenue?"),
                    width="stretch")
    dec = L.deciles(sel)
    dec["decile_revenue"] = dec["decile_revenue"].round(0).astype("int64")
    st.dataframe(dec.rename(columns={"revenue_decile": "decile (1 = top 10%)",
                                     "decile_revenue": "revenue_gbp",
                                     "pct_of_total_revenue": "% of revenue",
                                     "cumulative_pct_of_revenue": "cumulative %"}),
                 width="stretch", hide_index=True)

# ------------------------------------------------------------------ data quality
with tab_dq:
    led = data["ledger"]
    st.subheader("Exclusion ledger")
    st.caption("Every row removed between the raw file and the analysed table. "
               "The pipeline fails if these do not add up exactly.")
    st.dataframe(pd.DataFrame({
        "step": ["Raw rows loaded", "- Duplicate rows (business key)",
                 "- Non-product / service codes", "- Warehouse write-offs",
                 "- Zero or negative price", "= Rows analysed"],
        "rows": [led["raw_rows"], -led["removed_duplicates"], -led["removed_service_codes"],
                 -led["removed_writeoffs"], -led["removed_nonpositive_price"],
                 led["clean_rows"]]}), hide_index=True)
    st.subheader("What this analysis cannot tell you")
    st.markdown(f"""
- **{kpis['pct_unattributed_revenue']:.1f}% of net revenue has no customer ID.** If those
  buyers behave differently, every customer-level result is biased in an unknown direction.
- **Two years is not a lifetime.** Customers acquired in late 2011 are censored.
- **No cost data.** Revenue is not margin.
- **No marketing or channel data.** Nothing here explains *why* customers do not return.
- **Segment thresholds are business conventions**, not something the data discovered.
""")
    st.caption("Source: UCI Machine Learning Repository, Online Retail II (CC BY 4.0).")
