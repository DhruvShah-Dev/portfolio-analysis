# Validation record

As of October 20, 2026, the analysis uses the Kenneth French August 2026 data cut and FRED downloads saved under `../data/raw/`.

- `python ../validate.py` passed: unique industry-month grain; 320 matched months from January 2000 through August 2026; ten industries per month; equal-weight return arithmetic; market return equals `Mkt-RF + RF`; portfolio and market compounding, drawdowns, and 2015-to-latest annualized returns independently recomputed; October 2025 CPI missingness confirmed.
- The source download manifests in `provenance/` retain URL and SHA-256 for both Kenneth French ZIPs and the FRED CSVs. Original source data is downloaded locally and excluded from the public repository.
- The canonical `artifact.json` passed the Data Analytics portable report schema and exact-payload structural verifier. The self-contained `report.html` includes four extracted SVG chart fallbacks, four rendered charts, and three tables.
- The HTML was opened in Chromium at 1440px and 390px. Its enhanced reader reached `ready` at both sizes; chart and table counts matched the artifact; neither standalone viewport had horizontal overflow.
- The package tool's combined browser harness was intermittent, reporting reader timeout or an 8px iframe overflow. The final HTML was built through the same validated builder and chart extractor, then checked with the structural verifier and direct standalone browser inspection. This is a tooling verification limit, not a failed data check.

The return series are constructed research portfolios. The report's 10% weights, monthly rebalancing, and transaction costs are modeled assumptions. No manager holdings, fund fees, tax effects, or investable sector replication were verified. The benchmark is the Kenneth French broad U.S. market research return, not the S&P 500.
