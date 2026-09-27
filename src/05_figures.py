"""05_figures.py - the four report figures (PNG, outputs/figures/).

Adapted from the answer key's figures. Changes:
- Every number in a title or annotation is computed (headline.py), never typed.
- The retention curve shows the honest benchmark (Dec 2009 excluded) next to
  the naive all-cohort curve, so the left-censoring effect is visible.
- RFM wording says percentile-rank scores, not quintiles.
Palette: categorical slots in fixed order; sequential = one blue hue.
"""
from pathlib import Path

import duckdb
import matplotlib
matplotlib.use("Agg")
import matplotlib.colors as mcolors
import matplotlib.pyplot as plt
import numpy as np

from headline import CENSORED_COHORT, headline

ROOT = Path(__file__).resolve().parents[1]
DB = ROOT / "data" / "processed" / "retail.duckdb"
FIG = ROOT / "outputs" / "figures"

BLUE = ["#cde2fb", "#b7d3f6", "#9ec5f4", "#86b6ef", "#6da7ec", "#5598e7",
        "#3987e5", "#2a78d6", "#256abf", "#1c5cab", "#184f95", "#104281", "#0d366b"]
SEQ = mcolors.LinearSegmentedColormap.from_list("seqblue", BLUE)
S1, S2, S3 = "#2a78d6", "#eb6834", "#1baf7a"     # categorical slots 1-3
INK, INK2, MUTED = "#0b0b0b", "#52514e", "#8a8880"
GRID = "#e6e5e1"

plt.rcParams.update({
    "figure.facecolor": "white", "axes.facecolor": "white",
    "font.family": "DejaVu Sans", "font.size": 10,
    "axes.edgecolor": GRID, "axes.labelcolor": INK2,
    "xtick.color": INK2, "ytick.color": INK2,
    "axes.spines.top": False, "axes.spines.right": False,
    "axes.grid": True, "grid.color": GRID, "grid.linewidth": 0.8,
    "axes.axisbelow": True,
})


def title(ax, text, sub):
    """Bold title with a regular-weight subtitle underneath."""
    ax.set_title(text, loc="left", fontsize=13, color=INK, pad=24, fontweight="bold")
    ax.text(0, 1.02, sub, transform=ax.transAxes, fontsize=10, color=INK2)


def fig1_heatmap(con):
    df = con.execute("""
        SELECT cohort_month, period_number, retention_pct, cohort_size
        FROM cohort_retention WHERE period_number <= 12 ORDER BY 1, 2
    """).df()
    piv = df.pivot(index="cohort_month", columns="period_number", values="retention_pct")
    sizes = (df[df.period_number == 0]
             .set_index("cohort_month")["cohort_size"].reindex(piv.index))

    fig, ax = plt.subplots(figsize=(11.5, 8))
    m = np.ma.masked_invalid(piv.values)
    # Month 0 is always 100%: labelled, not shaded, so it doesn't flatten the scale.
    im = ax.imshow(np.where(piv.columns.values == 0, np.nan, m),
                   cmap=SEQ, vmin=0, vmax=40, aspect="auto")
    ax.set_xticks(range(len(piv.columns)))
    ax.set_xticklabels([f"M{c}" for c in piv.columns])
    ax.set_yticks(range(len(piv.index)))
    ax.set_yticklabels([f"{d:%b %Y}  (n={int(s):,})" for d, s in zip(piv.index, sizes)],
                       fontsize=9)
    ax.set_xlabel("Months since first purchase", labelpad=10)
    title(ax, "Monthly acquisition cohorts - retention",
          "Cell = % of the cohort with a net-positive order that month")
    for i in range(piv.shape[0]):
        for j in range(piv.shape[1]):
            v = piv.values[i, j]
            if np.isnan(v):
                continue
            if piv.columns[j] == 0:
                ax.text(j, i, "100", ha="center", va="center", fontsize=8, color=MUTED)
            else:
                ax.text(j, i, f"{v:.0f}", ha="center", va="center", fontsize=8,
                        color="white" if v > 22 else INK2)
    ax.grid(False)
    cb = fig.colorbar(im, ax=ax, fraction=0.025, pad=0.02)
    cb.set_label("Retention %", color=INK2)
    cb.outline.set_edgecolor(GRID)
    fig.text(0.01, 0.005,
             "Blank cells are months the data cannot observe yet - not zeros. "
             "Dec 2011 (9 days) is excluded. The Dec 2009 row is the first month of data "
             "and is left-censored.", fontsize=8, color=MUTED)
    fig.tight_layout()
    fig.savefig(FIG / "01_cohort_retention_heatmap.png", dpi=160, bbox_inches="tight")
    plt.close(fig)
    print("  01_cohort_retention_heatmap.png")


def fig2_curve(con, h):
    def curve(where):
        return con.execute(f"""
            SELECT period_number,
                   100.0 * sum(active_customers) / sum(cohort_size) AS retention_pct
            FROM cohort_retention
            WHERE period_number <= 12 {where}
            GROUP BY 1 ORDER BY 1""").df()
    bench = curve(f"AND cohort_month > '{CENSORED_COHORT}'")
    naive = curve("")

    fig, ax = plt.subplots(figsize=(9, 5))
    ax.plot(naive.period_number, naive.retention_pct, color=MUTED, linewidth=2,
            linestyle=(0, (4, 3)), label="All cohorts (incl. Dec 2009)", zorder=2)
    ax.plot(bench.period_number, bench.retention_pct, color=S1, linewidth=2,
            marker="o", markersize=7, markerfacecolor=S1, markeredgecolor="white",
            markeredgewidth=1.5, label="Benchmark (Dec 2009 excluded)", zorder=3)
    # Direct labels at the line ends, pushed apart if the lines end close together.
    y_naive, y_bench = naive.retention_pct.iloc[-1], bench.retention_pct.iloc[-1]
    if abs(y_naive - y_bench) < 5:
        mid = (y_naive + y_bench) / 2
        y_naive, y_bench = (mid + 2.5, mid - 2.5) if y_naive >= y_bench else (mid - 2.5, mid + 2.5)
    ax.text(12.25, y_naive, "all cohorts", va="center", fontsize=9, color=INK2)
    ax.text(12.25, y_bench, "benchmark", va="center", fontsize=9, color=INK)
    ax.annotate(f"Month 1: {h['m1']:.1f}%\n{100 - h['m1']:.0f}% never come back",
                xy=(1, h["m1"]), xytext=(2.4, 62), fontsize=10, color=INK,
                arrowprops=dict(arrowstyle="-", color=MUTED, linewidth=1))
    trend = "still drifting down" if h["m10"] < h["m1"] - 2 else "roughly flat after the cliff"
    ax.annotate(f"Month 10: {h['m10']:.1f}%\n{trend}",
                xy=(10, h["m10"]), xytext=(7.2, 45), fontsize=10, color=INK,
                arrowprops=dict(arrowstyle="-", color=MUTED, linewidth=1))
    ax.set_ylim(0, 105)
    ax.set_xlim(-0.3, 13.6)
    ax.set_xticks(range(0, 13))
    ax.set_xlabel("Months since first purchase")
    ax.set_ylabel("Customers still active (%)")
    ax.legend(loc="upper right", frameon=False, fontsize=9)
    title(ax, f"{100 - h['m1']:.0f}% of new customers do not return the next month",
          "Pooled retention, weighted by cohort size. Dec 2009 inflates the naive curve.")
    fig.tight_layout()
    fig.savefig(FIG / "02_retention_curve.png", dpi=160, bbox_inches="tight")
    plt.close(fig)
    print("  02_retention_curve.png")


def fig3_pareto(con):
    df = con.execute("""
        SELECT pct_of_customers, cumulative_pct_revenue
        FROM customer_revenue_ranked ORDER BY revenue_rank
    """).df()
    fig, ax = plt.subplots(figsize=(9, 5.4))
    ax.plot(df.pct_of_customers, df.cumulative_pct_revenue, color=S1, linewidth=2, zorder=3)
    ax.fill_between(df.pct_of_customers, df.cumulative_pct_revenue, color=S1, alpha=0.08)
    ax.plot([0, 100], [0, 100], color=MUTED, linewidth=1.2, linestyle=(0, (4, 4)), zorder=2)
    ax.text(62, 57, "perfect equality", fontsize=9, color=MUTED, rotation=32)
    for pct in (10, 20):
        y = float(np.interp(pct, df.pct_of_customers, df.cumulative_pct_revenue))
        ax.plot([pct, pct], [0, y], color=GRID, linewidth=1, zorder=1)
        ax.plot([0, pct], [y, y], color=GRID, linewidth=1, zorder=1)
        ax.plot([pct], [y], "o", color=S2, markersize=8,
                markeredgecolor="white", markeredgewidth=1.5, zorder=4)
        ax.annotate(f"top {pct}% of customers\n= {y:.1f}% of revenue",
                    xy=(pct, y), xytext=(pct + 8, y - 13), fontsize=10, color=INK,
                    arrowprops=dict(arrowstyle="-", color=MUTED, linewidth=1))
    ax.set_xlim(0, 100)
    ax.set_ylim(0, 102)
    ax.set_xlabel("Customers, ranked by lifetime net revenue (%)")
    ax.set_ylabel("Cumulative revenue (%)")
    title(ax, "Revenue is extremely concentrated",
          "Lorenz curve of lifetime net revenue per identified customer")
    fig.tight_layout()
    fig.savefig(FIG / "03_revenue_pareto.png", dpi=160, bbox_inches="tight")
    plt.close(fig)
    print("  03_revenue_pareto.png")


def fig4_segments(con, h):
    df = con.execute("""
        SELECT segment,
               round(100.0 * count(*) / sum(count(*)) OVER (), 1)           AS pct_customers,
               round(100.0 * sum(monetary) / sum(sum(monetary)) OVER (), 1) AS pct_revenue
        FROM rfm GROUP BY 1 ORDER BY pct_revenue DESC
    """).df()
    fig, axes = plt.subplots(1, 2, figsize=(12.5, 5.6), sharey=True)
    y = np.arange(len(df))[::-1]
    for ax, col, colour, label in (
        (axes[0], "pct_customers", S3, "Share of customers (%)"),
        (axes[1], "pct_revenue", S1, "Share of net revenue (%)"),
    ):
        ax.barh(y, df[col], height=0.62, color=colour, zorder=3)
        for yi, v in zip(y, df[col]):
            ax.text(v + 1.2, yi, f"{v:.1f}%", va="center", fontsize=9.5, color=INK2)
        ax.set_xlabel(label)
        ax.set_xlim(0, max(df[col]) * 1.22)
        ax.grid(axis="y", visible=False)
    axes[0].set_yticks(y)
    axes[0].set_yticklabels(df.segment, fontsize=10)
    fig.suptitle(f"{h['champ_cust_pct']:.0f}% of customers - the Champions - produce "
                 f"{h['champ_rev_pct']:.0f}% of net revenue",
                 x=0.012, ha="left", fontsize=13.5, color=INK, fontweight="bold", y=1.0)
    fig.text(0.012, 0.935, "RFM segments from percentile-rank scores (tied customers share "
             "a score); revenue is lifetime net of returns", fontsize=10, color=INK2, ha="left")
    fig.tight_layout(rect=(0, 0, 1, 0.92))
    fig.savefig(FIG / "04_rfm_segments.png", dpi=160, bbox_inches="tight")
    plt.close(fig)
    print("  04_rfm_segments.png")


def main() -> int:
    FIG.mkdir(parents=True, exist_ok=True)
    con = duckdb.connect(str(DB), read_only=True)
    h = headline(con)
    fig1_heatmap(con)
    fig2_curve(con, h)
    fig3_pareto(con)
    fig4_segments(con, h)
    con.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
