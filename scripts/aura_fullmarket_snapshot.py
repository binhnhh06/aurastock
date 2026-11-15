"""AURA full-market historical SSI sync and PRIVATE R2 snapshot.

Examples:
 python scripts/aura_fullmarket_snapshot.py status
 python scripts/aura_fullmarket_snapshot.py sync --mode missing --limit 1600 --pause 1.5
 python scripts/aura_fullmarket_snapshot.py sync --mode stale --limit 1600 --pause 1.5
 python scripts/aura_fullmarket_snapshot.py upload
 python scripts/aura_fullmarket_snapshot.py restore

No trading methods and no token output. Does not upload data to GitHub.
"""
from __future__ import annotations
import argparse
import csv
import hashlib
import json
import os
import re
import sys
import tempfile
import time
import zipfile
from datetime import datetime, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from core.aura_r2_market import client, prefix, setting, _quick_info, restore_if_configured

TZ = ZoneInfo("Asia/Ho_Chi_Minh")
SYMBOL = re.compile(r"[A-Z0-9]{2,12}")
INDEXES = ("VNINDEX", "VN30", "HNXINDEX", "UPCOMINDEX")


def load_dotenv(root):
    try:
        from dotenv import load_dotenv as ld
        ld(Path(root) / ".env", override=False)
    except ImportError:
        pass


def equity_symbols(root):
    from core.ssi_universe import screener_symbols
    result = sorted(set(screener_symbols(root, include_candidates=True)))
    return [x for x in result if SYMBOL.fullmatch(x)]


def status(root):
    root = Path(root)
    symbols = equity_symbols(root)
    prices = root / "data" / "ssi_cache" / "ohlcv"
    valid, enough, freshest, dates = 0, 0, "", {}
    for symbol in symbols:
        count, last = _quick_info(prices / (symbol + ".csv"))
        if count:
            valid += 1
            enough += count >= 200
            freshest = max(freshest, last)
            dates[symbol] = (count, last)
    at_latest = sum(n >= 200 and d == freshest for n, d in dates.values())
    report = {"equities": len(symbols), "with_any_bars": valid,
              "with_200_bars": enough, "latest_eod": freshest,
              "with_200_at_latest": at_latest, "not_downloaded": len(symbols)-valid}
    print("[FULL-MARKET]", json.dumps(report, ensure_ascii=False))
    return report


def target_date():
    now = datetime.now(TZ)
    # Weekends and before-market-close; holidays are not inferred.
    if now.hour < 16:
        now -= timedelta(days=1)
    while now.weekday() >= 5:
        now -= timedelta(days=1)
    return now.strftime("%Y-%m-%d")


def _ledger_path(root):
    return Path(root) / "data" / "ssi_cache" / "full_sync_ledger.json"


def _ledger(root):
    try:
        return json.loads(_ledger_path(root).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}


def _write_ledger(root, data):
    out = _ledger_path(root)
    out.parent.mkdir(parents=True, exist_ok=True)
    tmp = out.with_suffix(".tmp")
    tmp.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    os.replace(tmp, out)


def _on_cooldown(item):
    if item.get("status") != "ERROR":
        return False
    try:
        ts = datetime.fromisoformat(item.get("time", ""))
        return (datetime.now(TZ) - ts).total_seconds() < 12 * 3600
    except (ValueError, TypeError):
        return False


def sync_indexes(root, *, days=950, pause=1.5):
    """Supplement the equity snapshot with SSI indices only when stale/missing."""
    from scripts.ssi_fetch_symbol import from_ohlc, persist
    from ssi_sdk.enums import Timeframe
    from ssi_sdk import Auth, Data, Config
    keys = ("SSI_CLIENT_ID", "SSI_API_KEY", "SSI_API_SECRET")
    if any(not os.environ.get(k) for k in keys):
        return
    conf = Config(client_id=os.environ[keys[0]], api_key=os.environ[keys[1]],
                  api_secret=os.environ[keys[2]])
    target = target_date()
    folder = Path(root) / "data" / "ssi_cache" / "ohlcv"
    with Auth(conf) as auth:
        auth.authenticate()
        with Data(auth) as data:
            for sym in INDEXES:
                n, last = _quick_info(folder / f"{sym}.csv")
                if last >= target and n >= 60:
                    continue
                try:
                    from_day = (datetime.strptime(target, "%Y-%m-%d") - timedelta(days=days)).date()
                    candles = data.market_data.get_ohlc_all(
                        symbol=sym, timeframe=Timeframe.DAY_1,
                        from_date=from_day.strftime("%Y/%m/%d 00:00:00"),
                        to_date=target.replace("-", "/") + " 23:59:59",
                        size=1000, ascending=True,
                    )
                    df = from_ohlc(sym, candles)
                    if not df.empty:
                        bars = persist(sym, df, folder / f"{sym}.csv", target)
                        print(f"[INDEX] {sym}: {bars} bars")
                    else:
                        print(f"[INDEX] {sym}: NO_DATA")
                except Exception as exc:
                    print(f"[INDEX] {sym}: {type(exc).__name__}")
                time.sleep(pause)


def sync(root, *, mode, limit, pause, days, dry_run=False):
    if not (1 <= limit <= 2500 and pause >= 1.0 and 250 <= days <= 3000):
        raise ValueError("UNSAFE_SYNC_PARAMETERS")
    from scripts.ssi_fetch_symbol import download_with_service
    symbols = equity_symbols(root)
    if not symbols:
        raise RuntimeError("MISSING_MARKET_CATALOGUE")
    bar_path = Path(root) / "data" / "ssi_cache" / "ohlcv"
    target = target_date()
    ledger = _ledger(root)
    needed = []
    for sym in symbols:
        n, last = _quick_info(bar_path / f"{sym}.csv")
        should = n == 0 if mode == "missing" else n == 0 or last < target
        if should and not _on_cooldown(ledger.get(sym, {})):
            needed.append(sym)
    selected = needed[:limit]
    print(f"[QUEUE] SSI equities={len(symbols)} | target={target} | need={len(needed)} | batch={len(selected)}")
    if dry_run:
        return status(root)
    load_dotenv(root)
    from ssi_sdk import Auth, Data, Config
    keys = ("SSI_CLIENT_ID", "SSI_API_KEY", "SSI_API_SECRET")
    if any(not os.environ.get(k) for k in keys):
        raise RuntimeError("MISSING_SSI_ENVIRONMENT_SECRETS")
    conf = Config(client_id=os.environ["SSI_CLIENT_ID"],
                  api_key=os.environ["SSI_API_KEY"], api_secret=os.environ["SSI_API_SECRET"])
    counts = {"OK": 0, "NO_BARS": 0, "ERROR": 0}
    # Open a new authorized read-only SSI session per chunk, so a long
    # all-market run never relies on a single long-lived access token.
    chunk_size = 25
    for begin in range(0, len(selected), chunk_size):
        chunk = selected[begin:begin + chunk_size]
        try:
            with Auth(conf) as auth:
                auth.authenticate()
                with Data(auth) as data:
                    for offset, sym in enumerate(chunk, begin + 1):
                        state = "ERROR"
                        try:
                            state, n = download_with_service(data, sym, days=days, root=Path(root))
                            state = state if state in counts else "ERROR"
                        except Exception as exc:
                            # Do not print provider messages or tokens.
                            print(f"[{offset}/{len(selected)}] {sym}: {type(exc).__name__}", flush=True)
                        n, dt = _quick_info(bar_path / f"{sym}.csv")
                        if state == "OK" and n == 0:
                            state = "NO_BARS"
                        counts[state] += 1
                        ledger[sym] = {"status": state, "bars": n, "last": dt,
                                       "time": datetime.now(TZ).isoformat(timespec="seconds")}
                        _write_ledger(root, ledger)
                        if offset == 1 or offset % 20 == 0 or offset == len(selected):
                            print(f"[{offset}/{len(selected)}] {sym}: {state}, {n} bars ({dt})", flush=True)
                        if offset != len(selected):
                            time.sleep(pause)
        except Exception as exc:
            print("[SAFE] SSI session failure:", type(exc).__name__, "— progress saved; stop safely")
            break
    print("[COMPLETE]", counts)
    try:
        sync_indexes(root, days=days, pause=pause)
    except Exception as exc:
        print("[INDEX] session failed:", type(exc).__name__)
    return status(root)


def pack(root, path):
    root, path = Path(root), Path(path)
    catalogue = root / "data" / "ssi_cache" / "market_symbols.csv"
    if not catalogue.is_file():
        raise RuntimeError("MISSING_MARKET_CATALOGUE")
    equities = equity_symbols(root)
    if not equities:
        raise RuntimeError("NO_EQUITIES")
    prices = root / "data" / "ssi_cache" / "ohlcv"
    path.parent.mkdir(parents=True, exist_ok=True)
    written, enough, latest = 0, 0, ""
    with zipfile.ZipFile(path, "w", compression=zipfile.ZIP_DEFLATED, compresslevel=6, allowZip64=True) as z:
        z.write(catalogue, "market_symbols.csv")
        for sym in equities:
            file = prices / f"{sym}.csv"
            n, dt = _quick_info(file)
            if n == 0:
                continue
            z.write(file, f"ohlcv/{sym}.csv")
            written += 1
            enough += n >= 200
            latest = max(latest, dt)
        index_count = 0
        for index in INDEXES:
            file = prices / f"{index}.csv"
            n, dt = _quick_info(file)
            if n:
                z.write(file, f"ohlcv/{index}.csv")
                index_count += 1
    if written == 0:
        path.unlink(missing_ok=True)
        raise RuntimeError("NO_PRICE_FILES_TO_PUBLISH")
    sha = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            sha.update(chunk)
    result = {"equities": len(equities), "ohlcv_files": written, "at_least_200": enough, "indices": index_count,
              "as_of": latest, "sha256": sha.hexdigest(), "bytes": path.stat().st_size}
    print("[PACK]", json.dumps(result, ensure_ascii=False))
    return result


def upload(root):
    load_dotenv(root)
    from core.aura_r2_market import enabled
    if not enabled():
        raise RuntimeError("R2_PRIVATE_BUCKET_NOT_CONFIGURED")
    s3 = client()
    with tempfile.TemporaryDirectory(prefix="aura_pack_") as td:
        file = Path(td) / "aura_market.zip"
        details = pack(root, file)
        base, bucket = prefix(), setting("AURA_R2_BUCKET")
        # Fail safe against accidentally shrinking the cloud's full universe.
        try:
            current = json.loads(s3.get_object(
                Bucket=bucket, Key=f"{base}/current.json")["Body"].read(8192))
            if int(current.get("ohlcv_files", 0)) > details["ohlcv_files"]:
                raise RuntimeError("NEW_SNAPSHOT_HAS_FEWER_SYMBOLS_THAN_EXISTING")
        except RuntimeError:
            raise
        except Exception:
            # New bucket or first publish: its manifest does not exist yet.
            pass
        key = f"{base}/snapshots/{details['sha256']}.zip"
        print("[UPLOAD] Sending private snapshot; no SSI CSV is pushed to GitHub.")
        s3.upload_file(str(file), bucket, key,
                       ExtraArgs={"ContentType": "application/zip"})
        current = {**details, "zip_key": key,
                   "published_at": datetime.now(TZ).isoformat(timespec="seconds"),
                   "source": "SSI FastConnect EOD; private storage"}
        s3.put_object(Bucket=bucket, Key=f"{base}/current.json",
                      Body=json.dumps(current, ensure_ascii=False).encode("utf-8"),
                      ContentType="application/json", CacheControl="no-store")
        print("[UPLOADED] private bucket;", details["ohlcv_files"], "symbols, as_of", details["as_of"])
        return current


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("mode", choices=["status", "sync", "upload", "restore", "pack"])
    ap.add_argument("--root", default=str(ROOT))
    ap.add_argument("--limit", type=int, default=1600)
    ap.add_argument("--mode", dest="sync_mode", choices=["missing", "stale"], default="missing")
    ap.add_argument("--pause", type=float, default=1.5)
    ap.add_argument("--days", type=int, default=950)
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--output", default="")
    args = ap.parse_args()
    root = Path(args.root).resolve()
    try:
        if args.mode == "status":
            status(root)
        elif args.mode == "sync":
            sync(root, mode=args.sync_mode, limit=args.limit, pause=args.pause,
                 days=args.days, dry_run=args.dry_run)
        elif args.mode == "pack":
            if not args.output:
                raise ValueError("OUTPUT_REQUIRED")
            pack(root, args.output)
        elif args.mode == "upload":
            upload(root)
        elif args.mode == "restore":
            load_dotenv(root)
            r = restore_if_configured(root, force=True)
            print("[RESTORE]", r.get("status"), "| files=", r.get("count", 0))
            if r.get("status") != "OK":
                return 2
    except Exception as exc:
        print("[ERROR]", type(exc).__name__, "(details hidden to protect credentials)")
        return 2
    return 0

if __name__ == "__main__":
    raise SystemExit(main())
