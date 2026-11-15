"""BatDayStox SSI -- financial mapping review from audited financial CSVs.

INPUT: financial_line_candidates.csv, financial_review_flags.csv, financial_inventory.csv.
OUTPUT: candidates and consistency checks. NEVER populates the scored fundamentals_snapshot.csv.
No network, credentials, trading endpoints, or changes to the X10/screener models.
"""
from __future__ import annotations

from pathlib import Path
import pandas as pd
import numpy as np

# Deliberately narrow: ambiguities and 'review' aliases are never auto-selected.
STATEMENT_FOR = {
    "total_assets": "balance_sheet",
    "equity": "balance_sheet",
    "liabilities": "balance_sheet",
    "profit_after_tax": "income_statement",
    "profit_before_tax": "income_statement",
    "eps": "income_statement",
    "revenue": "income_statement",
    "gross_profit": "income_statement",
    "income_tax_expense": "income_statement",
}
METRIC_LIST = list(STATEMENT_FOR)
FINANCIAL_GROUPS = {"TCB": "BANK", "SSI": "SECURITIES", "FPT": "NONBANK"}


def _read_table(path: Path, required: set[str]) -> pd.DataFrame:
    df = pd.read_csv(path, encoding="utf-8-sig", low_memory=False)
    if not required.issubset(df.columns):
        raise ValueError(f"{path.name}: missing {sorted(required - set(df.columns))}")
    return df


def _finite(x):
    try:
        n = float(x)
        if np.isfinite(n):
            return n
    except (TypeError, ValueError, OverflowError):
        pass
    return np.nan


def compile_financial_review(audit_dir: Path, out_dir: Path):
    audit_dir, out_dir = Path(audit_dir), Path(out_dir)
    candidates = _read_table(audit_dir / "financial_line_candidates.csv", {
        "symbol", "statement", "year", "metric", "match", "row", "label", "value", "source_file"
    })
    flags = _read_table(audit_dir / "financial_review_flags.csv", {
        "symbol", "year", "severity", "test", "details"
    })
    inventory = _read_table(audit_dir / "financial_inventory.csv", {"symbol", "type", "file", "rows"})
    if candidates.empty:
        raise ValueError("No candidate metrics were found")
    candidates["symbol"] = candidates["symbol"].astype(str).str.upper().str.strip()
    candidates["year"] = pd.to_numeric(candidates["year"], errors="coerce")
    candidates["value"] = pd.to_numeric(candidates["value"], errors="coerce")
    flags["symbol"] = flags["symbol"].astype(str).str.upper().str.strip()
    flags["year"] = pd.to_numeric(flags["year"], errors="coerce")

    decisions = []
    for (symbol, year), df in candidates.groupby(["symbol", "year"], sort=True):
        year = int(year)
        ff = flags.loc[(flags.symbol == symbol) & (flags.year == year)]
        blocked_tax = ((ff.test == "tax_equals_pretax") & (ff.severity == "CRITICAL_REVIEW")).any()
        for metric, statement in STATEMENT_FOR.items():
            hits = df[(df.metric == metric) & (df.statement == statement)]
            exact = hits[(hits.match == "exact") & hits.value.notna()]
            decision = "UNMAPPED"
            if len(exact) == 1:
                decision = "MATCHED_UNVERIFIED"
            elif len(exact) > 1:
                decision = "AMBIGUOUS_EXACT"
            elif len(hits) > 0:
                decision = "REVIEW_ONLY"
            if metric == "income_tax_expense" and blocked_tax:
                decision = "BLOCKED_CRITICAL_TAX_LABEL"
            record = {
                "symbol": symbol, "year": year, "entity_type_hint": FINANCIAL_GROUPS.get(symbol, "UNCLASSIFIED"),
                "metric": metric, "status": decision,
                "value_candidate": _finite(exact.iloc[0].value) if decision == "MATCHED_UNVERIFIED" else np.nan,
                "source_file": str(exact.iloc[0].source_file) if decision == "MATCHED_UNVERIFIED" else "",
                "source_row": int(exact.iloc[0]["row"]) if decision == "MATCHED_UNVERIFIED" else np.nan,
                "source_label": str(exact.iloc[0].label) if decision == "MATCHED_UNVERIFIED" else "",
                "exact_matches": len(exact), "other_matches": len(hits) - len(exact),
                "note": "NEEDS accounting source + published_at verification; do not score",
            }
            if metric == "income_tax_expense" and blocked_tax:
                record["note"] = "CRITICAL: ambiguous tax label equals pretax profit; blocked"
            if metric == "revenue" and len(exact) > 1:
                record["note"] = "Two revenue labels; choose correct line from source statement manually"
            decisions.append(record)
    map_df = pd.DataFrame(decisions)
    pivot = map_df.pivot_table(index=["symbol", "year"], columns="metric", values="value_candidate", aggfunc="first").reset_index()
    for m in METRIC_LIST:
        if m not in pivot.columns:
            pivot[m] = np.nan
    pivot = pivot.sort_values(["symbol", "year"]).reset_index(drop=True)
    pivot["entity_type_hint"] = pivot.symbol.map(FINANCIAL_GROUPS).fillna("UNCLASSIFIED")

    metrics = []
    for symbol, g in pivot.groupby("symbol"):
        g = g.sort_values("year").reset_index(drop=True)
        for ix, r in g.iterrows():
            prev = g.iloc[ix - 1] if ix > 0 and int(g.iloc[ix - 1].year) == int(r.year) - 1 else None
            assets, eq, debt = (r["total_assets"], r["equity"], r["liabilities"])
            balance_residual_pct = np.nan
            if all(pd.notna(v) for v in [assets, eq, debt]) and assets > 0:
                balance_residual_pct = 100 * (assets - eq - debt) / assets
            balance_pass = pd.notna(balance_residual_pct) and abs(balance_residual_pct) <= .5
            pat = r["profit_after_tax"]
            avg_assets = (assets + prev["total_assets"]) / 2 if prev is not None and pd.notna(assets) and pd.notna(prev["total_assets"]) else np.nan
            avg_equity = (eq + prev["equity"]) / 2 if prev is not None and pd.notna(eq) and pd.notna(prev["equity"]) else np.nan
            # Ratios are analytical PREVIEWS only, not eligible for production score.
            roa = 100 * pat / avg_assets if pd.notna(pat) and pd.notna(avg_assets) and avg_assets > 0 and balance_pass else np.nan
            roe = 100 * pat / avg_equity if pd.notna(pat) and pd.notna(avg_equity) and avg_equity > 0 and balance_pass else np.nan
            eps = r["eps"]
            prev_eps = prev["eps"] if prev is not None else np.nan
            eps_growth = 100 * (eps / prev_eps - 1) if pd.notna(eps) and pd.notna(prev_eps) and prev_eps > 0 else np.nan
            if symbol == "SSI":
                # Same-year critical tax flags mean avoid calling the entire P&L verified.
                risk = "CRITICAL_TAX_LABEL; revenue ambiguous; verify official statements"
            elif symbol == "TCB":
                risk = "Bank ratio method/numerator and publication date require verification"
            else:
                risk = "Verify net profit and EPS split-adjustment / publication date"
            metrics.append({
                "symbol": symbol, "year": int(r.year), "entity_type_hint": r.entity_type_hint,
                "assets_vnd_candidate": assets, "liabilities_vnd_candidate": debt, "equity_vnd_candidate": eq,
                "net_profit_vnd_candidate": pat, "eps_vnd_candidate": eps,
                "balance_residual_pct": balance_residual_pct,
                "balance_identity_status": "PASS_PRELIMINARY" if balance_pass else ("FAIL" if pd.notna(balance_residual_pct) else "INSUFFICIENT"),
                "roe_pct_provisional": roe, "roa_pct_provisional": roa, "eps_growth_pct_provisional": eps_growth,
                "published_at": "", "filing_url": "", "verified": "NO", "score_eligible": "NO",
                "review_note": risk,
            })
    provisional = pd.DataFrame(metrics)
    # Per company and year: avoid treating the flat-year export as publication-stamped data.
    requests = []
    for _, r in provisional.iterrows():
        requests.append({
            "symbol": r.symbol, "report_period_end": f"{int(r.year)}-12-31", "published_at": "",
            "official_filing_url": "", "report_scope": "", "audited_or_reviewed": "",
            "currency_unit_verified": "NO", "net_profit_basis_checked": "NO",
            "price_adjustments_checked": "NO", "reviewer_note": "",
        })
    publication = pd.DataFrame(requests)
    ratios_schema = _read_table(audit_dir / "ratio_schema_examples.csv", {"symbol", "sample"})
    issues = flags.copy()
    # Add absence warnings where extracted statements don't supply key score metrics.
    for _, r in provisional.iterrows():
        for col in ["net_profit_vnd_candidate", "assets_vnd_candidate", "equity_vnd_candidate"]:
            if pd.isna(r[col]):
                issues.loc[len(issues)] = {
                    "symbol": r.symbol, "year": r.year, "severity": "MISSING_METRIC", "test": col,
                    "details": "No unique, exact source match; manual source mapping required"
                }

    out_dir.mkdir(parents=True, exist_ok=True)
    paths = {
        "map": out_dir / "financial_metric_mapping_review.csv",
        "provisional": out_dir / "financial_metrics_provisional.csv",
        "flags": out_dir / "financial_mapping_issues.csv",
        "publication": out_dir / "publication_dates_review_template.csv",
        "ratio": out_dir / "ratio_schema_reference.csv",
    }
    map_df.to_csv(paths["map"], index=False, encoding="utf-8-sig")
    provisional.to_csv(paths["provisional"], index=False, encoding="utf-8-sig")
    issues.to_csv(paths["flags"], index=False, encoding="utf-8-sig")
    publication.to_csv(paths["publication"], index=False, encoding="utf-8-sig")
    ratios_schema.to_csv(paths["ratio"], index=False, encoding="utf-8-sig")
    stats = {
        "companies": len(provisional.symbol.unique()),
        "years": len(provisional),
        "exact_candidate_metrics": int((map_df.status == "MATCHED_UNVERIFIED").sum()),
        "blocked_critical": int((map_df.status == "BLOCKED_CRITICAL_TAX_LABEL").sum()),
        "provisional_roes": int(provisional.roe_pct_provisional.notna().sum()),
        "ready_for_score": 0,
        "outputs": paths,
    }
    return stats
