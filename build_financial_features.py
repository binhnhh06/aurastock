"""BatDayStox SSI: build PRELIMINARY annual financial features from BCTC CSV.

Reads only: data/fundamentals/staging/{SYMBOL}_{statement}.csv (2021-25 if available).
Writes only: data/fundamentals/processed/financial_features_annual.csv
             data/fundamentals/processed/financial_feature_coverage.csv
No online fetch, valuation, investment scores or changes to core/ / app.py.
Important: NO report publication date has been verified, so score_eligible=NO.
Annual income and balance aliases updated from 18 real CSVs (Nov 2026).
"""
from __future__ import annotations

import argparse
import os
import re
import tempfile
import unicodedata
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parent
SYMBOLS = (
    "ACB BID BSR CTG FPT GAS GVR HDB HPG LPB MBB MCH MSN MWG SAB "
    "SHB SSB SSI STB TCB TCX VCB VHM VIB VIC VJC VNM VPB VPL VRE"
).split()
BANKS = set("ACB BID CTG HDB LPB MBB SHB SSB STB TCB VCB VIB VPB".split())
BROKERS = {"SSI", "TCX"}
YEARS = (2021, 2022, 2023, 2024, 2025)
STATEMENTS = ("balance_sheet", "income_statement", "cash_flow")


def catalogue_symbols(root=ROOT):
    """Do not limit financial coverage to original 30 codes."""
    file = Path(root) / "data" / "ssi_cache" / "market_symbols.csv"
    if file.is_file():
        try:
            market = pd.read_csv(file, encoding="utf-8-sig", keep_default_na=False)
            if {"symbol", "asset_class"}.issubset(market.columns):
                return sorted(set(market.loc[market["asset_class"].eq("EQUITY"), "symbol"]
                                  .astype(str).str.upper().str.strip()))
        except (OSError, ValueError, pd.errors.ParserError):
            pass
    # Fallback: at least process every symbol that already has local BCTC.
    staging = Path(root) / "data" / "fundamentals" / "staging"
    found = set()
    for f in staging.glob("*_balance_sheet.csv"):
        found.add(f.name.rsplit("_balance_sheet.csv", 1)[0])
    for suffix in ("_income_statement.csv", "_cash_flow.csv"):
        for f in staging.glob(f"*{suffix}"):
            found.add(f.name[: -len(suffix)])
    return sorted(found or SYMBOLS)


def catalogue_company_groups(root=ROOT):
    """Read SSI industry for all codes; avoid treating banks/insurers like manufacturers."""
    file = Path(root) / "data" / "ssi_cache" / "market_symbols.csv"
    if not file.is_file():
        return {}
    try:
        df = pd.read_csv(file, encoding="utf-8-sig", keep_default_na=False)
        if not {"symbol", "sector"}.issubset(df.columns):
            return {}
        return dict(zip(df["symbol"].astype(str).str.upper().str.strip(), df["sector"].map(norm)))
    except (OSError, ValueError, pd.errors.ParserError):
        return {}


def financial_type(symbol, sectors):
    sector = sectors.get(symbol, "")
    if "ngan hang" in sector or "bank" in sector or symbol in BANKS:
        return "BANK"
    if ("chung khoan" in sector or "bao hiem" in sector or "securities" in sector
            or "insurance" in sector or symbol in BROKERS):
        return "FINANCIAL_OTHER"
    if not sector:
        return "UNKNOWN"
    return "NONFINANCIAL"


# Exact labels only: do not use substring matching when selecting financial values.
ALIASES = {
    "assets": ("tong tai san", "tong cong tai san"),
    "liabilities": ("no phai tra", "tong no phai tra"),
    "equity": ("von chu so huu", "tong von chu so huu"),
    "profit": (
        "loi nhuan sau thue", "loi nhuan ke toan sau thue",
        "loi nhuan sau thue thu nhap doanh nghiep",
        "loi nhuan ke toan sau thue thu nhap doanh nghiep",
        "lai lo thuan sau thue",
    ),
    "eps": ("lai co ban tren co phieu", "thu nhap tren co phieu", "lai co ban tren co phieu vnd"),
    "revenue": (
        "doanh thu thuan", "doanh thu thuan ve hoat dong kinh doanh",
        "doanh thu hoat dong", "doanh thu thuan ve ban hang va cung cap dich vu",
        "doanh so thuan",
    ),
    "gross_profit": ("loi nhuan gop", "loi nhuan gop ve ban hang va cung cap dich vu", "lai gop"),
    "current_assets": ("tai san ngan han", "tong tai san ngan han"),
    "current_liabilities": ("no ngan han", "no phai tra ngan han", "tong no ngan han"),
}
STATEMENT_FOR = {
    "assets": "balance_sheet", "liabilities": "balance_sheet",
    "equity": "balance_sheet", "current_assets": "balance_sheet",
    "current_liabilities": "balance_sheet", "profit": "income_statement",
    "eps": "income_statement", "revenue": "income_statement",
    "gross_profit": "income_statement",
}


def norm(value: object) -> str:
    s = unicodedata.normalize("NFKD", str(value).strip().lower())
    s = "".join(c for c in s if not unicodedata.combining(c)).replace("đ", "d")
    return re.sub(r"\s+", " ", re.sub(r"[^a-z0-9]+", " ", s)).strip()


ALIASES = {key: {norm(a) for a in vals} for key, vals in ALIASES.items()}

# Cross-check labels are not fed into the rating. They identify inconsistent
# statements without confusing an aggregate with a reported line item.
INCOME_CHECK_ALIASES = {
    "pre_tax_profit": {norm(x) for x in ("lai lo rong truoc thue", "lai lo truoc thue")},
    "signed_tax_expense": {norm("chi phi thue thu nhap doanh nghiep")},
    "parent_profit": {norm("loi nhuan cua co dong cua cong ty me")},
    "minority_profit": {norm("loi ich cua co dong thieu so")},
}


def load_statement(path: Path):
    if not path.is_file():
        return None, "MISSING_FILE"
    try:
        df = pd.read_csv(path, encoding="utf-8-sig", low_memory=False)
    except Exception as exc:
        return None, "READ_ERROR:" + type(exc).__name__
    if df.empty or len(df.columns) < 2:
        return None, "EMPTY_OR_INVALID"
    label_col = "item" if "item" in df.columns else df.columns[0]
    df = df.rename(columns={label_col: "item"}).copy()
    df["_key"] = df["item"].map(norm)
    # Stop if headers indicate duplicate year columns after pandas suffixing.
    if any(re.fullmatch(r"20(?:21|22|23|24|25)\.\d+", str(c)) for c in df.columns):
        return None, "DUPLICATE_YEAR_COLUMNS"
    if not any(str(y) in df.columns for y in YEARS):
        return None, "NO_2021_2025_COLUMNS"
    return df, "OK"


def one_value(df, year: int, metric: str):
    """Return (numeric value or NaN, match status, source line label).

    Two exact matches (even numerically identical) are AMBIGUOUS, never averaged.
    """
    if df is None or str(year) not in df.columns:
        return np.nan, "MISSING_YEAR_OR_FILE", ""
    hits = df.loc[df["_key"].isin(ALIASES[metric]), ["item", str(year)]]
    if len(hits) == 0:
        return np.nan, "NOT_FOUND", ""
    if len(hits) > 1:
        return np.nan, "AMBIGUOUS_LABEL", "; ".join(hits["item"].astype(str).tolist()[:3])
    raw = hits.iloc[0][str(year)]
    val = pd.to_numeric(pd.Series([raw]), errors="coerce").iloc[0]
    if not np.isfinite(val):
        return np.nan, "NON_NUMERIC", str(hits.iloc[0]["item"])
    return float(val), "EXACT_UNVERIFIED", str(hits.iloc[0]["item"])


def check_nonfinancial_profit(df, year, reported_profit):
    """Cross-check annual consolidated PAT against two statement identities.

    'Chi phí thuế thu nhập doanh nghiệp' is negative in most provided files,
    but its raw signed value must be used. If a line is missing, return None
    (not checked). If a present line is ambiguous or inconsistent, return False.
    This is for candidate quality control; it does not verify source filings.
    """
    if df is None or not np.isfinite(reported_profit):
        return None, ""

    checks = []
    notes = []
    for lhs, rhs, tag in (
        ("pre_tax_profit", "signed_tax_expense", "PRETAX_PLUS_TAX"),
        ("parent_profit", "minority_profit", "PARENT_PLUS_MINORITY"),
    ):
        hit_values = []
        for metric in (lhs, rhs):
            hits = df.loc[df["_key"].isin(INCOME_CHECK_ALIASES[metric]), str(year)]
            if len(hits) == 0:
                hit_values = None
                break
            if len(hits) > 1:
                return False, f"{tag}_AMBIGUOUS"
            val = pd.to_numeric(pd.Series([hits.iloc[0]]), errors="coerce").iloc[0]
            if not np.isfinite(val):
                return False, f"{tag}_NON_NUMERIC"
            hit_values.append(float(val))
        if hit_values is None:
            continue
        expected = sum(hit_values)
        tolerance = max(abs(float(reported_profit)), abs(expected), 1.0) * 0.005
        passes = abs(expected - float(reported_profit)) <= tolerance
        checks.append(passes)
        if not passes:
            notes.append(f"{tag}_MISMATCH")
    return (all(checks) if checks else None), " | ".join(notes)


def positive_ratio(numer, denom, factor=1.0):
    if pd.notna(numer) and pd.notna(denom) and denom > 0:
        return factor * numer / denom
    return np.nan


def build(staging: Path, output: Path, symbols=None):
    symbols = list(symbols) if symbols is not None else catalogue_symbols(ROOT)
    sectors = catalogue_company_groups(ROOT)
    snapshots, coverage = [], []
    for symbol in symbols:
        group = financial_type(symbol, sectors)
        src = {}
        load_notes = []
        for st in STATEMENTS:
            src[st], state = load_statement(staging / f"{symbol}_{st}.csv")
            if state != "OK":
                load_notes.append(f"{st}:{state}")
        data = {}
        for year in YEARS:
            vals, statuses, source_labels = {}, {}, {}
            for metric, statement in STATEMENT_FOR.items():
                value, state, label = one_value(src[statement], year, metric)
                vals[metric] = value
                statuses[metric] = state
                source_labels[metric] = label
            a, l, e = vals["assets"], vals["liabilities"], vals["equity"]
            residual = (a - l - e) / a if all(pd.notna(x) for x in (a, l, e)) and a > 0 else np.nan
            balance_pass = pd.notna(residual) and abs(residual) <= 0.005 and e > 0
            note = list(load_notes)
            if pd.notna(residual) and not balance_pass:
                note.append("BALANCE_IDENTITY_FAIL")
            for metric in ("assets", "liabilities", "equity", "profit", "eps", "revenue"):
                if statuses[metric] == "AMBIGUOUS_LABEL":
                    note.append(f"AMBIGUOUS_{metric.upper()}")
            prev = data.get(year - 1)
            avg_a = (a + prev["assets"]) / 2 if prev and pd.notna(a) and pd.notna(prev["assets"]) and prev["balance_pass"] else np.nan
            avg_e = (e + prev["equity"]) / 2 if prev and pd.notna(e) and pd.notna(prev["equity"]) and prev["balance_pass"] else np.nan
            pat = vals["profit"]
            income_check, income_check_notes = (
                check_nonfinancial_profit(src["income_statement"], year, pat)
                if group == "NONFINANCIAL" else (None, "")
            )
            if income_check_notes:
                note.extend(income_check_notes.split(" | "))
            # Do not derive ratios from a failed income reconciliation. A missing
            # reconciliation is not automatically a failure (e.g. bank templates).
            can_use_profit = income_check is not False
            # Only compute ratios from a valid same-year and prior-year balance identity.
            roe = positive_ratio(pat, avg_e, 100) if balance_pass and can_use_profit else np.nan
            roa = positive_ratio(pat, avg_a, 100) if balance_pass and can_use_profit else np.nan
            eps_yoy = (100 * (vals["eps"] / prev["eps"] - 1)
                       if prev and pd.notna(vals["eps"]) and pd.notna(prev["eps"]) and prev["eps"] > 0 else np.nan)
            # Revenues and liquidity have different meanings for regulated financial entities.
            margin = positive_ratio(pat, vals["revenue"], 100) if group == "NONFINANCIAL" and can_use_profit else np.nan
            gross_margin = positive_ratio(vals["gross_profit"], vals["revenue"], 100) if group == "NONFINANCIAL" else np.nan
            current_ratio = positive_ratio(vals["current_assets"], vals["current_liabilities"]) if group == "NONFINANCIAL" else np.nan
            leverage = positive_ratio(l, e)  # Liabilities/equity, NOT borrowing debt/equity
            record = {
                "symbol": symbol, "year": year, "company_type": group,
                "total_assets_vnd_candidate": a, "total_liabilities_vnd_candidate": l,
                "equity_vnd_candidate": e, "net_profit_vnd_candidate": pat,
                "eps_vnd_candidate": vals["eps"],
                "revenue_vnd_candidate": vals["revenue"],
                "balance_residual_pct": residual * 100 if pd.notna(residual) else np.nan,
                "balance_identity_pass": bool(balance_pass),
                "roe_pct_provisional": roe, "roa_pct_provisional": roa,
                "eps_growth_pct_provisional": eps_yoy,
                "net_margin_pct_provisional": margin,
                "gross_margin_pct_provisional": gross_margin,
                "current_ratio_provisional": current_ratio,
                "liabilities_to_equity_provisional": leverage,
                # Explainability: source line names and income reconciliations.
                "source_label_assets": source_labels["assets"],
                "source_label_profit": source_labels["profit"],
                "source_label_revenue": source_labels["revenue"],
                "profit_reconciliation_pass": income_check,
                "published_at": "", "source_verified": "NO", "score_eligible": "NO",
                "status": "PROVISIONAL_REVIEW_REQUIRED" if any(pd.notna(v) for v in vals.values()) else "NO_USABLE_METRICS",
                "issues": " | ".join(dict.fromkeys(note)),
            }
            snapshots.append(record)
            data[year] = dict(vals, balance_pass=balance_pass)
        subset = [r for r in snapshots if r["symbol"] == symbol]
        last = subset[-1]
        coverage.append({
            "symbol": symbol, "company_type": group,
            "statement_files_present": sum((staging / f"{symbol}_{st}.csv").is_file() for st in STATEMENTS),
            "2025_balance_pass": last["balance_identity_pass"],
            "2025_roe_available": pd.notna(last["roe_pct_provisional"]),
            "2025_roa_available": pd.notna(last["roa_pct_provisional"]),
            "2025_eps_growth_available": pd.notna(last["eps_growth_pct_provisional"]),
            "2025_issues": last["issues"],
            "score_eligible": "NO",
        })
    output.mkdir(parents=True, exist_ok=True)
    features = pd.DataFrame(snapshots)
    cover = pd.DataFrame(coverage)
    for filename, table in (("financial_features_annual.csv", features),
                            ("financial_feature_coverage.csv", cover)):
        tmp = output / (filename + ".tmp")
        table.to_csv(tmp, index=False, encoding="utf-8-sig")
        os.replace(tmp, output / filename)
    return features, cover


def selftest():
    with tempfile.TemporaryDirectory() as td:
        base = Path(td)
        in_dir, out_dir = base / "staging", base / "processed"
        in_dir.mkdir()
        for symbol in ("TCB", "SSI"):
            pd.DataFrame({"item": ["TỔNG TÀI SẢN", "Nợ phải trả", "Vốn chủ sở hữu"],
                          "2023": [100, 60, 40], "2024": [120, 72, 48], "2025": [140, 84, 56]}).to_csv(in_dir / f"{symbol}_balance_sheet.csv", index=False)
            labels = ["Lợi nhuận sau thuế", "Lãi cơ bản trên cổ phiếu", "DOANH THU HOẠT ĐỘNG"]
            if symbol == "SSI":
                labels.append("Doanh thu thuần về hoạt động kinh doanh")
            df = pd.DataFrame({"item": labels, "2023": [8, 1000, 40] + ([40] if symbol == "SSI" else []),
                               "2024": [12, 1100, 50] + ([50] if symbol == "SSI" else []),
                               "2025": [14, 1200, 60] + ([60] if symbol == "SSI" else [])})
            df.to_csv(in_dir / f"{symbol}_income_statement.csv", index=False)
            pd.DataFrame({"item": ["Lưu chuyển tiền"], "2023": [1], "2024": [2], "2025": [3]}).to_csv(in_dir / f"{symbol}_cash_flow.csv", index=False)
        feat, _ = build(in_dir, out_dir, symbols=["TCB", "SSI"])
        tcb23 = feat[(feat.symbol == "TCB") & (feat.year == 2023)].iloc[0]
        tcb24 = feat[(feat.symbol == "TCB") & (feat.year == 2024)].iloc[0]
        ssi24 = feat[(feat.symbol == "SSI") & (feat.year == 2024)].iloc[0]
        assert pd.isna(tcb23.roe_pct_provisional), "2023 has no 2022 average equity"
        assert abs(tcb24.roe_pct_provisional - 100 * 12 / 44) < 1e-10
        assert pd.isna(ssi24.revenue_vnd_candidate), "Duplicate revenue labels must be blocked"
        assert feat.score_eligible.eq("NO").all(), "Never auto-score unverified statements"
        assert (out_dir / "financial_feature_coverage.csv").is_file()
        # Exact aliases seen in the supplied BCTC: do not rely on fuzzy matching.
        nonfin = pd.DataFrame({
            "item": ["TỔNG CỘNG TÀI SẢN", "NỢ PHẢI TRẢ", "Vốn chủ sở hữu",
                     "Lãi/(lỗ) thuần sau thuế", "Doanh số thuần", "Lãi gộp"],
            "2025": [140, 84, 56, 14, 70, 21],
        })
        nonfin["_key"] = nonfin["item"].map(norm)
        for metric, expected in (("assets", 140), ("profit", 14),
                                 ("revenue", 70), ("gross_profit", 21)):
            value, status, _ = one_value(nonfin, 2025, metric)
            assert status == "EXACT_UNVERIFIED" and value == expected, metric
        ni = pd.DataFrame({
            "item": ["Lãi/(lỗ) trước thuế", "Chi phí thuế thu nhập doanh nghiệp",
                     "Lợi nhuận của Cổ đông của Công ty mẹ",
                     "Lợi ích của cổ đông thiểu số"],
            "2025": [16, -2, 13, 1],
        })
        ni["_key"] = ni["item"].map(norm)
        flag, reason = check_nonfinancial_profit(ni, 2025, 14)
        assert flag is True, reason
        flag, _ = check_nonfinancial_profit(ni, 2025, 15)
        assert flag is False, "Mismatching profit must be rejected"
    print("SELF-TEST PASSED: aliases, ROE, income cross-checks, duplicate labels, no auto-score")


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--staging", type=Path, default=ROOT / "data" / "fundamentals" / "staging")
    p.add_argument("--out", type=Path, default=ROOT / "data" / "fundamentals" / "processed")
    p.add_argument("--self-test", action="store_true")
    args = p.parse_args()
    if args.self_test:
        selftest()
        return
    features, cover = build(args.staging, args.out)
    recent = features[features.year == 2025]
    print("=== AURA FINANCIAL FEATURES TOAN THI TRUONG (CHUA XAC MINH) ===")
    print(f"Ma trong danh muc: {len(cover)} | dong theo nam: {len(features)}")
    print(f"2025 BCTC co it nhat 1 file: {int(cover['statement_files_present'].gt(0).sum())}/{len(cover)}")
    print(f"2025 BCTC du 3 file: {int(cover['statement_files_present'].eq(3).sum())}/{len(cover)}")
    print(f"2025 balance identity PASS: {recent.balance_identity_pass.sum()}/{len(recent)}")
    for metric in ("roe_pct_provisional", "roa_pct_provisional", "eps_growth_pct_provisional",
                   "net_margin_pct_provisional", "gross_margin_pct_provisional"):
        print(f"2025 {metric}: {recent[metric].notna().sum()}/{len(recent)}")
    nonfin = recent[recent.company_type == "NONFINANCIAL"]
    if not nonfin.empty:
        print(f"2025 income reconciliation PASS: "
              f"{nonfin['profit_reconciliation_pass'].eq(True).sum()}/{len(nonfin)} nonfinancial firms")
    print("Ready for Smart Rating: 0 (publication dates and filings not verified)")
    print("Output:", args.out / "financial_features_annual.csv")
    print("Output:", args.out / "financial_feature_coverage.csv")


if __name__ == "__main__":
    main()
