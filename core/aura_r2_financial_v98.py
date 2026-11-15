"""AURA V9.8: read-only / private R2 financial research snapshot.

Annual 2021-2025 candidate ratios are NOT verified statements and NEVER
become scored fundamentals without independent, dated source checks.
"""
from __future__ import annotations

import csv
import hashlib
import io
import json
import os
import re
import tempfile
import threading
import time
import zipfile
from pathlib import Path

_FILES = {
    'financial_features_annual.csv',
    'aura_quality_by_year.csv',
    'aura_quality_by_symbol.csv',
    'aura_quality_issues.csv',
    'bctc_h1_2026.csv',
}
_ANNUAL = {'symbol', 'year', 'score_eligible', 'source_verified', 'published_at'}
_LOCK = threading.RLock()
_LAST = 0.0
_LAST_STATUS = None


def _validate_annual(raw: bytes):
    if len(raw) > 16 * 1024 * 1024:
        raise ValueError('ANNUAL_TOO_LARGE')
    try:
        value = raw.decode('utf-8-sig')
    except UnicodeDecodeError:
        raise ValueError('ANNUAL_ENCODING') from None
    reader = csv.DictReader(io.StringIO(value, newline=''))
    if not _ANNUAL.issubset(reader.fieldnames or []):
        raise ValueError('ANNUAL_REQUIRED_COLUMNS')
    if len(set(reader.fieldnames or [])) != len(reader.fieldnames or []):
        raise ValueError('ANNUAL_DUPLICATE_COLUMNS')
    rows, seen, verified, eligible = 0, set(), 0, 0
    for row in reader:
        rows += 1
        if rows > 16000:
            raise ValueError('ANNUAL_TOO_MANY_ROWS')
        symbol = (row.get('symbol') or '').strip().upper()
        year = (row.get('year') or '').strip()
        if not re.fullmatch(r'[A-Z0-9]{2,12}', symbol) or year not in {str(y) for y in range(2021, 2026)}:
            raise ValueError('ANNUAL_INVALID_SYMBOL_OR_YEAR')
        if (symbol, year) in seen:
            raise ValueError('ANNUAL_DUPLICATE_SYMBOL_YEAR')
        seen.add((symbol, year))
        source = (row.get('source_verified') or '').strip().upper()
        score = (row.get('score_eligible') or '').strip().upper()
        date = (row.get('published_at') or '').strip()
        if source in {'YES', 'TRUE', '1'}:
            verified += 1
        if score in {'YES', 'TRUE', '1'}:
            # Fail closed rather than publicly misrepresent incomplete audits.
            if source not in {'YES', 'TRUE', '1'} or not re.fullmatch(r'\d{4}-\d{2}-\d{2}', date):
                raise ValueError('ELIGIBLE_WITHOUT_VERIFIED_SOURCE_DATE')
            eligible += 1
    if rows == 0:
        raise ValueError('ANNUAL_EMPTY')
    return {'rows': rows, 'symbols': len({s for s, y in seen}), 'source_verified_rows': verified, 'score_eligible_rows': eligible}


def _archive_files(zip_bytes: bytes, sha256: str):
    if len(zip_bytes) > 20 * 1024 * 1024:
        raise ValueError('ARCHIVE_TOO_LARGE')
    if hashlib.sha256(zip_bytes).hexdigest() != sha256:
        raise ValueError('SHA256_MISMATCH')
    files = {}
    with zipfile.ZipFile(io.BytesIO(zip_bytes)) as z:
        members = z.infolist()
        if len(members) > len(_FILES) or sum(x.file_size for x in members) > 24 * 1024 * 1024:
            raise ValueError('ARCHIVE_UNEXPECTED_SIZE')
        for item in members:
            if item.filename not in _FILES or item.is_dir() or item.filename in files or item.file_size > 16 * 1024 * 1024:
                raise ValueError('ARCHIVE_UNEXPECTED_MEMBER')
            files[item.filename] = z.read(item)
    if 'financial_features_annual.csv' not in files:
        raise ValueError('ANNUAL_MISSING')
    info = _validate_annual(files['financial_features_annual.csv'])
    return files, info


def _settings():
    from core.aura_r2_market import client, enabled, prefix, setting
    if not enabled():
        return None
    return client(), setting('AURA_R2_BUCKET'), prefix()


def restore_if_configured(root: Path, *, force=False):
    """Best effort restore into local ephemeral cache before Streamlit reads CSVs."""
    global _LAST, _LAST_STATUS
    with _LOCK:
        if not force and _LAST_STATUS is not None and time.monotonic() - _LAST < 900:
            return _LAST_STATUS
        configuration = _settings()
        if not configuration:
            return {'status': 'NOT_CONFIGURED'}
        s3, bucket, base = configuration
        try:
            response = s3.get_object(Bucket=bucket, Key=base + '/financial/current.json')
            manifest = json.loads(response['Body'].read(16384))
            key = manifest['zip_key']
            sha256 = manifest['sha256']
            if (not isinstance(key, str) or not re.fullmatch(re.escape(base) + r'/financial/snapshots/[0-9a-f]{64}\.zip', key)
                    or not re.fullmatch(r'[0-9a-f]{64}', sha256)):
                raise ValueError('UNSAFE_FINANCIAL_MANIFEST')
            obj = s3.get_object(Bucket=bucket, Key=key)
            blob = obj['Body'].read(20 * 1024 * 1024 + 1)
            files, info = _archive_files(blob, sha256)
            dst = Path(root) / 'data' / 'fundamentals' / 'processed'
            dst.mkdir(parents=True, exist_ok=True)
            # Stage and validate entire archive before replacing any existing files.
            staged = []
            try:
                for name, raw in files.items():
                    with tempfile.NamedTemporaryFile(dir=str(dst), prefix='.aura_fin_', suffix='.tmp', delete=False) as t:
                        t.write(raw)
                        staged.append((Path(t.name), dst / name))
                for src, target in staged:
                    os.replace(src, target)
            finally:
                for src, _ in staged:
                    src.unlink(missing_ok=True)
            result = {'status': 'OK', 'rows': info['rows'], 'symbols': info['symbols'], 'files': len(files)}
        except Exception as exc:
            # Never leak botocore exception strings, request headers, bucket config, credentials.
            result = {'status': 'ERROR', 'error_type': type(exc).__name__}
        _LAST_STATUS, _LAST = result, time.monotonic()
        return result


def render_symbol_annual(root: Path, symbol: str):
    """Unverified annual candidate ratios shown separately from audited BCTC."""
    import pandas as pd
    import streamlit as st
    symbol = str(symbol or '').strip().upper()
    if not re.fullmatch(r'[A-Z0-9]{2,12}', symbol):
        return False
    source = Path(root) / 'data' / 'fundamentals' / 'processed' / 'financial_features_annual.csv'
    if not source.is_file():
        return False
    try:
        df = pd.read_csv(source, encoding='utf-8-sig', low_memory=False)
        if not {'symbol', 'year', 'score_eligible', 'source_verified', 'published_at'}.issubset(df):
            return False
        df = df.loc[df['symbol'].astype(str).str.upper().str.strip().eq(symbol)].copy()
        if df.empty:
            return False
        columns = {
            'year': 'Năm', 'roe_pct_provisional': 'ROE sơ bộ (%)',
            'roa_pct_provisional': 'ROA sơ bộ (%)',
            'eps_growth_pct_provisional': 'Tăng trưởng EPS sơ bộ (%)',
            'net_margin_pct_provisional': 'Biên LN ròng sơ bộ (%)',
            'gross_margin_pct_provisional': 'Biên LN gộp sơ bộ (%)',
            'liabilities_to_equity_provisional': 'Nợ phải trả/VCSH sơ bộ',
            'source_verified': 'Nguồn đã xác minh', 'published_at': 'Ngày công bố',
            'score_eligible': 'Đủ điều kiện chấm điểm',
        }
        st.subheader('BCTC 2021–2025 · chỉ tiêu xử lý sơ bộ')
        st.caption('Các tỷ số candidate/provisional lấy từ bộ dữ liệu đã xử lý; KHÔNG phải bản BCTC gốc đã xác minh. Không tự động dùng để chấm Smart Rating hoặc backtest.')
        st.dataframe(df[[c for c in columns if c in df]].rename(columns=columns).sort_values('Năm'),
                     hide_index=True, use_container_width=True)
        return True
    except (OSError, ValueError, KeyError, pd.errors.ParserError):
        return False
