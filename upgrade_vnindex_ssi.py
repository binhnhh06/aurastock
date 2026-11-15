"""One-time, idempotent BatDayStox SSI V3 VNINDEX integration.

Run from the *new* batday_ssi_project directory:
    .\\.venv\\Scripts\\python.exe upgrade_vnindex_ssi.py

Never modifies stock_analyzer remote or .env; preserves other data.py functions.
"""
from __future__ import annotations

import re
import shutil
from datetime import datetime
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parent
DATA_PY = ROOT / "core" / "data.py"
PIPELINE_PY = ROOT / "core" / "pipeline.py"
ADAPTER_PY = ROOT / "core" / "ssi_adapter.py"
RAW_CSV = ROOT / "data" / "ssi_cache" / "vnindex_ohlcv_ssi.csv"
DEST_CSV = ROOT / "data" / "ssi_cache" / "ohlcv" / "VNINDEX.csv"

VNINDEX_IMPL = '''def lay_vnindex(so_ngay=730):
    """Lay VN-Index qua SSI V3 (cache hoac API), giu contract DataFrame/None.

    Khong tu dong chuyen sang DNSE/Vnstock. Khi SSI khong san sang,
    ket qua None va LOI["vnindex"] ghi lai ly do, khong gia vo co du lieu.
    """
    try:
        from core.ssi_adapter import lay_gia_ssi
        refresh = os.getenv("BATDAY_SSI_INDEX_REFRESH", "0").strip() == "1"
        vni = lay_gia_ssi("VNINDEX", so_ngay=so_ngay, refresh=refresh)
        vni.attrs["nguon_chi_so"] = "SSI FastConnect V3"
        LOI.pop("vnindex", None)
        return vni
    except Exception as exc:
        LOI["vnindex"] = (
            f"Khong lay duoc VN-Index tu SSI: {type(exc).__name__}. "
            "Kiem tra data/ssi_cache/ohlcv/VNINDEX.csv hoac quyen API."
        )
        return None


'''

PATTERN = re.compile(r"(?ms)^def lay_vnindex\(so_ngay=730\):\n.*?(?=^def lay_bctc\()")
PIPELINE_OLD = '''"nguon_vni": "DNSE / vnstock (nguồn bổ trợ, chưa chuyển SSI)"'''
PIPELINE_NEW = '''"nguon_vni": (
                vni.attrs.get("nguon_chi_so", vni.attrs.get("nguon_gia", "SSI FastConnect V3"))
                if isinstance(vni, pd.DataFrame) and not vni.empty
                else "VN-Index SSI: không có dữ liệu"
            )'''


def validate_csv(path: Path):
    df = pd.read_csv(path)
    required = {"time", "open", "high", "low", "close", "volume"}
    missing = required - set(df.columns)
    if missing:
        raise ValueError("CSV thiếu cột: " + ", ".join(sorted(missing)))
    if len(df) < 60:
        raise ValueError("CSV chưa đủ 60 phiên VNINDEX")
    df["time"] = pd.to_datetime(df["time"], errors="coerce")
    for col in ("open", "high", "low", "close", "volume"):
        df[col] = pd.to_numeric(df[col], errors="coerce")
    if df[["time", "open", "high", "low", "close", "volume"]].isna().any().any():
        raise ValueError("CSV có ngày hoặc số liệu không hợp lệ")
    if df["time"].dt.normalize().duplicated().any():
        raise ValueError("CSV có ngày giao dịch trùng")
    if (df[["open", "high", "low", "close"]] <= 0).any().any() or (df["volume"] < 0).any():
        raise ValueError("CSV có giá/khối lượng âm hoặc bằng 0")
    if (df["high"] < df[["open", "low", "close"]].max(axis=1)).any():
        raise ValueError("Giá high không hợp lệ")
    if (df["low"] > df[["open", "high", "close"]].min(axis=1)).any():
        raise ValueError("Giá low không hợp lệ")
    return df.sort_values("time").reset_index(drop=True)


def main():
    print("=== BATDAY SSI V3 - CHUYEN VNINDEX SANG SSI ===")
    for path in (DATA_PY, PIPELINE_PY, ADAPTER_PY, RAW_CSV):
        if not path.is_file():
            raise FileNotFoundError(f"Thieu file bat buoc: {path.relative_to(ROOT)}")

    raw = validate_csv(RAW_CSV)
    print(f"[OK] CSV SSI: {len(raw)} phien, tu {raw['time'].iloc[0].date()} den {raw['time'].iloc[-1].date()}")
    source = DATA_PY.read_text(encoding="utf-8")
    pipeline = PIPELINE_PY.read_text(encoding="utf-8")
    was_patched = "vni.attrs[\"nguon_chi_so\"] = \"SSI FastConnect V3\"" in source
    if not was_patched:
        new_data, count = PATTERN.subn(lambda _: VNINDEX_IMPL, source)
        if count != 1:
            raise RuntimeError("Khong tim thay duy nhat ham lay_vnindex truoc def lay_bctc; chua sua code")
    else:
        new_data = source

    if PIPELINE_OLD in pipeline:
        new_pipeline = pipeline.replace(PIPELINE_OLD, PIPELINE_NEW, 1)
    elif PIPELINE_NEW in pipeline:
        new_pipeline = pipeline
    else:
        raise RuntimeError("Cau truc nguon_vni trong pipeline.py khong khop ban patch; chua sua code")

    existing = None
    if DEST_CSV.is_file():
        existing = validate_csv(DEST_CSV)
    should_copy = existing is None or existing["time"].iloc[-1] < raw["time"].iloc[-1]

    backup = ROOT.parent / "batday_ssi_backup" / ("vnindex_" + datetime.now().strftime("%Y%m%d_%H%M%S"))
    backup.mkdir(parents=True, exist_ok=True)
    shutil.copy2(DATA_PY, backup / "data.py")
    shutil.copy2(PIPELINE_PY, backup / "pipeline.py")

    if should_copy:
        DEST_CSV.parent.mkdir(parents=True, exist_ok=True)
        # Copy validated source byte-for-byte, preserving the SSI-origin CSV.
        shutil.copy2(RAW_CSV, DEST_CSV)
        print(f"[OK] Tao cache: {DEST_CSV.relative_to(ROOT)}")
    else:
        print("[OK] Cache VNINDEX hien tai moi hon/tuong duong; khong ghi de")

    if new_data != source:
        DATA_PY.write_text(new_data, encoding="utf-8")
        print("[OK] Da cap nhat lay_vnindex trong core/data.py")
    else:
        print("[OK] core/data.py da dung SSI, khong sua lai")
    if new_pipeline != pipeline:
        PIPELINE_PY.write_text(new_pipeline, encoding="utf-8")
        print("[OK] Da cap nhat nhan nguon SSI trong core/pipeline.py")
    else:
        print("[OK] core/pipeline.py da co nhan nguon SSI")

    compile(DATA_PY.read_text(encoding="utf-8"), str(DATA_PY), "exec")
    compile(PIPELINE_PY.read_text(encoding="utf-8"), str(PIPELINE_PY), "exec")
    print("[OK] Kiem tra cu phap thanh cong")
    print("[BACKUP]", backup)
    print("\nTiep theo chay:")
    print(r'  .\.venv\Scripts\python.exe -c "from core.data import lay_vnindex; x=lay_vnindex(730); print(x.attrs if x is not None else \"NO DATA\"); print(x.tail(2).to_string(index=False) if x is not None else \"\")"')


if __name__ == "__main__":
    main()
