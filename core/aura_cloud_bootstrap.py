"""AURA cloud pilot: SSI historical market data only; no trading methods.

Opt-in only via Streamlit Secrets. No credentials, user data or cached SSI
bars are committed to Git. A short on-server cache survives only while the
cloud instance exists. A public deployment requires SSI data-use permission.
"""
from __future__ import annotations

import json
import os
import threading
import time
from datetime import datetime, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

ROOT = Path(__file__).resolve().parent.parent
TZ = ZoneInfo("Asia/Ho_Chi_Minh")
STATE = ROOT / "data" / "ssi_cache" / "cloud_bootstrap_status.json"
LOCK = threading.RLock()
PILOT = (
    "FPT", "HPG", "SSI", "VCB", "TCB", "MBB", "CTG", "SHS", "PVS",
    "VGI", "ACB", "VPB", "BID", "MWG", "VNM", "VHM", "GAS", "STB",
    "SHB", "MSN", "HDB", "VIC", "VRE", "GVR", "TPB", "OCB", "NTP",
    "CTD", "VJC", "REE",
)
INDEXES = ("VNINDEX", "VN30", "HNXINDEX", "UPCOMINDEX")
CREDENTIALS = ("SSI_CLIENT_ID", "SSI_API_KEY", "SSI_API_SECRET")


def _setting(name, default=""):
    # Root-level Streamlit Secrets are configured on Community Cloud, not Git.
    try:
        import streamlit as st
        val = st.secrets.get(name, None)
        if val is not None:
            return str(val).strip()
    except (FileNotFoundError, KeyError, RuntimeError, AttributeError):
        pass
    return os.environ.get(name, default).strip()


def _read_state():
    try:
        d = json.loads(STATE.read_text(encoding="utf-8"))
        return d if isinstance(d, dict) else {}
    except (OSError, ValueError):
        return {}


def _save_state(d):
    STATE.parent.mkdir(parents=True, exist_ok=True)
    tmp = STATE.with_suffix(".tmp")
    tmp.write_text(json.dumps(d, ensure_ascii=False, indent=2), encoding="utf-8")
    tmp.replace(STATE)


def _fresh(state, minutes):
    try:
        last = datetime.fromisoformat(state.get("attempt_at", ""))
        if last.tzinfo is None:
            return False
        return (datetime.now(TZ) - last.astimezone(TZ)) < timedelta(minutes=minutes)
    except (TypeError, ValueError, OverflowError):
        return False


def _download_index(market_data, symbol, root, days=950):
    """Indices are not in the equity catalogue, so do not use validate_symbol."""
    from ssi_sdk.enums import Timeframe
    from scripts.ssi_fetch_symbol import from_ohlc, persist

    now = datetime.now(TZ)
    cutoff = now.date() if now.hour >= 16 else (now - timedelta(days=1)).date()
    since = cutoff - timedelta(days=days)
    candles = market_data.get_ohlc_all(
        symbol=symbol, timeframe=Timeframe.DAY_1,
        from_date=since.strftime("%Y/%m/%d 00:00:00"),
        to_date=cutoff.strftime("%Y/%m/%d 23:59:59"),
        size=1000, ascending=True,
    )
    df = from_ohlc(symbol, candles)
    if df.empty:
        return 0
    path = root / "data" / "ssi_cache" / "ohlcv" / f"{symbol}.csv"
    return persist(symbol, df, path, cutoff)


def _sync(root, limit=12, *, pause=0.6):
    """One authenticated SSI Data session for the entire pilot batch."""
    from ssi_sdk import Auth, Data, Config
    from core.ssi_universe import collect_market_catalogue, save_catalogue
    from scripts.ssi_fetch_symbol import download_with_service

    creds = {k: _setting(k) for k in CREDENTIALS}
    if not all(creds.values()):
        raise RuntimeError("MISSING_SSI_SECRETS")
    config = Config(client_id=creds["SSI_CLIENT_ID"],
                    api_key=creds["SSI_API_KEY"],
                    api_secret=creds["SSI_API_SECRET"])
    ok, errors, idx_ok = [], [], []
    with Auth(config) as auth:
        auth.authenticate()
        with Data(auth) as data:
            catalogue = collect_market_catalogue(data.market_data)
            catalogue["symbol"] = catalogue["symbol"].astype(str).str.upper()
            # Only show a truthful, bounded, SSI-returned comparison universe.
            usable = catalogue.loc[catalogue["asset_class"].eq("EQUITY")].copy()
            selected = [s for s in PILOT if s in set(usable["symbol"])][:limit]
            if len(selected) < 3:
                raise RuntimeError("SSI_CATALOGUE_TOO_SMALL_OR_WRONG_SCHEMA")
            subset = catalogue.loc[catalogue["symbol"].isin(selected)].copy()
            save_catalogue(subset, root / "data" / "ssi_cache" / "market_symbols.csv")
            for symbol in selected:
                try:
                    status, n = download_with_service(data, symbol, days=950, root=root)
                    if status == "OK" and n >= 60:
                        ok.append(symbol)
                    else:
                        errors.append(symbol + ":NO_BARS")
                except Exception as exc:
                    errors.append(symbol + ":" + type(exc).__name__)
                time.sleep(max(0.2, min(float(pause), 3)))
            for symbol in INDEXES:
                try:
                    if _download_index(data.market_data, symbol, root) >= 60:
                        idx_ok.append(symbol)
                    else:
                        errors.append(symbol + ":NO_BARS")
                except Exception as exc:
                    errors.append(symbol + ":" + type(exc).__name__)
                time.sleep(max(0.2, min(float(pause), 3)))
    return {"status": "OK" if ok else "NO_STOCK_BARS",
            "source": "SSI FastConnect V3 (temporary cloud cache)",
            "pilot_symbols": selected, "stock_ok": ok, "index_ok": idx_ok,
            "failed": errors}


def bootstrap_cloud():
    """Call AFTER st.set_page_config, on all three app entrypoints."""
    if _setting("AURA_CLOUD_ALLOW_SSI").lower() not in ("1", "true", "yes"):
        return
    # Avoid leaking SSI keys in exception repr, logs and UI messages.
    # Other legacy app modules read SSI credentials from environment variables.
    # Values never go to Git, stdout or client; Streamlit Secrets remain server-side.
    for key in CREDENTIALS:
        value = _setting(key)
        if value:
            os.environ.setdefault(key, value)
    with LOCK:
        d = _read_state()
        interval = 18 * 60 if d.get("status") == "OK" else 60
        if not _fresh(d, interval):
            d = {"status": "RUNNING", "attempt_at": datetime.now(TZ).isoformat()}
            _save_state(d)
            try:
                limit = max(3, min(30, int(_setting("AURA_CLOUD_PILOT_LIMIT", "12"))))
                result = _sync(ROOT, limit=limit)
                d.update(result)
            except Exception as exc:
                d["status"] = "ERROR"
                d["error_type"] = type(exc).__name__
                # Never display source exception text; SDK can include request details.
            _save_state(d)
        else:
            d = _read_state()
    try:
        import streamlit as st
        if d.get("status") != "OK":
            st.sidebar.warning("SSI cloud chưa đồng bộ được: " + d.get("error_type", d.get("status", "UNKNOWN")))
        else:
            st.sidebar.caption("SSI EOD cloud · bản demo " + str(len(d.get("stock_ok", []))) +
                               " mã; không phải toàn thị trường hay realtime.")
    except (ImportError, RuntimeError):
        pass
