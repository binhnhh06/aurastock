import sys as _aura_sys
from pathlib import Path as _AuraPath
_aura_sys.path.insert(0, str(_AuraPath(__file__).resolve().parents[2]))  # gốc dự án (file đã chuyển vào scripts/legacy)


import os
import json
from pathlib import Path
from datetime import datetime
from zoneinfo import ZoneInfo

import pandas as pd
from dotenv import load_dotenv
from ssi_sdk import Auth, Config, Data
from ssi_sdk.enums import Board

ROOT = Path(__file__).resolve().parents[2]
OUTPUT = ROOT / "data" / "ssi_cache"
OUTPUT.mkdir(parents=True, exist_ok=True)

load_dotenv(ROOT / ".env", override=True)

# Danh sach tham chieu tu SSI iBoard
# Kiem tra ngay 09/11/2026
# Phai cap nhat sau moi ky co cau VN30
VN30 = """
ACB BID BSR CTG FPT GAS GVR HDB HPG LPB
MBB MCH MSN MWG SAB SHB SSB SSI STB TCB
TCX VCB VHM VIB VIC VJC VNM VPB VPL VRE
""".split()

SOURCE_URL = "https://iboard.ssi.com.vn/"

def main():
    print("=" * 55)
    print("BATDAY SSI - XAC MINH DANH SACH VN30")
    print("=" * 55)

    assert len(VN30) == 30, "Danh sach khong du 30 ma"
    assert len(set(VN30)) == 30, "Danh sach co ma trung"

    config = Config(
        client_id=os.environ["SSI_CLIENT_ID"].strip(),
        api_key=os.environ["SSI_API_KEY"].strip(),
        api_secret=os.environ["SSI_API_SECRET"].strip(),
    )

    with Auth(config) as auth:
        auth.authenticate()
        print("[OK] SSI Auth")

        with Data(auth) as data:
            securities = (
                data.market_data
                .get_securities_info_by_board(Board.HOSE)
            )

            available = {
                str(getattr(s, "symbol", "")).upper().strip()
                for s in securities
            }

            found = [s for s in VN30 if s in available]
            missing = [s for s in VN30 if s not in available]

            print("So ma VN30 tham chieu:", len(VN30))
            print("So ma HOSE xac nhan:", len(found))
            print("So ma khong tim thay:", len(missing))

            if missing:
                print("Danh sach can kiem tra:", missing)
                print("[CANH BAO] Khong ghi file.")
                return

    df = pd.DataFrame({
        "symbol": sorted(VN30)
    })

    df.to_csv(
        OUTPUT / "vn30_symbols.csv",
        index=False,
        encoding="utf-8-sig"
    )

    metadata = {
        "index": "VN30",
        "source": "SSI iBoard - danh sach tham chieu",
        "source_url": SOURCE_URL,
        "reference_date": "2026-11-09",
        "validated_at": datetime.now(
            ZoneInfo("Asia/Ho_Chi_Minh")
        ).isoformat(),
        "validation": (
            "30 ma tham chieu duoc doi chieu "
            "voi danh sach ma tren HOSE qua SSI API. "
            "Khong tu dong xac nhan tu cach VN30."
        ),
        "count": len(VN30)
    }

    with open(
        OUTPUT / "vn30_metadata.json",
        "w",
        encoding="utf-8"
    ) as f:
        json.dump(
            metadata, f,
            ensure_ascii=False,
            indent=2
        )

    print("\n[OK] Da tao vn30_symbols.csv")
    print("[OK] Da tao vn30_metadata.json")
    print("Danh sach:", ", ".join(sorted(VN30)))
    print("\nHOAN THANH!")


if __name__ == "__main__":
    try:
        main()
    except Exception as exc:
        print("[LOI]", type(exc).__name__)
        print("Khong ghi danh sach neu chua xac minh.")
