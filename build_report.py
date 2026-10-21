"""Build the canonical, source-backed portfolio report artifact."""

import json
import os
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd
import duckdb


ROOT = Path(__file__).resolve().parent
OUT = ROOT / "analysis"


def percent(x, digits=1):
    return f"{100 * x:.{digits}f}%"


def main():
    os.chdir(ROOT)
    metrics = json.loads((OUT / "metrics.json").read_text(encoding="utf-8"))
    monthly = pd.read_csv(OUT / "monthly_analysis.csv")
    annual = pd.read_csv(OUT / "annual_returns.csv")
    main_period = metrics["main_2000_to_latest"]
    recent = metrics["recent_2015_to_latest"]
    p, m = main_period["portfolio_net"], main_period["market"]
    title = "Equal industry allocation: a modest long-run edge, a recent reversal"
    generated = datetime.now(timezone.utc).isoformat()
    sources = [
        {"id": "analysis_code", "label": "Portfolio analysis calculations", "path": "analyze.py",
         "query": {"engine": "python", "language": "python",
                   "description": "Reproducible monthly portfolio, benchmark, risk, factor, and sensitivity calculations from local source files.",
                   "tables_used": ["data/processed/industry_monthly_returns.csv", "data/processed/market_factors_monthly.csv", "data/raw/fred_usrec.csv", "data/raw/fred_cpiaucsl.csv"],
                   "filters": ["January 2000 through August 2026", "Ten value-weighted U.S. industry return series", "Monthly rebalance to 10% per industry"]}},
        {"id": "french_industry", "label": "Kenneth French 10 Industry Portfolios", "path": "data/raw/industries.zip",
         "url": "https://mba.tuck.dartmouth.edu/pages/faculty/ken.french/data_library.html"},
        {"id": "french_factors", "label": "Kenneth French 5 Factors", "path": "data/raw/factors.zip",
         "url": "https://mba.tuck.dartmouth.edu/pages/faculty/ken.french/data_library.html"},
        {"id": "fred_recession", "label": "FRED USREC recession indicator", "path": "data/raw/fred_usrec.csv",
         "url": "https://fred.stlouisfed.org/series/USREC"},
        {"id": "fred_cpi", "label": "FRED CPIAUCSL consumer price index", "path": "data/raw/fred_cpiaucsl.csv",
         "url": "https://fred.stlouisfed.org/series/CPIAUCSL"},
    ]
    datasets = {
        "headline": [{"portfolio_return": p["annualized_return"], "market_return": m["annualized_return"],
                      "portfolio_volatility": p["annualized_volatility"], "market_volatility": m["annualized_volatility"],
                      "portfolio_drawdown": p["max_drawdown"], "market_drawdown": m["max_drawdown"],
                      "recent_gap_pp": recent["annualized_return_gap_pp"]}],
        "wealth": [{"month": row.month[:7], "series": series, "growth": float(value)}
                   for row in monthly.itertuples(index=False)
                   for series, value in [("Equal industry, net", row.portfolio_wealth), ("Broad market", row.market_wealth)]],
        "drawdown": [{"month": row.month[:7], "series": series, "drawdown": float(value)}
                     for row in monthly.itertuples(index=False)
                     for series, value in [("Equal industry, net", row.portfolio_drawdown), ("Broad market", row.market_drawdown)]],
        "annual_active": [{"year": f"{int(row.year)} YTD" if int(row.year) == 2026 else str(int(row.year)),
                           "active_gap": float(row.active_gap)} for row in annual.itertuples(index=False)],
        "periods": [{"period": label, "portfolio_return": metrics[key]["portfolio_net"]["annualized_return"],
                     "market_return": metrics[key]["market"]["annualized_return"],
                     "return_gap": metrics[key]["annualized_return_gap_pp"] / 100}
                    for label, key in [("2000–2026", "main_2000_to_latest"), ("2015–2026", "recent_2015_to_latest"),
                                       ("2020–2026", "since_2020")]],
        "factor_models": [{"model": "Market only", "alpha": metrics["factor_models"]["market_only"]["annualized_alpha_approx"],
                           "ci_range": f"{percent(metrics['factor_models']['market_only']['annualized_alpha_95ci_approx'][0])} to {percent(metrics['factor_models']['market_only']['annualized_alpha_95ci_approx'][1])}",
                           "r2": metrics["factor_models"]["market_only"]["r_squared"]},
                          {"model": "Five factors", "alpha": metrics["factor_models"]["five_factor"]["annualized_alpha_approx"],
                           "ci_range": f"{percent(metrics['factor_models']['five_factor']['annualized_alpha_95ci_approx'][0])} to {percent(metrics['factor_models']['five_factor']['annualized_alpha_95ci_approx'][1])}",
                           "r2": metrics["factor_models"]["five_factor"]["r_squared"]}],
        "costs": [{"trading_cost_bps": int(bps), "annualized_return": value}
                  for bps, value in metrics["cost"]["cost_sensitivity"].items()],
        "sector_contribution": [{"industry": sector, "mean_monthly_contribution": value,
                                 "annualized_volatility": metrics["sector_annualized_volatility"][sector]}
                                for sector, value in sorted(metrics["sector_mean_monthly_contribution"].items(), key=lambda item: -item[1])],
    }
    snapshot_dir = OUT / "report_snapshot"
    snapshot_dir.mkdir(exist_ok=True)
    with duckdb.connect() as connection:
        for name, rows in datasets.items():
            snapshot_file = snapshot_dir / f"{name}.csv"
            pd.DataFrame(rows).to_csv(snapshot_file, index=False)
            sql = f"SELECT * FROM read_csv_auto('{snapshot_file.relative_to(ROOT).as_posix()}')"
            datasets[name] = json.loads(connection.execute(sql).df().to_json(orient="records"))
            sources.append({"id": f"dataset_{name}", "label": f"Reviewed report dataset: {name}",
                            "path": str(snapshot_file.relative_to(ROOT)).replace('\\', '/'),
                            "query": {"engine": "duckdb", "language": "sql", "sql": sql,
                                      "description": f"Reads the {name} report snapshot generated from analyze.py results.",
                                      "tables_used": [str(snapshot_file.relative_to(ROOT)).replace('\\', '/')]}})
    cards = [
        {"id": "portfolio_return", "description": "Geometric annual return after modeled rebalancing costs, January 2000–August 2026.", "dataset": "headline", "sourceId": "dataset_headline",
         "metrics": [{"label": "Portfolio annual return", "field": "portfolio_return", "format": "percent"}, {"label": "Market", "field": "market_return", "format": "percent"}]},
        {"id": "volatility", "description": "Standard deviation of monthly returns multiplied by the square root of 12.", "dataset": "headline", "sourceId": "dataset_headline",
         "metrics": [{"label": "Portfolio volatility", "field": "portfolio_volatility", "format": "percent"}, {"label": "Market", "field": "market_volatility", "format": "percent"}]},
        {"id": "drawdown", "description": "Largest peak-to-trough loss on monthly compounded wealth.", "dataset": "headline", "sourceId": "dataset_headline",
         "metrics": [{"label": "Portfolio max drawdown", "field": "portfolio_drawdown", "format": "percent"}, {"label": "Market", "field": "market_drawdown", "format": "percent"}]},
        {"id": "recent_gap", "description": "Portfolio annualized return minus market annualized return in percentage points, January 2015–August 2026.", "dataset": "headline", "sourceId": "dataset_headline",
         "metrics": [{"label": "Return gap since 2015 (pp)", "field": "recent_gap_pp", "format": "number", "unit": "pp", "signed": True}]},
    ]
    charts = [
        {"id": "wealth", "title": "Growth of $1, January 2000–August 2026", "type": "line", "dataset": "wealth", "sourceId": "dataset_wealth",
         "encodings": {"x": {"field": "month", "type": "ordinal", "label": "Month"}, "y": {"field": "growth", "type": "quantitative", "label": "Growth of $1"},
                       "color": {"field": "series", "type": "nominal", "label": "Series"}}},
        {"id": "annual_active", "title": "Yearly return gap versus market (2026 through August)", "type": "bar", "dataset": "annual_active", "sourceId": "dataset_annual_active",
         "encodings": {"x": {"field": "year", "type": "ordinal", "label": "Year"}, "y": {"field": "active_gap", "type": "quantitative", "label": "Portfolio minus market", "format": "percent"}},
         "valueFormat": "percent"},
        {"id": "drawdown", "title": "Monthly peak-to-trough drawdown", "type": "line", "dataset": "drawdown", "sourceId": "dataset_drawdown",
         "encodings": {"x": {"field": "month", "type": "ordinal", "label": "Month"}, "y": {"field": "drawdown", "type": "quantitative", "label": "Drawdown", "format": "percent"},
                       "color": {"field": "series", "type": "nominal", "label": "Series"}}, "valueFormat": "percent"},
        {"id": "sector_contribution", "title": "Mean monthly gross contribution by industry", "type": "bar", "dataset": "sector_contribution", "sourceId": "dataset_sector_contribution",
         "encodings": {"x": {"field": "industry", "type": "ordinal", "label": "Industry"},
                       "y": {"field": "mean_monthly_contribution", "type": "quantitative", "label": "Mean contribution", "format": "percent"}}, "valueFormat": "percent"},
    ]
    tables = [
        {"id": "periods", "title": "Annualized return by period", "dataset": "periods", "sourceId": "dataset_periods", "defaultSort": {"field": "period", "direction": "asc"},
         "columns": [{"field": "period", "label": "Period", "type": "text"}, {"field": "portfolio_return", "label": "Portfolio", "format": "percent"},
                     {"field": "market_return", "label": "Market", "format": "percent"}, {"field": "return_gap", "label": "Gap", "format": "percent"}]},
        {"id": "factor_models", "title": "Historical return regressions", "dataset": "factor_models", "sourceId": "dataset_factor_models", "defaultSort": {"field": "model", "direction": "asc"},
         "columns": [{"field": "model", "label": "Model", "type": "text"}, {"field": "alpha", "label": "Annual residual", "format": "percent"},
                     {"field": "ci_range", "label": "95% interval", "type": "text"}]},
        {"id": "costs", "title": "Trading-cost sensitivity", "dataset": "costs", "sourceId": "dataset_costs", "defaultSort": {"field": "trading_cost_bps", "direction": "asc"},
         "columns": [{"field": "trading_cost_bps", "label": "Basis points per traded dollar", "format": "number"},
                     {"field": "annualized_return", "label": "Portfolio annual return", "format": "percent"}]},
    ]
    blocks = [
        {"id": "title", "type": "markdown", "body": f"# {title}\n\nA public-data portfolio analyst case study · January 2000–August 2026 · Prepared October 2026"},
        {"id": "executive", "type": "markdown", "body": "## Executive Summary\n\n"
         f"- **The long-run result is positive but modest.** A hypothetical 10% allocation to each of ten U.S. industry research portfolios, rebalanced monthly, earned **{percent(p['annualized_return'])} a year after modeled trading costs**, versus **{percent(m['annualized_return'])}** for the broad-market research benchmark. The annualized gap was **{main_period['annualized_return_gap_pp']:.2f} percentage points**.\n"
         f"- **The recent result argues against a simple outperform claim.** From 2015 through August 2026, the same rule earned **{percent(recent['portfolio_net']['annualized_return'])}** versus **{percent(recent['market']['annualized_return'])}** for the market. Only **{percent(metrics['rolling_60m']['portfolio_outperformance_share'])}** of overlapping five-year windows beat the market.\n"
         "- **Treat this as a risk and attribution prototype.** The portfolio had slightly lower volatility and a shallower historical drawdown, but its five-factor residual was negative. The source industries are research portfolios, so investable implementation and actual holdings remain to be tested."},
        {"id": "metrics", "type": "metric-strip", "cardIds": ["portfolio_return", "volatility", "drawdown", "recent_gap"]},
        {"id": "definitions", "type": "markdown", "body": "## Mandate and measurement\n\nThe proposed mandate is a simple, transparent equal-industry U.S. equity allocation. At the start of every month, each of ten value-weighted industry research portfolios receives 10% of capital. The market comparison is the Kenneth French U.S. market return (`Mkt-RF + RF`), matched month for month. Portfolio returns include dividends; the simulation applies 10 basis points to every dollar bought or sold at each monthly rebalance, including the initial purchase. Annual returns are geometric; volatility and tracking error annualize monthly standard deviations with √12. Sharpe uses the same monthly risk-free return as the factor file. Drawdowns use monthly closes."},
        {"id": "long_run", "type": "markdown", "body": "## The full-period advantage is concentrated in a long history\n\n"
         f"Compounded from $1 at the start of 2000, the net portfolio reached **${p['total_growth_of_one']:.2f}** by August 2026 versus **${m['total_growth_of_one']:.2f}** for the market. This is a real historical difference for the stated research series, but its size is sensitive to the window: 2000 began just before the technology bust. The chart shows a simulation, not a client account."},
        {"id": "wealth_chart", "type": "chart", "chartId": "wealth", "layout": "full"},
        {"id": "recent", "type": "markdown", "body": "## Recent market leadership reverses the ranking\n\n"
         f"The portfolio lagged by **{abs(recent['annualized_return_gap_pp']):.2f} percentage points a year** from 2015 to August 2026. Calendar years also show that active results were uneven: the return gap was **+13.1 points in 2000** and **−8.0 points in 2023**. Overlapping five-year windows beat the market **{percent(metrics['rolling_60m']['portfolio_outperformance_share'])}** of the time; the worst five-year cumulative gap was **{metrics['rolling_60m']['worst_relative_gap_pp']:.1f} points**. Period selection can therefore change the headline."},
        {"id": "period_table", "type": "table", "tableId": "periods", "layout": "full"},
        {"id": "annual_chart", "type": "chart", "chartId": "annual_active", "layout": "full"},
        {"id": "risk", "type": "markdown", "body": "## Diversification softened losses, but did not prevent a crisis drawdown\n\n"
         f"The portfolio's annualized volatility was **{percent(p['annualized_volatility'])}**, versus **{percent(m['annualized_volatility'])}** for the market. Both reached their deepest monthly drawdown in February 2009: **{percent(p['max_drawdown'])}** for the portfolio and **{percent(m['max_drawdown'])}** for the market. The portfolio's market beta was **{p['market_beta']:.2f}** and tracking error **{percent(p['tracking_error'])}**. This is still predominantly equity risk, with a meaningful possibility of large losses."},
        {"id": "drawdown_chart", "type": "chart", "chartId": "drawdown", "layout": "full"},
        {"id": "macro", "type": "markdown", "body": "## Macro checks add context, not a timing rule\n\n"
         f"After adjusting the full-period ending wealth by the change in the U.S. consumer price index, the portfolio's $1 start was worth **${metrics['inflation']['portfolio_real_growth']:.2f}** in December 1999 purchasing power versus **${metrics['inflation']['market_real_growth']:.2f}** for the market. Across **{metrics['recession']['recession_months']} NBER-based recession months** in the analysis window, average portfolio-minus-market return was only **{100 * metrics['recession']['recession_mean_monthly_active']:.2f} percentage points per month**, close to **{100 * metrics['recession']['expansion_mean_monthly_active']:.2f} points** in expansions. This small, retrospective comparison does not support a recession-timing claim. The missing October 2025 CPI value prevents a complete monthly real-return series, so the inflation comparison uses only the start and end index levels."},
        {"id": "factors", "type": "markdown", "body": "## Factor exposures account for much of the apparent alpha\n\n"
         f"A market-only monthly regression estimates an approximately **+{percent(metrics['factor_models']['market_only']['annualized_alpha_approx'])} annual residual**; a five-factor regression estimates **{percent(metrics['factor_models']['five_factor']['annualized_alpha_approx'])}**. The five-factor fit rises from **{percent(metrics['factor_models']['market_only']['r_squared'])}** to **{percent(metrics['factor_models']['five_factor']['r_squared'])}**. Its positive historical profitability, investment, and value loadings suggest that style exposures explain some of the market-relative difference. Six-lag robust 95% intervals include zero for both residuals; these models do not establish persistent or forward-looking alpha."},
        {"id": "factor_table", "type": "table", "tableId": "factor_models", "layout": "full"},
        {"id": "sector", "type": "markdown", "body": "## Industry contribution was broad, with different risk profiles\n\n"
         "Every industry made a positive average gross contribution over the full window under fixed 10% monthly starting weights. Durable goods contributed the most on average, but also had the highest standalone volatility (33.0% annualized). Telecommunications contributed the least. This is arithmetic contribution to the simulated portfolio's monthly return; without benchmark industry weights, it is not Brinson allocation or selection attribution."},
        {"id": "sector_chart", "type": "chart", "chartId": "sector_contribution", "layout": "full"},
        {"id": "implementation", "type": "markdown", "body": "## Implementation economics need an investable test\n\n"
         f"The simulated strategy's average annual one-way rebalance turnover was **{percent(metrics['cost']['mean_annual_one_way_turnover'])}**. At 10 basis points per traded dollar, modeled trading reduced annualized return by about **{metrics['cost']['annualized_drag_pp']:.2f} percentage points**. Even a 100 basis point sensitivity leaves this research-series return above the benchmark for the full period, but that exercise does not capture fund expense ratios, taxes, market impact, or the cost of replicating the underlying research portfolios. The benchmark is also shown without an implementation fee."},
        {"id": "cost_table", "type": "table", "tableId": "costs", "layout": "full"},
        {"id": "next", "type": "markdown", "body": "## Recommended next steps\n\n1. Rebuild the same allocation with an investable, historically available set of sector funds, incorporating distributions, expense ratios, and fund inception dates. Compare it with an investable broad-market fund on the same dates.\n2. Add a holdings-based attribution exercise using actual disclosed positions or a public fund holdings file. Keep holdings dates and publication lags explicit; do not infer trades from successive snapshots.\n3. Reassess the mandate against a risk budget, especially maximum drawdown, tracking error, and concentration; then examine rolling five-year performance before deciding whether the allocation adds value."},
        {"id": "questions", "type": "markdown", "body": "## Further questions\n\nWould an annual rebalance retain the diversification benefit with less trading? How much of the recent lag comes from persistent sector weight differences versus within-industry returns? Would a client prefer a lower beta and drawdown profile even if recent market-relative returns remain weaker? Each question requires an explicit mandate and investable proxy before answering."},
        {"id": "caveats", "type": "markdown", "body": "## Caveats and sources\n\n"
         "**Research series.** [Kenneth French's Data Library](https://mba.tuck.dartmouth.edu/pages/faculty/ken.french/data_library.html) supplies the 10 value-weighted industry returns and five factors. The [industry methodology](https://mba.tuck.dartmouth.edu/pages/faculty/ken.french/data_library/det_10_ind_port.html) resets SIC-based membership each June. These are constructed portfolios, not fund NAVs or actual holdings. Source histories may be revised, and the library changed its CRSP return process in January 2025. The source URLs and ZIP SHA-256 hashes in `analysis/provenance/source_manifest.json` identify this vintage.\n\n"
         "**Macro context.** [FRED USREC](https://fred.stlouisfed.org/series/USREC) and [FRED CPIAUCSL](https://fred.stlouisfed.org/series/CPIAUCSL) were downloaded for regime and inflation checks. The CPI feed has no October 2025 observation, so no monthly inflation value was imputed. Endpoint CPI levels can still support a full-window purchasing-power comparison. Recession months are descriptive context and were not used to pick weights.\n\n"
         "**Modeling limits.** Weights were fixed at 10% each, not optimized. Rebalance costs are assumed, not observed. Tax, financing, fund fees, spreads inside the research portfolios, and cash drag are excluded. The factor regressions do not establish persistent alpha. This report is a historical analytical case study, not personalized investment advice."},
    ]
    artifact = {"surface": "report", "manifest": {"version": 1, "surface": "report", "title": title,
                "description": "Public-data portfolio analyst case study with performance, risk, factor, and cost analysis.",
                "generatedAt": generated, "cards": cards, "charts": charts, "tables": tables, "sources": sources, "blocks": blocks},
                "snapshot": {"version": 1, "generatedAt": generated, "status": "ready", "datasets": datasets},
                "sources": sources}
    (OUT / "artifact.json").write_text(json.dumps(artifact, ensure_ascii=False, indent=2, allow_nan=False) + "\n", encoding="utf-8")
    print(OUT / "artifact.json")


if __name__ == "__main__":
    main()
