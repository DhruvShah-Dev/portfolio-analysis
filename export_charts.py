"""Export publication-ready charts from the reviewed analysis outputs."""

import json
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.dates as mdates
import matplotlib.pyplot as plt
from matplotlib.ticker import PercentFormatter
import pandas as pd


ROOT = Path(__file__).resolve().parent
OUT = ROOT / "charts"
BLUE = "#194A78"
ORANGE = "#D77A43"
GREEN = "#1D7A56"
RED = "#BD4B45"
INK = "#162A3A"
GRID = "#E3E8ED"


def style(ax):
    ax.set_facecolor("white")
    for side in ["top", "right", "left"]:
        ax.spines[side].set_visible(False)
    ax.spines["bottom"].set_color(GRID)
    ax.tick_params(colors="#506273", labelsize=9, length=0)
    ax.grid(axis="y", color=GRID, linewidth=0.8)
    ax.set_axisbelow(True)


def save(fig, name):
    fig.text(0.06, 0.035, "Source: Kenneth French Data Library. Portfolio is hypothetical; see README for rules and limits.",
             fontsize=8, color="#677889")
    fig.savefig(OUT / name, dpi=180, facecolor="white", bbox_inches="tight", pad_inches=0.18)
    plt.close(fig)


def main():
    OUT.mkdir(exist_ok=True)
    frame = pd.read_csv(ROOT / "analysis" / "monthly_analysis.csv", parse_dates=["month"])
    annual = pd.read_csv(ROOT / "analysis" / "annual_returns.csv")
    metrics = json.loads((ROOT / "analysis" / "metrics.json").read_text(encoding="utf-8"))

    fig, ax = plt.subplots(figsize=(10.5, 5.1))
    fig.subplots_adjust(left=0.08, right=0.97, top=0.82, bottom=0.18)
    style(ax)
    ax.plot(frame.month, frame.portfolio_wealth, color=BLUE, linewidth=2.3, label="Equal industry, net")
    ax.plot(frame.month, frame.market_wealth, color=ORANGE, linewidth=2.3, label="Broad market")
    ax.set_title("Growth of $1 invested at the start of 2000", loc="left", fontsize=16, fontweight="bold", color=INK, pad=24)
    ax.text(0, 1.04, "Monthly compounding through August 2026; 10 bps per traded dollar for the portfolio",
            transform=ax.transAxes, fontsize=9, color="#506273")
    ax.set_ylabel("Growth of $1", color=INK)
    ax.xaxis.set_major_locator(mdates.YearLocator(4))
    ax.xaxis.set_major_formatter(mdates.DateFormatter("%Y"))
    ax.legend(loc="upper left", frameon=False, ncol=2, fontsize=9)
    save(fig, "growth_of_one.png")

    fig, ax = plt.subplots(figsize=(10.5, 5.1))
    fig.subplots_adjust(left=0.08, right=0.97, top=0.82, bottom=0.18)
    style(ax)
    ax.plot(frame.month, frame.portfolio_drawdown, color=BLUE, linewidth=1.8, label="Equal industry, net")
    ax.plot(frame.month, frame.market_drawdown, color=ORANGE, linewidth=1.8, label="Broad market")
    ax.set_title("Equity diversification still left deep drawdowns", loc="left", fontsize=16, fontweight="bold", color=INK, pad=24)
    ax.text(0, 1.04, "Peak-to-trough loss measured on monthly compounded wealth", transform=ax.transAxes,
            fontsize=9, color="#506273")
    ax.yaxis.set_major_formatter(PercentFormatter(1))
    ax.xaxis.set_major_locator(mdates.YearLocator(4))
    ax.xaxis.set_major_formatter(mdates.DateFormatter("%Y"))
    ax.legend(loc="lower right", frameon=False, ncol=2, fontsize=9)
    save(fig, "drawdowns.png")

    fig, ax = plt.subplots(figsize=(10.5, 5.1))
    fig.subplots_adjust(left=0.08, right=0.97, top=0.82, bottom=0.18)
    style(ax)
    labels = [f"{int(y)}*" if int(y) == 2026 else str(int(y)) for y in annual.year]
    colors = [GREEN if x >= 0 else RED for x in annual.active_gap]
    ax.bar(range(len(annual)), annual.active_gap, color=colors, width=0.75)
    ax.axhline(0, color="#607080", linewidth=0.8)
    ax.set_xticks(range(0, len(labels), 2), labels[::2], rotation=0)
    ax.yaxis.set_major_formatter(PercentFormatter(1))
    ax.set_ylabel("Portfolio minus market", color=INK)
    ax.set_title("Active returns varied sharply by year", loc="left", fontsize=16, fontweight="bold", color=INK, pad=24)
    ax.text(0, 1.04, "Calendar-year total-return gap; *2026 is January–August only", transform=ax.transAxes,
            fontsize=9, color="#506273")
    save(fig, "annual_active_returns.png")

    fig, ax = plt.subplots(figsize=(8.6, 3.3))
    fig.subplots_adjust(left=0.20, right=0.96, top=0.74, bottom=0.24)
    style(ax)
    models = [("Market only", metrics["factor_models"]["market_only"]),
              ("Five factors", metrics["factor_models"]["five_factor"])]
    for index, (name, values) in enumerate(models):
        estimate = values["annualized_alpha_approx"]
        low, high = values["annualized_alpha_95ci_approx"]
        ax.plot([low, high], [index, index], color=BLUE, linewidth=3, solid_capstyle="round")
        ax.scatter([estimate], [index], color=ORANGE, s=80, zorder=3)
    ax.axvline(0, color="#758493", linestyle="--", linewidth=1)
    ax.set_yticks([0, 1], [x[0] for x in models])
    ax.set_ylim(-0.35, 1.35)
    ax.invert_yaxis()
    ax.set_xlim(-0.025, 0.04)
    ax.xaxis.set_major_formatter(PercentFormatter(1))
    ax.set_xlabel("Approximate annual regression residual", color=INK)
    ax.set_title("Neither factor-model residual is clearly positive", loc="left", fontsize=15, fontweight="bold", color=INK, pad=24)
    ax.text(0, 1.07, "Point estimate and 95% interval using six-lag robust standard errors", transform=ax.transAxes,
            fontsize=9, color="#506273")
    save(fig, "factor_residuals.png")
    print("Exported four charts to", OUT)


if __name__ == "__main__":
    main()
