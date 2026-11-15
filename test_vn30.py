
import os
import re
from pathlib import Path

import pandas as pd
from dotenv import load_dotenv
from ssi_sdk import Auth, Config, Data
from ssi_sdk.enums import Board

ROOT = Path(__file__).resolve().parent
load_dotenv(ROOT / ".env", override=True)

OUTPUT = ROOT / "data" / "ssi_cache"
OUTPUT.mkdir(parents=True, exist_ok=True)


def get_symbols(items):
    """Trích mã cổ phiếu từ danh sách SDK."""
    result = []

    for item in items or []:
        symbol = str(
            getattr(item, "symbol", "") or ""
        ).upper().strip()

        # Chỉ nhận mã cổ phiếu 3 chữ cái
        if re.fullmatch(r"[A-Z]{3}", symbol):
            result.append(symbol)

    return sorted(set(result))


def show_result(name, items):
    items = items or []
    symbols = get_symbols(items)

    print(f"\n{name}")
    print("So ban ghi SDK:", len(items))
    print("So ma 3 ky tu:", len(symbols))
    print("Mau:", symbols[:10])

    return symbols


def main():
    print("=" * 55)
    print("BATDAY SSI - KIEM TRA DANH SACH VN30")
    print("=" * 55)

    config = Config(
        client_id=os.environ["SSI_CLIENT_ID"].strip(),
        api_key=os.environ["SSI_API_KEY"].strip(),
        api_secret=os.environ["SSI_API_SECRET"].strip(),
    )

    candidates = {}

    with Auth(config) as auth:
        auth.authenticate()
        print("[OK] Xac thuc thanh cong")

        with Data(auth) as data:

            # Cach 1: Securities Info by Index
            try:
                items = (
                    data.market_data
                    .get_securities_info_by_index("VN30")
                )

                candidates["info_by_index"] = show_result(
                    "[1] Securities Info by Index",
                    items
                )

                for item in (items or [])[:3]:
                    print(
                        "Chi tiet:",
                        getattr(item, "symbol", None),
                        "| Index:",
                        getattr(item, "index", None)
                    )

            except Exception as exc:
                print(
                    "[1] LOI:",
                    type(exc).__name__
                )

            # Cach 2: Securities Summary by Index
            try:
                items = (
                    data.market_data
                    .get_securities_summary_by_index("VN30")
                )

                candidates["summary_by_index"] = show_result(
                    "[2] Securities Summary by Index",
                    items
                )

            except Exception as exc:
                print(
                    "[2] LOI:",
                    type(exc).__name__
                )

            # Cach 3: Lay HOSE roi loc theo index
            try:
                hose = (
                    data.market_data
                    .get_securities_info_by_board(Board.HOSE)
                )

                print("\n[3] Securities Info by Board")
                print("Tong ban ghi HOSE:", len(hose or []))

                for sec in (hose or [])[:5]:
                    print(
                        "Mau:",
                        getattr(sec, "symbol", None),
                        "| Index:",
                        getattr(sec, "index", None)
                    )

                vn30_items = []

                for sec in hose or []:
                    index_value = getattr(
                        sec, "index", None
                    )

                    tokens = re.findall(
                        r"[A-Z0-9]+",
                        str(index_value or "").upper()
                    )

                    if "VN30" in tokens:
                        vn30_items.append(sec)

                candidates["hose_filter"] = show_result(
                    "HOSE loc theo VN30",
                    vn30_items
                )

            except Exception as exc:
                print(
                    "[3] LOI:",
                    type(exc).__name__
                )

    # Chi chap nhan danh sach dung 30 ma.
    valid = {
        name: symbols
        for name, symbols in candidates.items()
        if len(symbols) == 30
    }

    if not valid:
        print("\n[CANH BAO]")
        print("Chua xac nhan duoc du 30 ma VN30.")
        print("Khong ghi file vn30_symbols.csv.")
        return

    unique_lists = {
        tuple(symbols)
        for symbols in valid.values()
    }

    if len(unique_lists) > 1:
        print("\n[CANH BAO]")
        print("Cac nguon tra ve danh sach khac nhau.")
        print("Can doi chieu truoc khi luu.")
        return

    source, symbols = next(iter(valid.items()))

    pd.DataFrame({
        "symbol": symbols
    }).to_csv(
        OUTPUT / "vn30_symbols.csv",
        index=False,
        encoding="utf-8-sig"
    )

    print("\n[OK] XAC NHAN DU 30 MA VN30")
    print("Nguon:", source)
    print("Danh sach:", ", ".join(symbols))
    print("Da luu vn30_symbols.csv")


if __name__ == "__main__":
    main()
