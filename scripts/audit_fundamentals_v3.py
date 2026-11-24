"""BatDayStox SSI -- audit locally exported financial-statement CSVs.

Read-only with respect to originals; produces review files, NOT valuation scores.
No API calls, secrets, or assumptions about financial report publication dates.
"""
from __future__ import annotations

import argparse
import re
import unicodedata
from pathlib import Path

import pandas as pd

BASE = Path(__file__).resolve().parent
STMT_TYPES = ("balance_sheet", "income_statement", "cash_flow")
ALL_TYPES = (*STMT_TYPES, "ratios")

# Conservative aliases: these identify possible accounting lines for human review,
# not proven standardized fields. Bank/financial firm templates differ.
ALIASES = {
    "total_assets": ("tong tai san",),
    "equity": ("von chu so huu", "tong von chu so huu"),
    "liabilities": ("no phai tra", "tong no phai tra"),
    "profit_before_tax": ("loi nhuan truoc thue", "loi nhuan ke toan truoc thue"),
    "profit_after_tax": ("loi nhuan sau thue", "loi nhuan ke toan sau thue"),
    "income_tax_expense": ("chi phi thue thu nhap doanh nghiep",),
    "current_tax_expense": ("chi phi thue thu nhap hien hanh",),
    "deferred_tax_expense": ("chi phi thue thu nhap hoan lai",),
    "revenue": ("doanh thu thuan", "doanh thu thuan ve hoat dong kinh doanh", "doanh thu hoat dong"),
    "gross_profit": ("loi nhuan gop",),
    "eps": ("lai co ban tren co phieu", "thu nhap tren co phieu"),
    "roe": ("roe", "ty suat loi nhuan tren von chu so huu"),
    "roa": ("roa", "ty suat loi nhuan tren tong tai san"),
    "pe": ("p/e", "pe"),
    "pb": ("p/b", "pb"),
}


def normalize(label: object) -> str:
    x = unicodedata.normalize("NFKD", str(label).strip().lower())
    x = "".join(c for c in x if not unicodedata.combining(c))
    x = x.replace("đ", "d")
    x = re.sub(r"[^a-z0-9/%]+", " ", x).strip()
    return re.sub(r"\s+", " ", x)


NORMALIZED_ALIASES = {key: [normalize(v) for v in values] for key, values in ALIASES.items()}


def match_metric(label: object):
    norm = normalize(label)
    matches = []
    for metric, aliases in NORMALIZED_ALIASES.items():
        if norm in aliases:
            matches.append((metric, "exact"))
        elif len(norm) > 8 and any(norm.startswith(a + " ") or norm.endswith(" " + a) for a in aliases if len(a) > 8):
            matches.append((metric, "review"))
    return matches


def as_number(value):
    if pd.isna(value):
        return None
    # Do not guess locale or silently reinterpret comma/period in financial values.
    try:
        result = float(str(value).strip())
    except (ValueError, TypeError, OverflowError):
        return None
    if not (-float("inf") < result < float("inf")):
        return None
    return result


def year_fields(df):
    return [c for c in df.columns if re.fullmatch(r"(?:19|20)\d{2}(?:\.0)?", str(c).strip())]


def _single_exact(candidates: pd.DataFrame, symbol: str, year: int, metric: str, statement=None):
    if candidates.empty:
        return None
    mask = (
        (candidates["symbol"] == symbol)
        & (candidates["year"] == year)
        & (candidates["metric"] == metric)
        & (candidates["match"] == "exact")
    )
    if statement is not None:
        mask &= candidates["statement"].eq(statement)
    found = candidates.loc[mask]
    if len(found) == 1 and pd.notna(found.iloc[0]["value"]):
        return float(found.iloc[0]["value"])
    return None  # Missing/ambiguous values must not be used for automatic math.


def audit(staging: Path, output: Path):
    staging, output = Path(staging), Path(output)
    if not staging.exists():
        raise FileNotFoundError(f"Không thấy thư mục staging: {staging}")
    files = sorted(staging.glob("*.csv"))
    inventory, candidates, flags, ratio_examples = [], [], [], []
    symbols = set()

    for path in files:
        match = re.fullmatch(r"([A-Za-z0-9]+)_(balance_sheet|income_statement|cash_flow|ratios)\.csv", path.name)
        if match is None:
            continue
        symbol, stype = match.group(1).upper(), match.group(2)
        symbols.add(symbol)
        df = pd.read_csv(path, encoding="utf-8-sig", low_memory=False)
        if df.empty:
            flags.append({"symbol": symbol, "year": "", "severity": "WARN", "test": "empty_file", "details": path.name})
            continue
        first = df.columns[0]
        years = year_fields(df)
        inventory.append({
            "symbol": symbol, "file": path.name, "type": stype,
            "rows": len(df), "columns": len(df.columns), "label_column": str(first),
            "years": ",".join(str(y) for y in years), "year_column_count": len(years)
        })
        if stype == "ratios":
            # Layout differs by source; provide a small sample without guessing units.
            for _, row in df.head(8).iterrows():
                ratio_examples.append({"symbol": symbol, "source_file": path.name,
                                       "sample": " | ".join(f"{col}={str(row[col])[:70]}" for col in df.columns[:5])})
        if not years:
            flags.append({"symbol": symbol, "year": "", "severity": "REVIEW", "test": "year_schema_unknown",
                          "details": f"{path.name}: không tìm thấy cột năm dạng 2023/2024/2025"})
            continue
        for row_number, row in df.iterrows():
            label = str(row[first]).strip()
            matches = match_metric(label)
            if not matches:
                continue
            for col in years:
                year = int(float(str(col)))
                value = as_number(row[col])
                for metric, strength in matches:
                    candidates.append({"symbol": symbol, "statement": stype, "year": year,
                                       "metric": metric, "match": strength,
                                       "row": row_number + 2, "label": label, "value": value,
                                       "source_file": path.name})

    cdf = pd.DataFrame(candidates, columns=["symbol", "statement", "year", "metric", "match", "row", "label", "value", "source_file"])
    for sym in sorted(symbols):
        seen = {rec["type"] for rec in inventory if rec["symbol"] == sym}
        for kind in ALL_TYPES:
            if kind not in seen:
                flags.append({"symbol": sym, "year": "", "severity": "WARN",
                              "test": "missing_input", "details": f"Thiếu {sym}_{kind}.csv"})
        years = sorted(cdf.loc[cdf["symbol"] == sym, "year"].dropna().unique()) if not cdf.empty else []
        for year in years:
            year = int(year)
            # Duplicates of strict aliases must be reviewed, not arbitrarily selected.
            exact = cdf.loc[(cdf["symbol"] == sym) & (cdf["year"] == year) & (cdf["match"] == "exact")]
            for (typ, metric), sub in exact.groupby(["statement", "metric"]):
                if len(sub) > 1:
                    flags.append({"symbol": sym, "year": year, "severity": "REVIEW", "test": "ambiguous_metric",
                                  "details": f"{typ}/{metric} khớp {len(sub)} dòng; cần đối chiếu mã chỉ tiêu"})
            pretax_cash = _single_exact(cdf, sym, year, "profit_before_tax", "cash_flow")
            tax_is = _single_exact(cdf, sym, year, "income_tax_expense", "income_statement")
            if pretax_cash is not None and tax_is is not None and abs(pretax_cash) > 0:
                if abs(tax_is - pretax_cash) <= 1e-7 * max(abs(pretax_cash), 1.0):
                    flags.append({"symbol": sym, "year": year, "severity": "CRITICAL_REVIEW",
                                  "test": "tax_equals_pretax",
                                  "details": "Dòng nhãn chi phí thuế KQKD trùng lợi nhuận trước thuế trong LCTT; KHÔNG dùng làm chi phí thuế trước khi xác minh"})
            a = _single_exact(cdf, sym, year, "total_assets", "balance_sheet")
            l = _single_exact(cdf, sym, year, "liabilities", "balance_sheet")
            e = _single_exact(cdf, sym, year, "equity", "balance_sheet")
            if all(v is not None for v in [a, l, e]) and abs(a) > 0:
                residual = (a - l - e) / abs(a)
                if abs(residual) > 0.005:
                    flags.append({"symbol": sym, "year": year, "severity": "REVIEW",
                                  "test": "balance_sheet_identity",
                                  "details": f"|Tổng tài sản - nợ - VCSH|/tài sản = {abs(residual):.2%}"})

    output.mkdir(parents=True, exist_ok=True)
    paths = {
        "inventory": output / "financial_inventory.csv",
        "candidates": output / "financial_line_candidates.csv",
        "flags": output / "financial_review_flags.csv",
        "ratios": output / "ratio_schema_examples.csv",
    }
    pd.DataFrame(inventory, columns=["symbol", "file", "type", "rows", "columns", "label_column", "years", "year_column_count"]).to_csv(paths["inventory"], index=False, encoding="utf-8-sig")
    cdf.to_csv(paths["candidates"], index=False, encoding="utf-8-sig")
    pd.DataFrame(flags, columns=["symbol", "year", "severity", "test", "details"]).to_csv(paths["flags"], index=False, encoding="utf-8-sig")
    pd.DataFrame(ratio_examples, columns=["symbol", "source_file", "sample"]).to_csv(paths["ratios"], index=False, encoding="utf-8-sig")
    return {"files": len(inventory), "symbols": sorted(symbols), "candidate_rows": len(cdf),
            "flags": flags, "outputs": paths}


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--staging", type=Path, default=BASE / "data" / "fundamentals" / "staging")
    parser.add_argument("--out", type=Path, default=BASE / "data" / "fundamentals" / "audit")
    args = parser.parse_args()
    result = audit(args.staging, args.out)
    print("=== BATDAYSTOX - AUDIT BCTC V3 ===")
    print("Số mã:", len(result["symbols"]), "|", ", ".join(result["symbols"]))
    print("Số file hợp lệ:", result["files"])
    print("Số dòng ứng viên chỉ tiêu:", result["candidate_rows"])
    print("Cờ cần rà soát:", len(result["flags"]))
    for flag in result["flags"][:20]:
        print(" -", flag["symbol"], flag["year"], flag["severity"], flag["test"])
    print("\nFile kết quả:")
    for path in result["outputs"].values():
        print(" -", path)
    print("\nChưa tạo điểm Smart Rating; báo cáo năm chưa có ngày công bố xác minh.")


if __name__ == "__main__":
    main()
