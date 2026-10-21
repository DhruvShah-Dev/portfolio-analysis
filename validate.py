"""Independent high-impact checks against the published analysis outputs."""

import json
from pathlib import Path

import numpy as np
import pandas as pd


ROOT = Path(__file__).resolve().parent
RAW = ROOT / "data" / "processed"
OUT = ROOT / "analysis"


def annual_return(values):
    return float(np.exp(np.log1p(values).sum() * 12 / len(values)) - 1)


def main():
    sectors = pd.read_csv(RAW / "industry_monthly_returns.csv")
    factors = pd.read_csv(RAW / "market_factors_monthly.csv")
    published = pd.read_csv(OUT / "monthly_analysis.csv")
    reported = json.loads((OUT / "metrics.json").read_text(encoding="utf-8"))
    assert not sectors.duplicated(["month", "industry"]).any()
    assert not factors.duplicated(["month"]).any()
    assert sectors.groupby("month").industry.nunique().eq(10).all()
    assert len(published) == 320 and published.month.iloc[0] == "2000-01-01" and published.month.iloc[-1] == "2026-08-01"
    merged = published[["month", "equal_industry_gross", "market_total_return"]].merge(
        sectors.groupby("month", as_index=False).total_return.mean(), on="month", validate="one_to_one")
    assert np.allclose(merged.equal_industry_gross, merged.total_return, atol=1e-12)
    assert np.allclose(published.market_total_return, published.market_excess_return + published.risk_free_return, atol=1e-12)
    portfolio = published.equal_industry_net.to_numpy()
    market = published.market_total_return.to_numpy()
    assert abs(annual_return(portfolio) - reported["main_2000_to_latest"]["portfolio_net"]["annualized_return"]) < 1e-12
    assert abs(annual_return(market) - reported["main_2000_to_latest"]["market"]["annualized_return"]) < 1e-12
    assert abs(np.prod(1 + portfolio) - published.portfolio_wealth.iloc[-1]) < 1e-9
    assert abs(np.prod(1 + market) - published.market_wealth.iloc[-1]) < 1e-9
    def drawdown(values):
        wealth = np.r_[1, np.exp(np.cumsum(np.log1p(values)))]
        return float((wealth / np.maximum.accumulate(wealth) - 1).min())
    assert abs(drawdown(portfolio) - reported["main_2000_to_latest"]["portfolio_net"]["max_drawdown"]) < 1e-12
    assert abs(drawdown(market) - reported["main_2000_to_latest"]["market"]["max_drawdown"]) < 1e-12
    recent = published.loc[published.month >= "2015-01-01"]
    assert abs(annual_return(recent.equal_industry_net.to_numpy()) - reported["recent_2015_to_latest"]["portfolio_net"]["annualized_return"]) < 1e-12
    assert abs(annual_return(recent.market_total_return.to_numpy()) - reported["recent_2015_to_latest"]["market"]["annualized_return"]) < 1e-12
    assert reported["inflation"]["missing_cpi_months"] == ["2025-10-01"]
    print("PASS: grain, coverage, source return arithmetic, compounding, drawdowns, recent-window returns, and CPI gap")


if __name__ == "__main__":
    main()
