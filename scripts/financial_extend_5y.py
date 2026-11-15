"""Extend existing annual BCTC staging with 2021 and 2022 without overwriting 2023-2025.

Run AFTER scripts/sync_market_financials.py has stopped/finished.
Prices, index, investment ratings and previous 2023-2025 values are untouched.
Use only source-supported historic years; do not fabricate missing history.
"""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
from pathlib import Path
import os
import sys
import time
from typing import Any

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from core.ssi_universe import load_catalogue
from scripts import sync_market_financials as prior

YEARS = ("2021", "2022", "2023", "2024", "2025")
EXTRA = ("2021", "2022")
STAGING = ROOT / "data" / "fundamentals" / "staging"
LEDGER = ROOT / "data" / "fundamentals" / "financial_5y_status.csv"
STATEMENTS = prior.STATEMENTS

# Prior module has shared helpers; use them with the extended annual year range.
prior.YEARS = YEARS


def now_iso() -> str:
    return datetime.now(timezone.utc).astimezone().isoformat(timespec="seconds")


def header_years(symbol: str, statement: str) -> set[str]:
    path = STAGING / f"{symbol}_{statement}.csv"
    if not path.is_file():
        return set()
    try:
        cols = pd.read_csv(path, nrows=0, encoding="utf-8-sig").columns
        return set(str(c) for c in cols if str(c) in YEARS)
    except (OSError, ValueError, pd.errors.ParserError):
        return set()


def read_existing(symbol: str, statement: str) -> pd.DataFrame | None:
    path = STAGING / f"{symbol}_{statement}.csv"
    if not path.is_file():
        return None
    table = pd.read_csv(path, encoding="utf-8-sig")
    label_col = "item" if "item" in table.columns else (table.columns[0] if len(table.columns) else "")
    if not label_col:
        raise ValueError("Existing file lacks item names")
    table = table.set_index(label_col)
    table.index = table.index.astype(str).str.strip()
    if not table.index.is_unique or table.index.hasnans:
        raise ValueError("Existing BCTC has duplicate/empty item labels")
    keep = [c for c in table.columns if str(c) in YEARS]
    if not keep:
        raise ValueError("Existing BCTC has no recognized annual years")
    table = table[keep]
    table.columns = [str(c) for c in table.columns]
    return table.apply(pd.to_numeric, errors="coerce")


def to_prepared(raw: pd.DataFrame) -> pd.DataFrame:
    standardized = prior.prepare_wide(raw)
    if "item" not in standardized.columns:
        raise ValueError("Source has no item column")
    out = standardized.set_index("item")
    out.index = out.index.astype(str).str.strip()
    if out.index.duplicated().any():
        raise ValueError("Source has duplicate item labels")
    out.columns = [str(c) for c in out.columns]
    return out.apply(pd.to_numeric, errors="coerce")


def _normalized_labels(df: pd.DataFrame) -> pd.DataFrame:
    """Use exact punctuation-insensitive matching only for source consistency tests."""
    index = df.index.to_series().map(lambda x: str(x).casefold().strip()).str.replace(r"\s+", " ", regex=True)
    if index.duplicated().any():
        raise ValueError("Duplicate normalized statement labels")
    checked = df.copy()
    checked.index = index.to_list()
    return checked


def overlapping_sources_are_compatible(existing: pd.DataFrame, candidate: pd.DataFrame) -> bool:
    """Prevent merging financial figures from sources with different units/definitions.

    Requires at least 3 comparable nonzero numbers in a common year and
    <= 2% relative discrepancy for 90% of them, <= 8% for all. Conservative.
    """
    common_years = [year for year in YEARS if year in existing.columns and year in candidate.columns]
    if not common_years:
        return False
    left, right = _normalized_labels(existing), _normalized_labels(candidate)
    items = left.index.intersection(right.index)
    if items.empty:
        return False
    ratios = []
    for year in common_years:
        a = pd.to_numeric(left.loc[items, year], errors="coerce")
        b = pd.to_numeric(right.loc[items, year], errors="coerce")
        ok = a.notna() & b.notna() & ((a.abs() + b.abs()) > 1e-8)
        for v1, v2 in zip(a[ok].to_numpy(), b[ok].to_numpy()):
            ratios.append(abs(v1 - v2) / max(abs(v1), abs(v2), 1e-8))
    if len(ratios) < 3:
        return False
    discrepancy = np.asarray(ratios)
    return bool(np.quantile(discrepancy, 0.90) <= 0.02 and discrepancy.max() <= 0.08)


def merge_only_missing_years(existing: pd.DataFrame | None, incoming: pd.DataFrame) -> tuple[pd.DataFrame | None, str]:
    missing = [year for year in EXTRA if year in incoming.columns and incoming[year].notna().any()]
    if not missing:
        return None, "NO_OLD_YEARS"
    if existing is None:
        # New symbol: preserve all reported years, not only 2021/2022.
        chosen = [y for y in YEARS if y in incoming.columns]
        out = incoming[chosen].copy()
        return out, "NEW_FILE"
    years_to_add = [y for y in missing if y not in existing.columns or existing[y].isna().all()]
    if not years_to_add:
        return None, "ALREADY_5Y"
    if not overlapping_sources_are_compatible(existing, incoming):
        return None, "SOURCE_MISMATCH_REVIEW"
    out = existing.copy()
    # Add only actual source values for 2021/22. Preserve every existing datum.
    # Match source labels consistently with the overlap check; protect differing
    # capitalization/whitespace without silently merging duplicate labels.
    old_labels = _normalized_labels(out)
    new_labels = _normalized_labels(incoming)
    for year in years_to_add:
        old_labels[year] = new_labels[year].reindex(old_labels.index)
        more_items = new_labels.index.difference(old_labels.index)
        if not more_items.empty:
            extra = pd.DataFrame(index=more_items, columns=old_labels.columns, dtype=float)
            extra[year] = new_labels.loc[more_items, year]
            old_labels = pd.concat([old_labels, extra], axis=0)
    # Preserve the original item captions, including Vietnamese accents/casing.
    original_captions = {str(k).casefold().strip(): str(k) for k in out.index}
    old_labels.index = [original_captions.get(str(k), str(k)) for k in old_labels.index]
    out = old_labels
    out = out[[year for year in YEARS if year in out.columns]]
    return out, "EXTENDED"


def try_update(symbol: str, statement: str, incoming: pd.DataFrame) -> str:
    existing = read_existing(symbol, statement)
    merged, status = merge_only_missing_years(existing, incoming)
    if merged is None:
        return status
    target = STAGING / f"{symbol}_{statement}.csv"
    saved = merged.reset_index().rename(columns={merged.index.name or "index": "item"})
    if "item" not in saved.columns:
        saved = saved.rename(columns={saved.columns[0]: "item"})
    prior.atomic_csv(saved, target, replace=True)
    return status


def ledger_load() -> dict[str, dict[str, Any]]:
    if not LEDGER.is_file():
        return {}
    try:
        df = pd.read_csv(LEDGER, encoding="utf-8-sig", dtype=str, keep_default_na=False)
        return {row["symbol"]: row.to_dict() for _, row in df.iterrows()}
    except (OSError, ValueError, KeyError, pd.errors.ParserError):
        return {}


def ledger_save(rows: dict[str, dict[str, Any]]) -> None:
    fields = ("symbol", "status", "added", "total_historic_files", "notes", "attempted_at")
    output = pd.DataFrame([{field: rec.get(field, "") for field in fields}
                           for _, rec in sorted(rows.items())], columns=fields)
    prior.atomic_csv(output, LEDGER, replace=True)


def needs_history(symbol: str) -> bool:
    # A source may provide only 1-4 years for recent listings. We never invent a year.
    return any(not set(EXTRA).issubset(header_years(symbol, st)) for st in STATEMENTS)


def run() -> None:
    ap = argparse.ArgumentParser(description="AURA: extend BCTC 2023-25 to 2021-25 when reported")
    ap.add_argument("--limit", type=int, default=0, help="0 = every eligible symbol")
    ap.add_argument("--pause", type=float, default=1.5)
    ap.add_argument("--retry", action="store_true", help="retry previously checked symbols")
    ap.add_argument("--no-build", action="store_true", help="do not rebuild preview features")
    ap.add_argument("--dry-run", action="store_true", help="show pending symbols only")
    args = ap.parse_args()
    if args.limit < 0 or args.pause < 0:
        ap.error("limit/pause must be >= 0")
    catalogue = load_catalogue(ROOT)
    if "asset_class" not in catalogue or "symbol" not in catalogue:
        raise SystemExit("Khong co SSI EQUITY catalogue")
    symbols = sorted(set(catalogue.loc[catalogue["asset_class"].eq("EQUITY"), "symbol"]
                         .astype(str).str.upper().str.strip()))
    rows = ledger_load()
    done_states = {"EXTENDED", "PARTIAL", "NO_OLD_YEARS", "NO_SOURCE", "REVIEW_REQUIRED", "ALREADY_5Y"}
    todo = [s for s in symbols if needs_history(s) and (args.retry or rows.get(s, {}).get("status") not in done_states)]
    if args.limit:
        todo = todo[:args.limit]
    print(f"AURA BCTC 2021-2025 | danh muc {len(symbols)} | can kiem tra {len(todo)}", flush=True)
    if args.dry_run:
        print("20 ma dau:", ", ".join(todo[:20]))
        return
    if not todo:
        print("Da kiem tra het cac ma du dieu kien (hoac can --retry).")
        return
    # One bulk fetch, not a costly remote call for each of 1518 symbols.
    bulk, messages = prior.prefetch_bulk(set(todo))
    for msg in messages:
        print("Nguon:", msg, flush=True)
    count_extended = count_manual = 0
    STAGING.mkdir(parents=True, exist_ok=True)
    for n, symbol in enumerate(todo, 1):
        statuses, notes = [], []
        left = [st for st in STATEMENTS if not set(EXTRA).issubset(header_years(symbol, st))]
        for st in left:
            raw = bulk.get((symbol, st))
            if raw is not None:
                try:
                    status = try_update(symbol, st, to_prepared(raw))
                    statuses.append(status)
                    if status == "SOURCE_MISMATCH_REVIEW":
                        notes.append(f"{st}: khac don vi/chi tieu voi 2023-25")
                except (OSError, ValueError, KeyError, TypeError, pd.errors.ParserError) as ex:
                    statuses.append("BULK_ERROR")
                    notes.append(f"{st}:{type(ex).__name__}")
        missing = [st for st in left if not set(EXTRA).issubset(header_years(symbol, st))]
        if missing:
            fallback = prior.fallback_vnstock(symbol, allow=True)
            for st in missing:
                if st not in fallback:
                    continue
                try:
                    status = try_update(symbol, st, to_prepared(fallback[st]))
                    statuses.append(status)
                    if status == "SOURCE_MISMATCH_REVIEW":
                        notes.append(f"{st}: khac don vi/chi tieu voi 2023-25")
                except (OSError, ValueError, KeyError, TypeError, pd.errors.ParserError) as ex:
                    statuses.append("FALLBACK_ERROR")
                    notes.append(f"{st}:{type(ex).__name__}")
        now_present = sum(set(EXTRA).issubset(header_years(symbol, st)) for st in STATEMENTS)
        added = statuses.count("EXTENDED") + statuses.count("NEW_FILE")
        if added:
            count_extended += 1
        if "SOURCE_MISMATCH_REVIEW" in statuses:
            status = "REVIEW_REQUIRED"
            count_manual += 1
        elif now_present == 3:
            status = "EXTENDED" if added else "ALREADY_5Y"
        elif now_present > 0:
            status = "PARTIAL"
        else:
            status = "NO_OLD_YEARS" if statuses else "NO_SOURCE"
        rows[symbol] = dict(symbol=symbol, status=status, added=str(added),
                            total_historic_files=str(now_present), notes=" | ".join(notes)[:300],
                            attempted_at=now_iso())
        ledger_save(rows)
        print(f"[{n}/{len(todo)}] {symbol}: {status} ({now_present}/3 bao cao co 2021+2022; +{added})", flush=True)
        if n != len(todo) and args.pause:
            time.sleep(args.pause)
    print(f"HOAN THANH DOT: {count_extended} ma bo sung | {count_manual} ma khac so lieu can xem lai")
    print("Nhat ky:", LEDGER)
    if not args.no_build:
        from build_financial_features import build, catalogue_symbols
        feats, cover = build(STAGING, ROOT / "data" / "fundamentals" / "processed",
                             symbols=catalogue_symbols(ROOT))
        print(f"Da tao lai chi tieu 2021-2025: {len(feats)} dong nam; van CHUA xac minh ngay cong bo.")


if __name__ == "__main__":
    try:
        run()
    except KeyboardInterrupt:
        print("\nDa dung. Du lieu va trang thai cua cac ma hoan thanh da duoc giu lai.", flush=True)
        raise SystemExit(130)
