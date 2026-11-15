"""Private R2 SSI EOD snapshot restore, before AURA imports market cache.

No data is made public by this module. Never log S3 exception messages, URLs
with credentials, response bodies, or Streamlit secrets.
"""
from __future__ import annotations
import hashlib
import json
import os
import re
import tempfile
import threading
import time
import zipfile
from pathlib import Path

_LOCK = threading.RLock()
_CHECK_AT = 0.0
_STATUS = None
_TTL_SECONDS = 900
_SYMBOL = re.compile(r"[A-Z0-9]{2,12}")
_INDEXES = {"VNINDEX", "VN30", "HNXINDEX", "UPCOMINDEX"}


def setting(name, default=""):
    try:
        import streamlit as st
        v = st.secrets.get(name)
        if v is not None:
            return str(v).strip()
    except (ImportError, FileNotFoundError, KeyError, RuntimeError, AttributeError):
        pass
    return os.getenv(name, default).strip()


def enabled():
    return all(setting(k) for k in (
        "AURA_R2_ENDPOINT", "AURA_R2_BUCKET", "AURA_R2_ACCESS_KEY_ID", "AURA_R2_SECRET_ACCESS_KEY"
    ))


def client():
    import boto3
    from botocore.config import Config
    endpoint = setting("AURA_R2_ENDPOINT")
    from urllib.parse import urlsplit
    u = urlsplit(endpoint)
    if (u.scheme != "https" or not u.hostname or
            not u.hostname.endswith(".r2.cloudflarestorage.com") or
            u.username or u.password or u.query or u.fragment or u.path not in ("", "/")):
        raise ValueError("INVALID_R2_ENDPOINT")
    return boto3.client(
        "s3", region_name="auto", endpoint_url=endpoint,
        aws_access_key_id=setting("AURA_R2_ACCESS_KEY_ID"),
        aws_secret_access_key=setting("AURA_R2_SECRET_ACCESS_KEY"),
        config=Config(retries={"max_attempts": 3, "mode": "standard"},
                      connect_timeout=10, read_timeout=120),
    )


def prefix():
    p = setting("AURA_R2_PREFIX", "aura-eod").strip("/")
    if not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_/-]{0,120}", p) or ".." in p:
        raise ValueError("INVALID_R2_PREFIX")
    return p


def verify_snapshot_archive(path, expected_sha=None):
    """Return (file names, valid archive size); reject path traversal/zip bombs."""
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            h.update(chunk)
    if expected_sha and h.hexdigest() != expected_sha:
        raise ValueError("SHA256_MISMATCH")
    with zipfile.ZipFile(path, "r") as z:
        names = z.namelist()
        if len(names) > 2700 or sum(i.file_size for i in z.infolist()) > 350 * 1024 * 1024:
            raise ValueError("ZIP_TOO_LARGE")
        if "market_symbols.csv" not in names:
            raise ValueError("MISSING_CATALOGUE")
        bars = []
        for n in names:
            if n == "market_symbols.csv":
                continue
            if not n.startswith("ohlcv/") or not n.endswith(".csv"):
                raise ValueError("UNEXPECTED_ARCHIVE_MEMBER")
            symbol = n[len("ohlcv/"):-4]
            if not _SYMBOL.fullmatch(symbol):
                raise ValueError("UNSAFE_ARCHIVE_PATH")
            bars.append(symbol)
        if len(set(bars)) != len(bars):
            raise ValueError("DUPLICATE_ARCHIVE_SYMBOL")
        with z.open("market_symbols.csv") as file:
            header = file.readline(1024).decode("utf-8-sig").lower()
            if "symbol" not in header or "board" not in header:
                raise ValueError("INVALID_CATALOGUE_HEADER")
    return bars, h.hexdigest()


def _quick_info(path):
    """Count bars and last date without loading 1,500 files into RAM."""
    import csv
    import math
    try:
        with open(path, newline="", encoding="utf-8-sig") as f:
            reader = csv.DictReader(f)
            if not {"symbol", "date", "open", "high", "low", "close", "volume"}.issubset(reader.fieldnames or []):
                return 0, ""
            count, last = 0, ""
            for row in reader:
                dt = str(row.get("date", ""))[:10]
                if not re.fullmatch(r"\d{4}-\d{2}-\d{2}", dt):
                    return 0, ""
                try:
                    o,h,l,c,v = (float(row[k]) for k in ("open", "high", "low", "close", "volume"))
                    if not all(math.isfinite(x) for x in (o,h,l,c,v)):
                        return 0, ""
                    if min(o,h,l,c) <= 0 or v < 0 or h < max(o,l,c) or l > min(o,h,c):
                        return 0, ""
                except (TypeError, ValueError, OverflowError):
                    return 0, ""
                count += 1
                if dt > last:
                    last = dt
            return count, last
    except (OSError, UnicodeError, ValueError, TypeError):
        return 0, ""


def install_zip(archive, root, expected_sha=None):
    """Merge validated bars, never delete existing market data."""
    root = Path(root)
    symbols, checksum = verify_snapshot_archive(archive, expected_sha)
    target_root = root / "data" / "ssi_cache"
    prices = target_root / "ohlcv"
    prices.mkdir(parents=True, exist_ok=True)
    updated, verified = 0, set()
    with zipfile.ZipFile(archive, "r") as z:
        with tempfile.TemporaryDirectory(prefix="aura_r2_unpack_") as td:
            tmp = Path(td)
            for symbol in symbols:
                member = f"ohlcv/{symbol}.csv"
                z.extract(member, tmp)
                source = tmp / member
                src_count, src_date = _quick_info(source)
                if not src_count:
                    continue
                verified.add(symbol)
                dest = prices / (symbol + ".csv")
                dst_count, dst_date = _quick_info(dest)
                if dst_date > src_date or (dst_date == src_date and dst_count >= src_count):
                    continue
                # File in the same directory to permit atomic os.replace on cloud.
                temp_path = prices / (".aura_" + symbol + ".tmp")
                try:
                    import shutil
                    shutil.copyfile(source, temp_path)
                    os.replace(temp_path, dest)
                finally:
                    temp_path.unlink(missing_ok=True)
                updated += 1
            catalogue = tmp / "market_symbols.csv"
            z.extract("market_symbols.csv", tmp)
            dest = target_root / "market_symbols.csv"
            # Do not replace a newer/larger catalogue with a smaller sample.
            import pandas as pd
            incoming = pd.read_csv(catalogue, encoding="utf-8-sig", usecols=["symbol"])
            old = pd.read_csv(dest, encoding="utf-8-sig", usecols=["symbol"]) if dest.is_file() else None
            if old is None or incoming.symbol.nunique() >= old.symbol.nunique():
                temp_path = target_root / ".aura_catalogue.tmp"
                try:
                    import shutil
                    shutil.copyfile(catalogue, temp_path)
                    os.replace(temp_path, dest)
                finally:
                    temp_path.unlink(missing_ok=True)
    return {"status": "OK", "count": sum(s not in _INDEXES for s in verified),
            "index_count": sum(s in _INDEXES for s in verified),
            "updated": updated, "sha256": checksum}


def restore_if_configured(root, *, force=False):
    """Load the private snapshot once per running process, TTL 15 min for manifest."""
    global _CHECK_AT, _STATUS
    if not enabled():
        return {"status": "NOT_CONFIGURED", "count": 0}
    with _LOCK:
        now = time.monotonic()
        if not force and _STATUS is not None and now - _CHECK_AT < _TTL_SECONDS:
            return _STATUS
        _CHECK_AT = now
        try:
            s3 = client()
            bucket, base = setting("AURA_R2_BUCKET"), prefix()
            raw = s3.get_object(Bucket=bucket, Key=f"{base}/current.json")["Body"].read(8192)
            m = json.loads(raw)
            key = m.get("zip_key", "")
            sha = m.get("sha256", "")
            if not key.startswith(f"{base}/snapshots/") or not re.fullmatch(r"[0-9a-f]{64}", sha):
                raise ValueError("INVALID_MANIFEST")
            root = Path(root)
            state = root / "data" / "ssi_cache" / "aura_r2_installed.json"
            if state.exists():
                try:
                    old = json.loads(state.read_text(encoding="utf-8"))
                    if old.get("sha256") == sha:
                        _STATUS = {"status": "OK", "count": int(old.get("count", 0)), "updated": 0,
                                   "as_of": m.get("as_of", "")}
                        return _STATUS
                except (OSError, ValueError, TypeError):
                    pass
            with tempfile.NamedTemporaryFile(suffix=".zip", prefix="aura_r2_", delete=False) as f:
                tmp = Path(f.name)
            try:
                s3.download_file(bucket, key, str(tmp))
                info = install_zip(tmp, root, sha)
                state.parent.mkdir(parents=True, exist_ok=True)
                state_tmp = state.with_suffix(".tmp")
                state_tmp.write_text(json.dumps(info), encoding="utf-8")
                os.replace(state_tmp, state)
                _STATUS = {**info, "as_of": m.get("as_of", "")}
            finally:
                tmp.unlink(missing_ok=True)
        except Exception as exc:
            # Do not print exception content: requests may echo confidential headers.
            _STATUS = {"status": "ERROR", "error_type": type(exc).__name__, "count": 0}
        return _STATUS
