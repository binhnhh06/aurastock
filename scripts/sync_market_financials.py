"""AURA: thu thap BCTC nam 2023-2025 cho danh muc EQUITY SSI.

Luu file nguon dang chi-tieu x nam va nhat ky. KHONG chung nhan ngay cong bo,
KHONG thay the ho so BCTC goc, KHONG auto-cap nhat diem dau tu.
Nguon thu: vnfinancialdata (HSX/HNX) + fallback vnstock neu co quyen.
Gia/SSI khong dung de lay BCTC. Chay lai duoc va khong ghi de file cu.
"""
from __future__ import annotations

import argparse
from datetime import datetime, timezone, timedelta
import os
from pathlib import Path
import re
import sys
import time
from typing import Any

import pandas as pd

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from core.ssi_universe import load_catalogue

STATEMENTS = ("balance_sheet", "income_statement", "cash_flow")
YEARS = ("2023", "2024", "2025")
STAGING = ROOT / "data" / "fundamentals" / "staging"
LEDGER = ROOT / "data" / "fundamentals" / "fundamental_sync_status.csv"
VALID_SYMBOL = re.compile(r"^[A-Z0-9]{2,12}$")


def iso_now() -> str:
    return datetime.now(timezone.utc).astimezone().isoformat(timespec="seconds")


def atomic_csv(table: pd.DataFrame, dest: Path, *, replace: bool = False) -> bool:
    dest.parent.mkdir(parents=True, exist_ok=True)
    tmp = dest.with_name(dest.name + ".tmp")
    table.to_csv(tmp, index=False, encoding="utf-8-sig")
    try:
        if not replace and dest.is_file():
            return False
        os.replace(tmp, dest)
        return True
    finally:
        tmp.unlink(missing_ok=True)


def current_ledger() -> dict[str, dict[str, str]]:
    if not LEDGER.is_file():
        return {}
    try:
        df = pd.read_csv(LEDGER, encoding="utf-8-sig", keep_default_na=False, dtype=str)
        if "symbol" not in df:
            return {}
        return {str(row["symbol"]): {str(k): str(v) for k, v in row.items()}
                for _, row in df.iterrows()}
    except (OSError, ValueError, pd.errors.ParserError):
        return {}


def save_ledger(records: dict[str, dict[str, str]]) -> None:
    cols = ["symbol", "board", "status", "saved", "files_present", "sources", "detail", "attempted_at"]
    rows = [{col: rec.get(col, "") for col in cols} for _, rec in sorted(records.items())]
    atomic_csv(pd.DataFrame(rows, columns=cols), LEDGER, replace=True)


def existing_statement(symbol: str, st: str) -> bool:
    f = STAGING / f"{symbol}_{st}.csv"
    return f.is_file() and f.stat().st_size > 30


def _column(frame: pd.DataFrame, *names: str) -> Any:
    mapping = {str(c).strip().casefold(): c for c in frame.columns}
    for n in names:
        if n.casefold() in mapping:
            return mapping[n.casefold()]
    return None


def prepare_wide(frame: pd.DataFrame) -> pd.DataFrame:
    """Nhan bang chi-tieu x nam, hoac bang long, khong tu doan don vi."""
    if not isinstance(frame, pd.DataFrame) or frame.empty:
        raise ValueError("BCTC trong")
    if isinstance(frame.columns, pd.MultiIndex):
        raise ValueError("Cot MultiIndex chua duoc chuan hoa")
    df = frame.copy()
    df.columns = [str(c).strip() for c in df.columns]
    target = [y for y in YEARS if y in df.columns]
    if target:
        label = _column(df, "item", "item_name", "name", "Chỉ tiêu")
        if label is not None:
            df = df.set_index(label)
        elif isinstance(df.index, pd.RangeIndex):
            # vnfinancialdata output comes indexed by item_name; raw RangeIndex is not a label.
            raise ValueError("Khong co cot ten chi tieu")
        out = df[target].apply(pd.to_numeric, errors="coerce")
    elif _column(df, "period") is not None and _column(df, "value") is not None:
        period = _column(df, "period")
        item = _column(df, "item", "item_name", "name")
        value = _column(df, "value")
        if item is None:
            raise ValueError("BCTC dang long thieu item/name")
        raw = df[[period, item, value]].copy()
        raw[period] = raw[period].astype(str)
        raw = raw[raw[period].isin(YEARS)]
        raw = raw.drop_duplicates()
        if raw.duplicated([period, item]).any():
            raise ValueError("Chi tieu trung nam, khong tu chon first")
        out = raw.pivot(index=item, columns=period, values=value)
        out = out.apply(pd.to_numeric, errors="coerce")
    else:
        # Legacy vnstock finance often returns one row per year.
        from core.bctc_du_phong import _sang_bang
        tmp = _sang_bang(df, 5)
        if tmp is None:
            raise ValueError("Khong nhan ra ky BCTC nam")
        out = tmp.copy()
        out.columns = [str(c).strip() for c in out.columns]
        out = out[[y for y in YEARS if y in out.columns]]
    out = out.loc[pd.Index(out.index).astype(str).str.strip() != ""]
    out.index = out.index.astype(str).str.strip()
    if out.index.duplicated().any():
        # Multiple labels under one line item are ambiguous for ratio calculations.
        raise ValueError("Trung ten chi tieu BCTC")
    out = out.dropna(axis=0, how="all")
    target = [y for y in YEARS if y in out.columns]
    if not target or out.empty or out[target].notna().sum().sum() < 5:
        raise ValueError("Khong du chi tieu/ky nam hop le")
    out = out[target].reset_index().rename(columns={out.index.name or "index": "item"})
    if "item" not in out.columns:
        out = out.rename(columns={out.columns[0]: "item"})
    return out


def prefetch_bulk(symbols: set[str]) -> tuple[dict[tuple[str, str], pd.DataFrame], list[str]]:
    """Load up to 6 reports (2 boards x 3), index by symbol once, avoid 1518 x re-scan."""
    indexed: dict[tuple[str, str], pd.DataFrame] = {}
    logs = []
    try:
        import vnfinancialdata as vnf
    except ImportError:
        return indexed, ["vnfinancialdata chua cai, thu fallback vnstock"]
    for exchange in ("HSX", "HNX"):
        for statement in STATEMENTS:
            try:
                df = vnf.load(exchange=exchange, statement=statement)
                if not isinstance(df, pd.DataFrame) or df.empty:
                    logs.append(f"{exchange}/{statement}: khong co bang")
                    continue
                symbol_col = _column(df, "ticker", "symbol", "stock_code", "code", "company_code")
                year_col = _column(df, "year", "fiscal_year", "period")
                item_col = _column(df, "item_name", "item", "name")
                value_col = _column(df, "value")
                if any(x is None for x in (symbol_col, year_col, item_col, value_col)):
                    logs.append(f"{exchange}/{statement}: sai so do cot")
                    continue
                raw = df[[symbol_col, year_col, item_col, value_col]].copy()
                raw.columns = ["symbol", "year", "item", "value"]
                raw["symbol"] = raw["symbol"].astype(str).str.upper().str.strip()
                raw["year"] = pd.to_numeric(raw["year"], errors="coerce").astype("Int64").astype(str)
                raw = raw[raw["symbol"].isin(symbols) & raw["year"].isin(YEARS)]
                for sym, sub in raw.groupby("symbol", sort=False):
                    sub = sub[["year", "item", "value"]].dropna(subset=["item", "year"]).drop_duplicates()
                    if sub.duplicated(["year", "item"]).any():
                        logs.append(f"{sym}/{statement}: trung nhan BCTC ({exchange})")
                        continue
                    wide = sub.pivot(index="item", columns="year", values="value")
                    if not wide.empty:
                        indexed[(sym, statement)] = wide
                logs.append(f"{exchange}/{statement}: {len(raw)} dong chi tieu")
            except Exception as exc:
                logs.append(f"{exchange}/{statement}: {type(exc).__name__}")
    return indexed, logs


def fallback_vnstock(symbol: str, *, allow: bool) -> dict[str, pd.DataFrame]:
    """Support the project's legacy Vnstock adapter plus newer Fundamental interfaces."""
    if not allow:
        return {}
    result: dict[str, pd.DataFrame] = {}
    try:
        from core.bctc_du_phong import lay_bctc_du_phong
        result = lay_bctc_du_phong(symbol, 5) or {}
    except (ImportError, RuntimeError, ValueError, AttributeError, KeyError):
        pass
    missing = [st for st in STATEMENTS if st not in result]
    if not missing:
        return result
    try:
        from vnstock import Fundamental
        api = Fundamental().equity(symbol)
    except (ImportError, RuntimeError, ValueError, TypeError, AttributeError):
        return result
    for st in missing:
        for kw in (
            {"period": "year", "lang": "vi", "format": "wide", "source": "vci"},
            {"period": "year", "lang": "vi", "format": "wide", "source": "fhsc"},
            {"period": "year", "lang": "vi", "format": "wide"},
        ):
            try:
                frame = getattr(api, st)(**kw)
                if frame is not None and isinstance(frame, pd.DataFrame) and not frame.empty:
                    # Keep the raw table for prepare_wide to validate later.
                    result[st] = frame
                    break
            except (OSError, RuntimeError, ValueError, TypeError, AttributeError, KeyError):
                continue
    return result


def in_cooldown(record: dict[str, str], hours: float) -> bool:
    if not record or record.get("status") not in ("NO_DATA", "PARTIAL", "ERROR"):
        return False
    try:
        at = datetime.fromisoformat(record.get("attempted_at", ""))
        if at.tzinfo is None:
            return False
        return datetime.now(timezone.utc) - at.astimezone(timezone.utc) < timedelta(hours=hours)
    except (TypeError, ValueError):
        return False


def main() -> None:
    parser = argparse.ArgumentParser(description="AURA: bo sung BCTC 2023-2025 cho EQUITY SSI")
    parser.add_argument("--limit", type=int, default=0, help="0 = toan bo danh muc")
    parser.add_argument("--pause", type=float, default=1.5)
    parser.add_argument("--cooldown-hours", type=float, default=72)
    parser.add_argument("--retry", action="store_true", help="Thu lai ma NO_DATA/ERROR ngay")
    parser.add_argument("--no-fallback", action="store_true", help="Chi lay nguon vnfinancialdata")
    parser.add_argument("--no-build", action="store_true", help="Khong tao lai features sau dong bo")
    parser.add_argument("--build-every", type=int, default=150,
                        help="Tinh lai features sau moi N ma de Streamlit co the xem trong luc tai; 0 = chi cuoi")
    args = parser.parse_args()
    if args.limit < 0 or args.pause < 0 or args.cooldown_hours < 0 or args.build_every < 0:
        parser.error("limit/pause/cooldown-hours phai >= 0")
    catalogue = load_catalogue(ROOT)
    if catalogue.empty or "asset_class" not in catalogue.columns:
        raise SystemExit("Thieu market_symbols.csv voi phan loai SSI EQUITY")
    subset = catalogue.loc[catalogue["asset_class"].eq("EQUITY")].copy()
    symbols = sorted(set(subset["symbol"].astype(str).str.strip().str.upper()))
    symbols = [s for s in symbols if VALID_SYMBOL.fullmatch(s)]
    boards = dict(zip(subset["symbol"], subset.get("board", pd.Series("", index=subset.index))))
    if not symbols:
        raise SystemExit("Khong tim thay ma EQUITY; khong su dung danh muc rong")
    STAGING.mkdir(parents=True, exist_ok=True)
    done = current_ledger()
    todo = [s for s in symbols if not all(existing_statement(s, st) for st in STATEMENTS)]
    if not args.retry:
        todo = [s for s in todo if not in_cooldown(done.get(s, {}), args.cooldown_hours)]
    if args.limit:
        todo = todo[:args.limit]
    print(f"AURA BCTC 2023-2025 | EQUITY {len(symbols)} | can bo sung {len(todo)}", flush=True)
    if not todo:
        print("Khong con ma du dieu kien thu ngay; co the dang cooldown.")
    bulk, notes = prefetch_bulk(set(todo)) if todo else ({}, [])
    for note in notes:
        print("Nguon:", note, flush=True)
    total_new = 0
    for i, symbol in enumerate(todo, 1):
        missing = [st for st in STATEMENTS if not existing_statement(symbol, st)]
        sources, details, saved = set(), [], 0
        # First, use a single pre-fetched bulk table for these three files.
        for st in missing:
            raw = bulk.get((symbol, st))
            if raw is None:
                continue
            try:
                wide = prepare_wide(raw)
                if atomic_csv(wide, STAGING / f"{symbol}_{st}.csv"):
                    saved += 1
                sources.add("vnfinancialdata/HSX-HNX")
            except (OSError, ValueError, TypeError, KeyError) as exc:
                details.append(f"{st}:bulk:{type(exc).__name__}")
        still = [st for st in STATEMENTS if not existing_statement(symbol, st)]
        if still:
            fallback = fallback_vnstock(symbol, allow=not args.no_fallback)
            for st in still:
                frame = fallback.get(st)
                if frame is None:
                    continue
                try:
                    wide = prepare_wide(frame)
                    if atomic_csv(wide, STAGING / f"{symbol}_{st}.csv"):
                        saved += 1
                    sources.add("vnstock/financials-unverified")
                except (OSError, ValueError, TypeError, KeyError) as exc:
                    details.append(f"{st}:vnstock:{type(exc).__name__}")
        present = sum(existing_statement(symbol, st) for st in STATEMENTS)
        status = "COMPLETE" if present == 3 else ("PARTIAL" if present > 0 else ("ERROR" if details else "NO_DATA"))
        done[symbol] = {"symbol": symbol, "board": str(boards.get(symbol, "")),
                        "status": status, "saved": str(saved), "files_present": str(present),
                        "sources": " | ".join(sorted(sources)) or done.get(symbol, {}).get("sources", ""),
                        "detail": " | ".join(details)[:300], "attempted_at": iso_now()}
        save_ledger(done)
        total_new += saved
        print(f"[{i}/{len(todo)}] {symbol}: {status} ({present}/3 file; +{saved})", flush=True)
        if not args.no_build and args.build_every and i % args.build_every == 0:
            from build_financial_features import build, catalogue_symbols
            feats, cover = build(STAGING, ROOT / "data" / "fundamentals" / "processed",
                                 symbols=catalogue_symbols(ROOT))
            print(f"Da lam moi bang BCTC so bo sau {i} ma.", flush=True)
        if i < len(todo) and args.pause:
            time.sleep(args.pause)
    present3 = sum(all(existing_statement(sym, st) for st in STATEMENTS) for sym in symbols)
    present1 = sum(any(existing_statement(sym, st) for st in STATEMENTS) for sym in symbols)
    print(f"HOAN THANH DOT: them {total_new} file | it nhat 1 BCTC {present1}/{len(symbols)} | 3 BCTC {present3}/{len(symbols)}")
    print("Nhat ky:", LEDGER)
    print("CHUA xac minh ngay cong bo, ho so bao cao, ty so dinh gia; CHUA kich hoat diem co ban.")
    if not args.no_build:
        from build_financial_features import build, catalogue_symbols
        chosen = catalogue_symbols(ROOT)
        feat, cov = build(STAGING, ROOT / "data" / "fundamentals" / "processed", symbols=chosen)
        usable = feat[(feat["year"].eq(2025)) & (feat["status"].eq("PROVISIONAL_REVIEW_REQUIRED"))]["symbol"].nunique()
        print(f"Tinh lai BCTC so bo: {usable}/{len(chosen)} ma co chi tieu; {len(cov)} ma trong danh muc.")


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("\nDang luu bang BCTC so bo tu cac file da tai...", flush=True)
        try:
            from build_financial_features import build, catalogue_symbols
            build(STAGING, ROOT / "data" / "fundamentals" / "processed",
                  symbols=catalogue_symbols(ROOT))
        except (OSError, ValueError, KeyError, ImportError) as exc:
            print("Chua tao lai duoc BCTC so bo:", type(exc).__name__, flush=True)
        print("Da dung an toan: cac file hoan thanh va nhat ky da duoc luu. Chay lai cung lenh de tiep tuc.")
        raise SystemExit(130)
