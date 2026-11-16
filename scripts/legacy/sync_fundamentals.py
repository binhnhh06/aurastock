"""Thu thap BCTC nam 2023-2025 cho 30 ma, khong ghi de CSV da co.

Nguon: core.data.lay_bctc (vnfinancialdata hoac vnstock fallback).
Khong su dung core.data.lay_ratio do ky du lieu khong hop le.
Khong tao diem dau tu va khong gia dinh ngay cong bo.
"""
from __future__ import annotations
import sys as _aura_sys
from pathlib import Path as _AuraPath
_aura_sys.path.insert(0, str(_AuraPath(__file__).resolve().parents[2]))  # gốc dự án (file đã chuyển vào scripts/legacy)


from datetime import datetime
from pathlib import Path
import time

import pandas as pd

from core.data import lay_bctc

SYMBOLS = (
    "ACB", "BID", "BSR", "CTG", "FPT", "GAS", "GVR", "HDB", "HPG", "LPB",
    "MBB", "MCH", "MSN", "MWG", "SAB", "SHB", "SSB", "SSI", "STB", "TCB",
    "TCX", "VCB", "VHM", "VIB", "VIC", "VJC", "VNM", "VPB", "VPL", "VRE",
)
STATEMENTS = ("balance_sheet", "income_statement", "cash_flow")
YEARS = {"2023", "2024", "2025"}
ROOT = Path(__file__).resolve().parents[2]
OUT = ROOT / "data" / "fundamentals" / "staging"


def prepare_yearly(frame: pd.DataFrame) -> tuple[pd.DataFrame, str]:
    if not isinstance(frame, pd.DataFrame) or frame.empty:
        raise ValueError("Bang BCTC trong")
    if isinstance(frame.columns, pd.MultiIndex):
        raise ValueError("Bang cot nhieu cap; can kiem tra thu cong")
    selected = [c for c in frame.columns if str(c).strip() in YEARS]
    selected_years = [str(c).strip() for c in selected]
    if not selected:
        raise ValueError("Khong tim thay cot nam 2023-2025")
    if len(selected_years) != len(set(selected_years)):
        raise ValueError("Trung cot nam trong BCTC")
    result = frame.loc[:, selected].copy()
    result.columns = selected_years
    result.index.name = "item"
    return result, ",".join(selected_years)


def main() -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    records: list[dict[str, str | int]] = []
    for pos, symbol in enumerate(SYMBOLS, 1):
        print(f"[{pos:02d}/30] {symbol}", flush=True)
        missing_statements = [s for s in STATEMENTS if not (OUT / f"{symbol}_{s}.csv").exists()]
        if not missing_statements:
            print("   SKIP: ca 3 file da co")
            for st in STATEMENTS:
                records.append({"symbol": symbol, "statement": st, "status": "EXISTING_NOT_OVERWRITTEN", "years": "", "rows": "", "file": f"{symbol}_{st}.csv"})
            continue
        try:
            result = lay_bctc(symbol, 6)
            if not isinstance(result, dict):
                raise ValueError("lay_bctc khong tra ve dict")
        except Exception as exc:
            print(f"   ERROR {type(exc).__name__}")
            result = {}
        for st in STATEMENTS:
            file_name = f"{symbol}_{st}.csv"
            dest = OUT / file_name
            if dest.exists():
                status, years, nrows = "EXISTING_NOT_OVERWRITTEN", "", ""
            elif st not in result:
                status, years, nrows = "NO_SOURCE", "", ""
            else:
                try:
                    frame, years = prepare_yearly(result[st])
                    # Nguon CSV goc van duoc giu, khong ghi de khi trung ten.
                    with dest.open("x", encoding="utf-8-sig", newline="") as handle:
                        frame.to_csv(handle)
                    status, nrows = "SAVED_UNVERIFIED", len(frame)
                except FileExistsError:
                    status, years, nrows = "EXISTING_NOT_OVERWRITTEN", "", ""
                except Exception as exc:
                    print(f"   {st}: {type(exc).__name__}")
                    status, years, nrows = "NEEDS_REVIEW", "", ""
            print(f"   {st}: {status} ({years})")
            records.append({"symbol": symbol, "statement": st, "status": status, "years": years, "rows": nrows, "file": file_name})
        # Nhieu nguon bo tro co han che yeu cau; khong gui dong loat.
        if pos < len(SYMBOLS):
            time.sleep(1)

    report = pd.DataFrame(records)
    report["checked_at_local"] = datetime.now().isoformat(timespec="seconds")
    report["source_note"] = "core.data.lay_bctc: nguon bo tro chua xac minh; KHONG PHAI SSI"
    report["score_eligible"] = "NO"
    report.to_csv(OUT / "fundamental_sync_summary.csv", index=False, encoding="utf-8-sig")
    print("\n=== TONG KET 30 MA ===")
    print(report.groupby("status").size().to_string())
    print("Bao cao:", OUT / "fundamental_sync_summary.csv")
    print("Chi thu thap BCTC, CHUA cham diem va CHUA xac minh ngay cong bo.")


if __name__ == "__main__":
    main()
