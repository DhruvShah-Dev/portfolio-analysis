"""Reproducible, public-data U.S. industry allocation case study."""

import csv
import hashlib
import json
import math
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
import pandas as pd


ROOT = Path(__file__).resolve().parent
PROCESSED = ROOT / "data" / "processed"
RAW = ROOT / "data" / "raw"
OUT = ROOT / "analysis"
START = "2000-01-01"
COST_PER_TRADED_NOTIONAL = 0.001  # 10 basis points on each buy/sell dollar


def fred_series(series):
    url = f"https://fred.stlouisfed.org/graph/fredgraph.csv?id={series}"
    request = urllib.request.Request(url, headers={"User-Agent": "PortfolioAnalysisResearch/1.0"})
    with urllib.request.urlopen(request, timeout=45) as response:
        payload = response.read()
    (RAW / f"fred_{series.lower()}.csv").write_bytes(payload)
    frame = pd.read_csv(RAW / f"fred_{series.lower()}.csv", parse_dates=["observation_date"])
    frame = frame.rename(columns={"observation_date": "month", series: series.lower()}).set_index("month")
    frame.index = frame.index.to_period("M").to_timestamp()
    frame[series.lower()] = pd.to_numeric(frame[series.lower()], errors="coerce")
    return frame


def annualized_return(r):
    return float(np.prod(1 + r) ** (12 / len(r)) - 1)


def max_drawdown(r):
    wealth = np.r_[1.0, np.cumprod(1 + np.asarray(r))]
    return float(np.min(wealth / np.maximum.accumulate(wealth) - 1))


def metrics(frame, column):
    r = frame[column].to_numpy(dtype=float)
    benchmark = frame["market_total_return"].to_numpy(dtype=float)
    excess = r - frame["risk_free_return"].to_numpy(dtype=float)
    active = r - benchmark
    vol = float(np.std(r, ddof=1) * np.sqrt(12))
    te = float(np.std(active, ddof=1) * np.sqrt(12))
    market_excess = benchmark - frame["risk_free_return"].to_numpy(dtype=float)
    beta = float(np.cov(excess, market_excess, ddof=1)[0, 1] / np.var(market_excess, ddof=1))
    return {
        "annualized_return": annualized_return(r),
        "annualized_volatility": vol,
        "sharpe": float(np.mean(excess) * 12 / vol),
        "max_drawdown": max_drawdown(r),
        "tracking_error": te,
        "information_ratio": float(np.mean(active) * 12 / te) if te else None,
        "market_beta": beta,
        "positive_month_share": float(np.mean(r > 0)),
        "positive_active_month_share": float(np.mean(active > 0)),
        "total_growth_of_one": float(np.prod(1 + r)),
    }


def regression(y, x):
    design = np.column_stack([np.ones(len(y)), x])
    coef = np.linalg.lstsq(design, y, rcond=None)[0]
    residual = y - design @ coef
    r2 = 1 - float(np.sum(residual**2) / np.sum((y - np.mean(y))**2))
    # Newey-West sandwich covariance with six monthly lags; descriptive uncertainty only.
    weighted = design * residual[:, None]
    meat = weighted.T @ weighted
    for lag in range(1, 7):
        lag_product = weighted[lag:].T @ weighted[:-lag]
        meat += (1 - lag / 7) * (lag_product + lag_product.T)
    bread = np.linalg.inv(design.T @ design)
    standard_error = float(np.sqrt(max((bread @ meat @ bread)[0, 0], 0)))
    return {"monthly_alpha": float(coef[0]), "annualized_alpha_approx": float(coef[0] * 12),
            "annualized_alpha_95ci_approx": [float((coef[0] - 1.96 * standard_error) * 12),
                                             float((coef[0] + 1.96 * standard_error) * 12)],
            "hac_lags": 6, "betas": [float(v) for v in coef[1:]], "r_squared": r2}


def main():
    OUT.mkdir(exist_ok=True)
    sectors = pd.read_csv(PROCESSED / "industry_monthly_returns.csv", parse_dates=["month"])
    factors = pd.read_csv(PROCESSED / "market_factors_monthly.csv", parse_dates=["month"]).set_index("month")
    wide = sectors.pivot(index="month", columns="industry", values="total_return").sort_index()
    frame = factors.join(wide, how="inner")
    frame = frame.loc[START:]
    if frame.isna().any().any() or len(frame) < 120 or frame.index.has_duplicates:
        raise ValueError("Incomplete or duplicated analysis panel")
    if frame.index[-1] > pd.Timestamp.today().to_period("M").to_timestamp():
        raise ValueError("Source contains future month")
    industry_names = list(wide.columns)
    gross = frame[industry_names].mean(axis=1)
    net = []
    turnover = []
    prior_returns = None
    for date, row in frame[industry_names].iterrows():
        if prior_returns is None:
            traded = 1.0  # initial purchase from cash
        else:
            ending_weights = (0.1 * (1 + prior_returns)) / (1 + float(np.mean(prior_returns)))
            traded = float(np.abs(0.1 - ending_weights).sum())
        cost = COST_PER_TRADED_NOTIONAL * traded
        net.append((1 - cost) * (1 + gross.loc[date]) - 1)
        turnover.append(traded / 2 if prior_returns is not None else 1.0)
        prior_returns = row.to_numpy(dtype=float)
    frame["equal_industry_gross"] = gross
    frame["equal_industry_net"] = net
    frame["one_way_turnover"] = turnover
    frame["active_net"] = frame["equal_industry_net"] - frame["market_total_return"]
    frame["portfolio_wealth"] = (1 + frame["equal_industry_net"]).cumprod()
    frame["market_wealth"] = (1 + frame["market_total_return"]).cumprod()
    frame["portfolio_drawdown"] = frame["portfolio_wealth"] / frame["portfolio_wealth"].cummax().clip(lower=1) - 1
    frame["market_drawdown"] = frame["market_wealth"] / frame["market_wealth"].cummax().clip(lower=1) - 1
    frame["rolling_60m_portfolio_return"] = (1 + frame["equal_industry_net"]).rolling(60).apply(np.prod, raw=True) - 1
    frame["rolling_60m_market_return"] = (1 + frame["market_total_return"]).rolling(60).apply(np.prod, raw=True) - 1

    recession = fred_series("USREC")
    cpi = fred_series("CPIAUCSL")
    frame = frame.join(recession).join(cpi)
    frame["inflation_monthly"] = frame["cpiaucsl"].pct_change(fill_method=None)
    if frame["usrec"].isna().any() or pd.isna(frame["cpiaucsl"].iloc[-1]):
        raise ValueError("Required FRED macro coverage incomplete")

    periods = {"main_2000_to_latest": frame, "recent_2015_to_latest": frame.loc["2015":],
               "pre_2020": frame.loc[:"2019"], "since_2020": frame.loc["2020":]}
    summary = {name: {"months": len(part), "start": str(part.index[0].date()), "end": str(part.index[-1].date()),
                      "portfolio_net": metrics(part, "equal_industry_net"),
                      "portfolio_gross": metrics(part, "equal_industry_gross"),
                      "market": metrics(part, "market_total_return"),
                      "annualized_return_gap_pp": 100 * (annualized_return(part["equal_industry_net"]) - annualized_return(part["market_total_return"]))}
               for name, part in periods.items()}
    main = frame
    rolling = main.dropna(subset=["rolling_60m_portfolio_return", "rolling_60m_market_return"])
    summary["rolling_60m"] = {"windows": len(rolling),
                              "portfolio_outperformance_share": float((rolling["rolling_60m_portfolio_return"] > rolling["rolling_60m_market_return"]).mean()),
                              "worst_relative_gap_pp": float(100 * (rolling["rolling_60m_portfolio_return"] - rolling["rolling_60m_market_return"]).min())}
    summary["recession"] = {"recession_months": int((main.usrec == 1).sum()),
                            "expansion_months": int((main.usrec == 0).sum()),
                            "recession_mean_monthly_active": float(main.loc[main.usrec == 1, "active_net"].mean()),
                            "expansion_mean_monthly_active": float(main.loc[main.usrec == 0, "active_net"].mean())}
    summary["cost"] = {"assumed_cost_per_traded_notional": COST_PER_TRADED_NOTIONAL,
                       "annualized_drag_pp": 100 * (annualized_return(main["equal_industry_gross"]) - annualized_return(main["equal_industry_net"])),
                       "mean_annual_one_way_turnover": float(main["one_way_turnover"].iloc[1:].mean() * 12),
                       "cost_sensitivity": {str(bps): annualized_return((1 - (bps / 10000) * np.where(np.arange(len(main)) == 0, 1.0, 2 * main["one_way_turnover"].to_numpy())) * (1 + main["equal_industry_gross"].to_numpy()) - 1)
                                            for bps in [0, 10, 50, 100]}}
    cpi_base = float(cpi.loc[pd.Timestamp(START) - pd.offsets.MonthBegin(), "cpiaucsl"])
    inflation_factor = float(main.cpiaucsl.iloc[-1]) / cpi_base
    summary["inflation"] = {"cpi_base_previous_month": cpi_base, "cpi_last": float(main.cpiaucsl.iloc[-1]),
                            "missing_cpi_months": [str(x.date()) for x in main.index[main.cpiaucsl.isna()]],
                            "portfolio_real_growth": float(main.portfolio_wealth.iloc[-1] / inflation_factor),
                            "market_real_growth": float(main.market_wealth.iloc[-1] / inflation_factor)}
    y = main["equal_industry_net"].to_numpy() - main["risk_free_return"].to_numpy()
    summary["factor_models"] = {
        "market_only": regression(y, main[["market_excess_return"]].to_numpy()),
        "five_factor": regression(y, main[["market_excess_return", "smb", "hml", "rmw", "cma"]].to_numpy())}
    summary["sector_mean_monthly_contribution"] = {sector: float(main[sector].mean() / 10) for sector in industry_names}
    summary["sector_annualized_volatility"] = {sector: float(main[sector].std(ddof=1) * math.sqrt(12)) for sector in industry_names}
    annual = (1 + main[["equal_industry_net", "market_total_return"]]).groupby(main.index.year).prod() - 1
    annual["active_gap"] = annual["equal_industry_net"] - annual["market_total_return"]
    annual.to_csv(OUT / "annual_returns.csv", index_label="year")
    main.reset_index().to_csv(OUT / "monthly_analysis.csv", index=False)
    (OUT / "metrics.json").write_text(json.dumps(summary, indent=2) + "\n", encoding="utf-8")
    macro_manifest = {"downloaded_at_utc": datetime.now(timezone.utc).isoformat(), "series": {}}
    for code in ["USREC", "CPIAUCSL"]:
        payload = (RAW / f"fred_{code.lower()}.csv").read_bytes()
        macro_manifest["series"][code] = {"source_url": f"https://fred.stlouisfed.org/series/{code}",
                                          "csv_url": f"https://fred.stlouisfed.org/graph/fredgraph.csv?id={code}",
                                          "sha256": hashlib.sha256(payload).hexdigest()}
    (RAW / "macro_source_manifest.json").write_text(json.dumps(macro_manifest, indent=2) + "\n", encoding="utf-8")
    provenance = OUT / "provenance"
    provenance.mkdir(exist_ok=True)
    (provenance / "macro_source_manifest.json").write_text(json.dumps(macro_manifest, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"coverage": [summary["main_2000_to_latest"]["start"], summary["main_2000_to_latest"]["end"]],
                      "portfolio_return": summary["main_2000_to_latest"]["portfolio_net"]["annualized_return"],
                      "market_return": summary["main_2000_to_latest"]["market"]["annualized_return"],
                      "portfolio_drawdown": summary["main_2000_to_latest"]["portfolio_net"]["max_drawdown"]}, indent=2))


if __name__ == "__main__":
    main()
