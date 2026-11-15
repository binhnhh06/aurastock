"""Read-only, position-safe Vnstock ratio period normalizer.

Caution: repeated period column labels (e.g. 16 identical '2018') are legal
in a DataFrame. Always index by *physical column position*, never label.

The returned metrics are UNVERIFIED candidates, NOT eligible for scoring or
historical backtests without publication dates / financial validation.
"""
from __future__ import annotations
from collections import Counter
import math
import pandas as pd

IDENTITY = {'item', 'item_en', 'item_id', 'Unnamed: 0'}
SAMPLE_IDS = ('pe_ratio', 'pb_ratio', 'roe', 'roa', 'dividend_yield', 'market_cap')


def _year(value):
    n = pd.to_numeric(value, errors='coerce')
    try:
        if pd.notna(n) and float(n).is_integer() and 1990 <= float(n) <= 2100:
            return int(n)
    except (TypeError, ValueError):
        pass
    return None


def _quarter(value):
    n = pd.to_numeric(value, errors='coerce')
    try:
        if pd.notna(n) and float(n).is_integer():
            return int(n)
    except (TypeError, ValueError):
        pass
    return None


def _find_row_position(df, item_id):
    """Return row offset for one exact item_id, otherwise None."""
    # Defend against duplicate 'item_id' labels too.
    matching_columns = [i for i, c in enumerate(df.columns) if str(c) == 'item_id']
    if len(matching_columns) != 1:
        return None
    keys = df.iloc[:, matching_columns[0]].astype(str).str.strip().str.lower()
    hits = [i for i, matched in enumerate(keys.eq(item_id.lower())) if matched]
    return hits[0] if len(hits) == 1 else None


def normalize_ratio(df: pd.DataFrame, symbol: str, source: str = 'VCI', recent_year: int = 2025):
    """Return (period_diagnostics, unverified_candidates); never scores.

    Handles repeated dataframe column names using .iloc row and column offsets.
    Year is taken strictly from the 'year' metadata row, not column labels.
    """
    if not isinstance(df, pd.DataFrame) or df.empty:
        return pd.DataFrame([{'symbol': symbol, 'source': source, 'status': 'EMPTY'}]), pd.DataFrame()
    table = df.copy()
    if isinstance(table.columns, pd.MultiIndex):
        return pd.DataFrame([{'symbol': symbol, 'source': source, 'status': 'UNSUPPORTED_MULTIINDEX'}]), pd.DataFrame()

    row_positions = {key: _find_row_position(table, key) for key in ('year', 'quarter', 'ratioType')}
    if any(pos is None for pos in row_positions.values()):
        return pd.DataFrame([{'symbol': symbol, 'source': source, 'status': 'MISSING_METADATA'}]), pd.DataFrame()

    # Physical positions uniquely identify columns, even if labels are identical.
    period_positions = [(pos, str(label)) for pos, label in enumerate(table.columns)
                        if str(label) not in IDENTITY]
    if not period_positions:
        return pd.DataFrame([{'symbol': symbol, 'source': source, 'status': 'NO_PERIOD_COLUMNS'}]), pd.DataFrame()

    records = []
    for pos, label in period_positions:
        y = _year(table.iloc[row_positions['year'], pos])
        q = _quarter(table.iloc[row_positions['quarter'], pos])
        kind = str(table.iloc[row_positions['ratioType'], pos]).strip().upper()
        period = ''
        if y is None:
            status = 'INVALID_YEAR'
        elif kind.endswith('YEAR') and not kind.endswith('TTM'):
            # 'quarter=5' often marks annual ratios in this provider format.
            period = str(y)
            status = 'STRUCTURE_OK'
        elif kind.endswith('TTM') and q in (1, 2, 3, 4):
            period = f'{y}-Q{q}'
            status = 'STRUCTURE_OK'
        else:
            status = 'INVALID_PERIOD_TYPE'
        if status == 'STRUCTURE_OK' and y < recent_year:
            status = 'STALE'
        records.append({'symbol': symbol, 'source': source, 'column_position': pos,
                        'column': label, 'period': period, 'year': y, 'quarter': q,
                        'ratio_type': kind, 'status': status})

    # Duplicate physical columns that describe the same reporting period cannot
    # safely be interpreted as independent observations (even if names differ).
    counts = Counter((r['period'], r['ratio_type']) for r in records if r['period'])
    for row in records:
        if row['period'] and counts[(row['period'], row['ratio_type'])] > 1:
            row['status'] = 'DUPLICATE_PERIOD'

    metric_positions = {key: _find_row_position(table, key) for key in SAMPLE_IDS}
    candidates = []
    for row in records:
        if row['status'] != 'STRUCTURE_OK':
            continue
        out = {'symbol': symbol, 'source': source, 'period': row['period'],
               'column_position': row['column_position'], 'year': row['year'],
               'ratio_type': row['ratio_type'], 'publication_verified': 'NO',
               'eligible_for_backtest': 'NO'}
        for key, metric_row_pos in metric_positions.items():
            val = (pd.to_numeric(table.iloc[metric_row_pos, row['column_position']], errors='coerce')
                   if metric_row_pos is not None else float('nan'))
            try:
                out[key] = float(val) if pd.notna(val) and math.isfinite(float(val)) else float('nan')
            except (TypeError, ValueError):
                out[key] = float('nan')
        candidates.append(out)

    return pd.DataFrame(records), pd.DataFrame(candidates)
