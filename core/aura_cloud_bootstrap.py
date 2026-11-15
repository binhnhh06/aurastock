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



def _save_catalogue_portable(frame, path):
    """Write only verified SSI catalogue fields as a portable, atomic CSV.

    Avoid pandas' mixed object-dtype CSV formatter for the cloud pilot.
    Missing optional fields remain empty. Never fill missing tickers or prices.
    On validation/write failure, preserve any existing catalogue unchanged.
    """
    import csv
    import math
    import re
    import tempfile
    import pandas as pd

    columns = (
        'symbol', 'board', 'name', 'icb_code', 'sector',
        'stock_type', 'asset_class', 'equity_scan', 'last_trading_date',
    )
    required = {'symbol', 'board', 'asset_class'}
    if not isinstance(frame, pd.DataFrame) or frame.empty:
        raise ValueError('CATALOGUE_EMPTY_OR_INVALID')
    if not required.issubset(frame.columns):
        raise ValueError('CATALOGUE_REQUIRED_COLUMNS_MISSING')
    if frame.columns.has_duplicates:
        raise ValueError('CATALOGUE_DUPLICATE_COLUMNS')

    def safe_string(value):
        if value is None:
            return ''
        if isinstance(value, (float, int)) and not isinstance(value, bool):
            try:
                if not math.isfinite(float(value)):
                    return ''
            except (ValueError, OverflowError, TypeError):
                return ''
        try:
            # pd.NA has no bool conversion; stringify explicitly.
            result = str(value).strip()
        except (ValueError, TypeError, UnicodeError):
            return ''
        if result in ('<NA>', 'nan', 'NaN', 'None', 'NaT'):
            return ''
        # The market catalogue has no reason to retain multiline fields.
        return result.replace('\r', ' ').replace('\n', ' ')

    rows = []
    for raw in frame.to_dict(orient='records'):
        item = {col: safe_string(raw.get(col)) for col in columns}
        item['symbol'] = item['symbol'].upper()
        item['board'] = item['board'].upper()
        item['asset_class'] = item['asset_class'].upper()
        if not re.fullmatch(r'[A-Z0-9]{2,12}', item['symbol']):
            raise ValueError('CATALOGUE_INVALID_SYMBOL')
        if not item['board'] or not item['asset_class']:
            raise ValueError('CATALOGUE_INVALID_BOARD_OR_CLASS')
        item['equity_scan'] = (
            'True' if safe_string(raw.get('equity_scan')).lower() in ('true', '1', 'yes')
            else 'False'
        )
        rows.append(item)
    if not rows:
        raise ValueError('CATALOGUE_NO_VALID_ROWS')

    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    temp_name = None
    try:
        # Unique temporary name prevents collisions across cloud sessions.
        with tempfile.NamedTemporaryFile(
            mode='w', suffix='.tmp', prefix='catalogue_',
            dir=str(path.parent), encoding='utf-8-sig', newline='', delete=False,
        ) as f:
            temp_name = f.name
            writer = csv.DictWriter(f, fieldnames=columns, lineterminator='\n')
            writer.writeheader()
            writer.writerows(rows)
        # Verify the saved file before replacing a valid previous catalogue.
        with open(temp_name, encoding='utf-8-sig', newline='') as f:
            reader = csv.DictReader(f)
            if not required.issubset(reader.fieldnames or []):
                raise ValueError('CATALOGUE_WRITTEN_HEADER_INVALID')
            written = list(reader)
            if len(written) != len(rows):
                raise ValueError('CATALOGUE_WRITTEN_ROW_COUNT_MISMATCH')
            if [r['symbol'] for r in written] != [r['symbol'] for r in rows]:
                raise ValueError('CATALOGUE_WRITTEN_SYMBOL_MISMATCH')
        os.replace(temp_name, path)
    finally:
        if temp_name:
            try:
                Path(temp_name).unlink(missing_ok=True)
            except OSError:
                pass
    return len(rows)


class CloudBootstrapError(RuntimeError):
    """Only sanitized, fixed-code diagnostics cross into the Streamlit UI."""

    def __init__(self, stage: str, original_type: str):
        self.stage = stage
        self.original_type = original_type
        super().__init__(stage + ":" + original_type)


def _sync(root, limit=12, *, pause=0.6):
    """One authenticated SSI Data session for the entire pilot batch."""
    stage = "START"
    try:
        stage = "SDK_IMPORT"
        from ssi_sdk import Auth, Data, Config
        stage = "PROJECT_MODULE_IMPORT"
        from core.ssi_universe import collect_market_catalogue
        from scripts.ssi_fetch_symbol import download_with_service

        stage = "CREDENTIALS"
        creds = {k: _setting(k) for k in CREDENTIALS}
        if not all(creds.values()):
            raise RuntimeError("MISSING_SSI_SECRETS")
        stage = "CONFIG"
        config = Config(client_id=creds["SSI_CLIENT_ID"],
                        api_key=creds["SSI_API_KEY"],
                        api_secret=creds["SSI_API_SECRET"])
        ok, errors, idx_ok = [], [], []
        stage = "AUTH_CONTEXT"
        with Auth(config) as auth:
            stage = "AUTHENTICATE"
            auth.authenticate()
            stage = "DATA_CONTEXT"
            with Data(auth) as data:
                stage = "CATALOGUE_API"
                catalogue = collect_market_catalogue(data.market_data)
                stage = "CATALOGUE_SCHEMA"
                catalogue["symbol"] = catalogue["symbol"].astype(str).str.upper()
                # Only show a truthful, bounded, SSI-returned comparison universe.
                stage = "SELECT_EQUITIES"
                usable = catalogue.loc[catalogue["asset_class"].eq("EQUITY")].copy()
                selected = [s for s in PILOT if s in set(usable["symbol"])][:limit]
                if len(selected) < 3:
                    raise RuntimeError("SSI_CATALOGUE_TOO_SMALL_OR_WRONG_SCHEMA")
                # The API returned a full three-board catalogue; retain it all.
                # Pilot limit bounds OHLCV downloads, not the symbol universe.
                stage = "SAVE_CATALOGUE"
                _save_catalogue_portable(catalogue, root / "data" / "ssi_cache" / "market_symbols.csv")
                stage = "DOWNLOAD_STOCK_BARS"
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
                stage = "DOWNLOAD_INDEX_BARS"
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
                "universe_equities": int(catalogue.loc[
                    catalogue["asset_class"].isin(("EQUITY", "EQUITY_CANDIDATE")),
                    "symbol"].nunique()),
                "failed": errors}
    except CloudBootstrapError:
        raise
    except Exception as exc:
        # Do not store, print or display exception values: SDK may echo requests.
        raise CloudBootstrapError(stage, type(exc).__name__) from None


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
        if d.get("diag_version") != "9.2.2" or not _fresh(d, interval):
            d = {"status": "RUNNING", "diag_version": "9.3.0", "attempt_at": datetime.now(TZ).isoformat()}
            _save_state(d)
            try:
                limit = max(3, min(30, int(_setting("AURA_CLOUD_PILOT_LIMIT", "12"))))
                result = _sync(ROOT, limit=limit)
                d.update(result)
            except Exception as exc:
                d["status"] = "ERROR"
                d["error_type"] = getattr(exc, "original_type", type(exc).__name__)
                d["error_stage"] = getattr(exc, "stage", "PILOT_LIMIT_OR_SETTINGS")
                # Never display source exception text; SDK can include request details.
            _save_state(d)
        else:
            d = _read_state()
    try:
        import streamlit as st
        if d.get("status") != "OK":
            stage = str(d.get("error_stage") or d.get("status", "UNKNOWN"))
            kind = str(d.get("error_type") or d.get("status", "UNKNOWN"))
            st.sidebar.warning("SSI cloud chưa đồng bộ: " + stage + " / " + kind)
            failures = d.get("failed", [])
            if isinstance(failures, list) and failures:
                # Errors are internally formatted as symbol:type, never exception text.
                st.sidebar.caption("Mã không có nến: " + ", ".join(
                    str(v)[:45] for v in failures[:3]
                ))
        else:
            total = d.get("universe_equities", "?")
            st.sidebar.caption("SSI EOD cloud · " + str(len(d.get("stock_ok", []))) +
                               " / " + str(total) +
                               " mã ứng viên có nến giá; bản thí điểm, không realtime.")
    except (ImportError, RuntimeError):
        pass
