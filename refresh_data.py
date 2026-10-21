"""Download and prepare monthly portfolio research data from Kenneth French."""

import csv
import hashlib
import io
import json
import re
import urllib.request
import zipfile
from datetime import datetime, timezone
from pathlib import Path


ROOT = Path(__file__).resolve().parent
RAW = ROOT / "data" / "raw"
PROCESSED = ROOT / "data" / "processed"
SOURCES = {
    "industries": "https://mba.tuck.dartmouth.edu/pages/faculty/ken.french/ftp/10_Industry_Portfolios_CSV.zip",
    "factors": "https://mba.tuck.dartmouth.edu/pages/faculty/ken.french/ftp/F-F_Research_Data_5_Factors_2x3_CSV.zip",
}


def monthly_table(archive: bytes, expected_header: list[str], section: str | None = None):
    with zipfile.ZipFile(io.BytesIO(archive)) as bundle:
        lines = bundle.read(bundle.namelist()[0]).decode("latin-1").splitlines()
    start = 0
    if section:
        start = next(i for i, line in enumerate(lines) if line.strip() == section) + 1
    header = next(i for i in range(start, len(lines)) if [v.strip() for v in next(csv.reader([lines[i]]))] == expected_header)
    rows = {}
    for line in lines[header + 1 :]:
        fields = [v.strip() for v in next(csv.reader([line]))]
        if not fields or not re.fullmatch(r"\d{6}", fields[0]):
            break
        if len(fields) != len(expected_header):
            raise ValueError(f"Unexpected column count: {line}")
        month = fields[0]
        datetime.strptime(month, "%Y%m")
        if month in rows:
            raise ValueError(f"Duplicate month: {month}")
        values = [float(v) for v in fields[1:]]
        if any(v in (-99.99, -999.0) for v in values):
            raise ValueError(f"Missing-value sentinel in {month}")
        rows[month] = values
    if not rows:
        raise ValueError("No monthly records found")
    return rows


def write_csv(path: Path, header: list[str], rows: list[list]):
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.writer(handle)
        writer.writerow(header)
        writer.writerows(rows)


def main():
    RAW.mkdir(parents=True, exist_ok=True)
    PROCESSED.mkdir(parents=True, exist_ok=True)
    archives = {}
    manifest = {"downloaded_at_utc": datetime.now(timezone.utc).isoformat(), "sources": {}}
    for name, url in SOURCES.items():
        request = urllib.request.Request(url, headers={"User-Agent": "PortfolioAnalysisResearch/1.0"})
        with urllib.request.urlopen(request, timeout=45) as response:
            archive = response.read()
        with zipfile.ZipFile(io.BytesIO(archive)) as bundle:
            if bundle.testzip() is not None:
                raise ValueError(f"Corrupt ZIP: {name}")
        (RAW / f"{name}.zip").write_bytes(archive)
        archives[name] = archive
        manifest["sources"][name] = {"url": url, "sha256": hashlib.sha256(archive).hexdigest()}

    sectors = ["NoDur", "Durbl", "Manuf", "Enrgy", "HiTec", "Telcm", "Shops", "Hlth", "Utils", "Other"]
    industry = monthly_table(archives["industries"], [""] + sectors, "Average Value Weighted Returns -- Monthly")
    factors = monthly_table(archives["factors"], ["", "Mkt-RF", "SMB", "HML", "RMW", "CMA", "RF"])
    months = sorted(set(industry) & set(factors))
    if not months or months != sorted(industry)[-len(months):] or months != sorted(factors)[-len(months):]:
        raise ValueError("Monthly source coverage is not aligned")
    if any(int(months[i][:4]) * 12 + int(months[i][4:]) != int(months[i-1][:4]) * 12 + int(months[i-1][4:]) + 1 for i in range(1, len(months))):
        raise ValueError("Gap in monthly coverage")

    industry_rows = [[f"{m[:4]}-{m[4:]}-01", sector, industry[m][i] / 100]
                     for m in months for i, sector in enumerate(sectors)]
    factor_rows = [[f"{m[:4]}-{m[4:]}-01", *(v / 100 for v in factors[m]),
                    (factors[m][0] + factors[m][5]) / 100] for m in months]
    write_csv(PROCESSED / "industry_monthly_returns.csv", ["month", "industry", "total_return"], industry_rows)
    write_csv(PROCESSED / "market_factors_monthly.csv",
              ["month", "market_excess_return", "smb", "hml", "rmw", "cma", "risk_free_return", "market_total_return"], factor_rows)
    manifest["coverage"] = {"first_month": months[0], "last_month": months[-1],
                            "months": len(months), "industry_rows": len(industry_rows)}
    (RAW / "source_manifest.json").write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
    provenance = ROOT / "analysis" / "provenance"
    provenance.mkdir(parents=True, exist_ok=True)
    (provenance / "source_manifest.json").write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(manifest["coverage"], indent=2))


if __name__ == "__main__":
    main()
