"""Export exactly what local AURA displays, upload per-symbol private R2.

Usage: python scripts/aura_export_original_bctc_v99.py --symbols FPT --dry-run
       python scripts/aura_export_original_bctc_v99.py --symbols FPT --upload --rights-confirmed
Always keep third-party market/financial redistribution rights in mind.
"""
from __future__ import annotations
import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
from core.aura_original_bctc_v99 import build_document, encode_document, object_key, decode_document


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--symbols", required=True, help="FPT or FPT,SSI,HPG")
    p.add_argument("--dry-run", action="store_true")
    p.add_argument("--upload", action="store_true")
    p.add_argument("--rights-confirmed", action="store_true", help="Confirm you are authorized to store and display provider data through your app")
    args = p.parse_args()
    if args.upload == args.dry_run or (args.upload and not args.rights_confirmed):
        p.error("Choose either --dry-run or --upload --rights-confirmed")
    symbols = list(dict.fromkeys(x.strip().upper() for x in args.symbols.split(",") if x.strip()))
    if not symbols or len(symbols) > 50:
        p.error("Choose 1-50 symbols per batch")
    from core.data import lay_bctc
    from core.analysis import tinh_ty_so
    client = bucket = base = None
    if args.upload:
        from core.aura_r2_market import client as r2_client, prefix, enabled, setting
        if not enabled():
            raise RuntimeError("MISSING_R2_UPLOADER_ENV_IN_CURRENT_TERMINAL")
        client, bucket, base = r2_client(), setting("AURA_R2_BUCKET"), prefix()
    uploaded = 0
    for symbol in symbols:
        try:
            data = lay_bctc(symbol, so_nam=5)
            if not data:
                print("[NO_LOCAL_BCTC]", symbol)
                continue
            doc = build_document(symbol, data)
            blob = encode_document(doc)
            decoded, _ = decode_document(blob, symbol)
            ratio = tinh_ty_so(decoded)
            print("[PARITY-CHECK]", json.dumps({
                "symbol": symbol, "statements": list(decoded),
                "rows": {k: len(v) for k, v in decoded.items()},
                "ratio_rows": len(ratio), "blob_bytes": len(blob),
                "ROE_2025": round(float(ratio.loc["ROE (%)", 2025]), 3)
                    if "ROE (%)" in ratio.index and 2025 in ratio.columns else None,
            }, ensure_ascii=False))
            if args.upload:
                key = object_key(symbol, base)
                client.put_object(Bucket=bucket, Key=key, Body=blob,
                                  ContentType="application/json", ContentEncoding="gzip",
                                  CacheControl="private, max-age=0")
                uploaded += 1
                print("[ORIGINAL-UPLOADED]", symbol, "private R2; not GitHub")
        except Exception as e:
            print("[ERROR]", symbol, type(e).__name__, str(e)[:120])
            raise SystemExit(2)
    if args.upload:
        print("[COMPLETE]", uploaded, "symbols uploaded. Prices and research scores unchanged.")
    else:
        print("[DRY-RUN COMPLETE] No credentials used and no uploads performed.")

if __name__ == "__main__":
    main()
