"""SSI market-wide symbol catalogue: HOSE, HNX, UPCOM. No trading actions."""
from __future__ import annotations
import os
import re
from pathlib import Path
import pandas as pd

ROOT = Path(__file__).resolve().parent.parent
CATALOGUE = ROOT / 'data' / 'ssi_cache' / 'market_symbols.csv'
FALLBACK = ROOT / 'data' / 'ssi_cache' / 'vn30_symbols.csv'
VALID_SYMBOL = re.compile(r'^[A-Z0-9]{2,12}$')

# SSI / legacy FastConnect: ST = stock, CW = warrant, EF = ETF,
# FU = future, BO = bond, OF/MF = open/mutual fund.
NON_EQUITY_TYPES = {
    'CW', 'COVERED WARRANT', 'WARRANT', 'ETF', 'EF', 'ETN',
    'FUND', 'OF', 'MF', 'MUTUAL FUND', 'OPEN-END FUND',
    'BO', 'BOND', 'FU', 'FUTURE', 'DERIVATIVE', 'DERIVATIVES',
}
EQUITY_TYPES = {'ST', 'STOCK', 'STOCKS', 'EQUITY', 'SHARE', 'SHARES', 'COMMON STOCK'}


def _has_text(value):
    return str(value if value is not None else '').strip().upper() not in {
        '', 'NONE', 'NULL', 'NAN', '0', '0.0', 'N/A', '-'
    }


def _positive_number(value):
    try:
        number = float(str(value).strip().replace(',', ''))
        return 0 < number < float('inf')
    except (TypeError, ValueError):
        return False


def classify(item):
    """Conservative SSI security type classification.

    Never treat a zero-valued optional warrant/ETF/derivative field as
    evidence that the security is non-equity.
    """
    typ = str(getattr(item, 'stock_type', None) or '').strip().upper()
    # An explicit underlying security means the record is a warrant,
    # even if the stock_type field is inconsistent.
    if _has_text(getattr(item, 'cw_underlying_symbol', None)):
        return 'NON_EQUITY'

    # Explicit security type takes precedence over generic populated defaults.
    if typ in NON_EQUITY_TYPES or any(
        word in typ for word in ('WARRANT', 'FUND', 'ETF', 'BOND', 'FUTURE', 'DERIV')
    ):
        return 'NON_EQUITY'
    if typ in EQUITY_TYPES or 'COMMON STOCK' in typ:
        return 'EQUITY'

    # No explicit type: infer exclusions only from meaningful payload values.
    if (_has_text(getattr(item, 'cw_underlying_symbol', None))
            or _positive_number(getattr(item, 'cw_exercise_price', None))
            or _positive_number(getattr(item, 'cw_execution_ratio', None))
            or _positive_number(getattr(item, 'i_nav', None))
            or _positive_number(getattr(item, 'open_interest', None))
            or _positive_number(getattr(item, 'settlement_price', None))
            or _has_text(getattr(item, 'maturity_date', None))):
        return 'NON_EQUITY'

    # Positive listed shares suggest an equity, but are not definitive.
    if _positive_number(getattr(item, 'listed_shares', None)):
        return 'EQUITY_CANDIDATE'
    return 'UNKNOWN'


def _board_str(b):
    value = str(getattr(b, 'value', b) or '').upper()
    return value.split('.')[-1]


def collect_market_catalogue(market_data):
    """Returns all returned symbols, with a stock-type classification. No guessed counts."""
    from ssi_sdk.enums import Board
    records = []
    failed = []
    for board in (Board.HOSE, Board.HNX, Board.UPCOM):
        bname = _board_str(board)
        try:
            result = market_data.get_securities_info_by_board(board)
        except Exception as exc:
            failed.append(f'{bname}: {type(exc).__name__}')
            continue
        for it in result or []:
            sym = str(getattr(it,'symbol','') or '').strip().upper()
            if not VALID_SYMBOL.fullmatch(sym):
                continue
            category = classify(it)
            records.append({
                'symbol': sym, 'board': bname,
                'name': getattr(it, 'symbol_name_vi', None) or getattr(it,'symbol_name_en',None) or '',
                'icb_code': getattr(it,'icb_code',None) or '',
                'sector': getattr(it,'icb_name',None) or '',
                'stock_type': getattr(it,'stock_type',None) or '',
                'asset_class': category,
                'equity_scan': category in ('EQUITY','EQUITY_CANDIDATE'),
                'last_trading_date': getattr(it,'last_trading_date',None) or '',
            })
    if failed:
        # Partial catalogue is unsafe to advertise as full market.
        raise RuntimeError('Không thể lấy đầy đủ danh sách sàn: ' + '; '.join(failed))
    if not records:
        raise RuntimeError('SSI không trả về danh sách mã nào')
    df = pd.DataFrame(records)
    df = df.sort_values(['board', 'symbol']).drop_duplicates(['board', 'symbol']).reset_index(drop=True)
    # Safety gate: a large HOSE catalogue with virtually no stocks means
    # the type mapping is incompatible with the API payload. Do not save it.
    hose = df.loc[df['board'].eq('HOSE')]
    eligible = hose['asset_class'].isin(('EQUITY', 'EQUITY_CANDIDATE')).sum()
    if len(hose) >= 200 and eligible < 100:
        common_types = hose['stock_type'].fillna('').value_counts().head(6).to_dict()
        raise RuntimeError(
            f'Phân loại HOSE bất thường: {eligible}/{len(hose)} ứng viên cổ phiếu. '
            f'stock_type phổ biến: {common_types}. Không ghi đè market_symbols.csv.'
        )
    return df


def save_catalogue(df, path=CATALOGUE):
    """Reject partial 1-symbol/one-board SSI snapshots and retain a rollback copy."""
    import shutil
    from datetime import datetime
    path = Path(path)
    if df is None or df.empty or 'symbol' not in df.columns:
        raise ValueError('Danh muc SSI rong hoac thieu cot symbol; khong ghi de')
    fresh = df['symbol'].dropna().astype(str).str.upper().str.strip()
    fresh_n = int(fresh[fresh.ne('')].nunique())
    if fresh_n < 100:
        raise ValueError(f'SSI chi tra {fresh_n} ma: tu choi ghi de danh muc toan thi truong')
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.is_file():
        prior = pd.read_csv(path, encoding='utf-8-sig', keep_default_na=False)
        prior_n = (prior['symbol'].astype(str).str.upper().str.strip().nunique()
                   if 'symbol' in prior else 0)
        if prior_n >= 100 and fresh_n < prior_n * 0.80:
            raise ValueError(f'SSI chi tra {fresh_n}/{prior_n} ma; khong ghi de danh muc cu')
        if prior_n >= 100 and 'board' in df and 'board' in prior:
            previous_boards = set(prior['board'].astype(str).str.upper()) & {'HOSE','HNX','UPCOM'}
            fresh_boards = set(df['board'].astype(str).str.upper())
            if previous_boards - fresh_boards:
                raise ValueError('Du lieu SSI thieu san: ' + ','.join(sorted(previous_boards - fresh_boards)))
        backup = path.parent / f'market_symbols_backup_{datetime.now():%Y%m%d_%H%M%S_%f}.csv'
        shutil.copy2(path, backup)
    tmp = path.with_suffix('.tmp')
    df.to_csv(tmp, index=False, encoding='utf-8-sig')
    os.replace(tmp, path)
    return path



def load_catalogue(root=ROOT):
    file = Path(root) / 'data' / 'ssi_cache' / 'market_symbols.csv'
    if not file.exists():
        return pd.DataFrame(columns=['symbol','board','name','sector','asset_class','equity_scan'])
    df = pd.read_csv(file, encoding='utf-8-sig', keep_default_na=False)
    if 'symbol' not in df:
        raise ValueError('market_symbols.csv thiếu cột symbol')
    df['symbol'] = df['symbol'].astype(str).str.upper().str.strip()
    if 'equity_scan' in df:
        df['equity_scan'] = df['equity_scan'].astype(str).str.lower().isin(('true','1','yes'))
    return df


def screener_symbols(root=ROOT, *, include_candidates=True):
    """Full-market equity candidates when catalogue exists; fallback to VN30 for older installs."""
    data = load_catalogue(root)
    if not data.empty:
        if 'asset_class' in data:
            allowed = ['EQUITY','EQUITY_CANDIDATE'] if include_candidates else ['EQUITY']
            data = data[data['asset_class'].isin(allowed)]
        return data['symbol'].drop_duplicates().tolist()
    old = Path(root) / 'data' / 'ssi_cache' / 'vn30_symbols.csv'
    if old.exists():
        return pd.read_csv(old, encoding='utf-8-sig')['symbol'].dropna().astype(str).str.upper().str.strip().drop_duplicates().tolist()
    return []


def validate_symbol(symbol, root=ROOT):
    symbol = str(symbol or '').upper().strip()
    if not VALID_SYMBOL.fullmatch(symbol):
        raise ValueError('Mã không hợp lệ')
    df = load_catalogue(root)
    if not df.empty and symbol not in df['symbol'].values:
        raise ValueError('Mã không có trong danh sách SSI hiện tại; hãy cập nhật danh sách sàn')
    return symbol
