"""Check that BatDayStox is reading SSI VNINDEX cache (no trading requests)."""
import sys as _aura_sys
from pathlib import Path as _AuraPath
_aura_sys.path.insert(0, str(_AuraPath(__file__).resolve().parents[2]))  # gốc dự án (file đã chuyển vào scripts/legacy)

from core.data import lay_vnindex, LOI

print("=== BATDAY SSI V3 - VNINDEX SMOKE TEST ===")
vni = lay_vnindex(730)
if vni is None or len(vni) < 50:
    print("[FAIL] SSI VNINDEX unavailable / insufficient data")
    print("Reason:", LOI.get("vnindex", "No further details"))
    raise SystemExit(1)

last = vni.iloc[-1]
ma50 = vni["close"].rolling(50).mean().iloc[-1]
print("[OK] Sessions:", len(vni))
print("[OK] Source:", vni.attrs.get("nguon_chi_so", vni.attrs.get("nguon_gia")))
print("[OK] Mode:", vni.attrs.get("che_do"))
print("[OK] Last date:", last["time"].date())
print("[OK] Last VNINDEX close:", round(float(last["close"]), 2))
print("[OK] MA50:", round(float(ma50), 2))
print("[INFO]", vni.attrs.get("canh_bao", ""))
print("[SUCCESS] SSI VNINDEX -> strategy input ready")
