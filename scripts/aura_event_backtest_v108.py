# -*- coding: utf-8 -*-
"""Strict next-session event study from EXTERNAL historical signal CSV.

This does NOT invent AURA signals; first replay a frozen historical AURA strategy,
export signals at each past EOD with date/symbol/strategy/confirmed, then run.
This is an event study, NOT a portfolio equity backtest.

Input signals: signal_date,symbol,strategy,confirmed (confirmed=true or 1)
Prices folder: <SYMBOL>.csv with date/time,open,close, optional volume.
Exit: close after holding H trading sessions starting from entry session.
"""
from __future__ import annotations
import argparse
from pathlib import Path
import math
import pandas as pd


def prepare_prices(path: Path) -> pd.DataFrame:
    df = pd.read_csv(path, encoding='utf-8-sig')
    date_col = next((c for c in ('date', 'time', 'Date', 'trading_date') if c in df), None)
    if date_col is None or not {'open','close'}.issubset(df.columns):
        raise ValueError(f'{path.name}: requires date/time, open, close')
    df = df.rename(columns={date_col:'trading_day'})
    df['trading_day'] = pd.to_datetime(df['trading_day'], errors='coerce').dt.normalize()
    for c in ('open','close'):
        df[c] = pd.to_numeric(df[c], errors='coerce')
    df = df.dropna(subset=['trading_day', 'open','close']).sort_values('trading_day')
    if (df[['open','close']] <= 0).any().any():
        raise ValueError(f'{path.name}: nonpositive price')
    if df.trading_day.duplicated().any():
        raise ValueError(f'{path.name}: duplicate trading dates')
    if len(df) < 2:
        raise ValueError(f'{path.name}: too few sessions')
    return df.set_index('trading_day')


def run_event(signals: pd.DataFrame, prices_dir: Path, hold: int,
              buy_fee_bps: float, sell_fee_bps: float, slippage_bps: float) -> pd.DataFrame:
    if hold < 1:
        raise ValueError('holding sessions must be >= 1')
    missing = {'signal_date','symbol','strategy','confirmed'} - set(signals.columns)
    if missing:
        raise ValueError('signals CSV missing ' + str(sorted(missing)))
    sig = signals.copy()
    sig['signal_date'] = pd.to_datetime(sig['signal_date'], errors='coerce').dt.normalize()
    sig['symbol'] = sig['symbol'].astype(str).str.upper().str.strip()
    sig['strategy'] = sig['strategy'].astype(str).str.strip()
    sig['confirmed'] = sig['confirmed'].astype(str).str.strip().str.lower().isin({'true','1','yes','y'})
    sig = sig.dropna(subset=['signal_date'])
    sig = sig[sig.confirmed & sig.symbol.str.fullmatch(r'[A-Z0-9]{2,12}') & (sig.strategy!='')]
    if sig.duplicated(['signal_date','symbol','strategy']).any():
        raise ValueError('duplicate signal records')
    frames = {}
    results = []
    for row in sig.itertuples(index=False):
        if row.symbol not in frames:
            path = prices_dir / (row.symbol + '.csv')
            frames[row.symbol] = prepare_prices(path) if path.exists() else None
        df = frames[row.symbol]
        if df is None:
            results.append(dict(symbol=row.symbol,strategy=row.strategy,signal_date=row.signal_date.date(),
                                status='MISSING_PRICE'))
            continue
        # Entry is STRICTLY AFTER signal date, never on the signal close.
        start = df.index.searchsorted(row.signal_date, side='right')
        exit_ix = start + hold - 1
        if start >= len(df) or exit_ix >= len(df):
            results.append(dict(symbol=row.symbol,strategy=row.strategy,signal_date=row.signal_date.date(),
                                status='INSUFFICIENT_FUTURE_BARS'))
            continue
        entry_date = df.index[start]
        # Skip dates where prices are absent for long periods; this is an event study,
        # not a model for delisted/suspended shares.
        if (entry_date - row.signal_date).days > 10:
            results.append(dict(symbol=row.symbol,strategy=row.strategy,signal_date=row.signal_date.date(),
                                status='LONG_GAP_AFTER_SIGNAL'))
            continue
        open_price = float(df['open'].iloc[start])
        close_price = float(df['close'].iloc[exit_ix])
        gross = close_price / open_price - 1
        buy_cost = (buy_fee_bps + slippage_bps) / 10000.0
        sell_cost = (sell_fee_bps + slippage_bps) / 10000.0
        net = close_price*(1-sell_cost) / (open_price*(1+buy_cost)) - 1
        results.append(dict(symbol=row.symbol,strategy=row.strategy,signal_date=row.signal_date.date(),
                            entry_date=entry_date.date(), exit_date=df.index[exit_ix].date(),
                            hold_sessions=hold,entry_open=open_price,exit_close=close_price,
                            gross_return_pct=100*gross,net_return_pct=100*net,status='OK'))
    return pd.DataFrame(results)


def summarize(results: pd.DataFrame) -> pd.DataFrame:
    if results.empty or 'status' not in results:
        return pd.DataFrame(columns=['strategy','trades','win_rate_pct','avg_net_pct','median_net_pct'])
    valid = results[results.status.eq('OK')]
    if valid.empty:
        return pd.DataFrame(columns=['strategy','trades','win_rate_pct','avg_net_pct','median_net_pct'])
    return (valid.groupby('strategy').agg(trades=('net_return_pct','size'),
              win_rate_pct=('net_return_pct',lambda s: 100*(s>0).mean()),
              avg_net_pct=('net_return_pct','mean'),
              median_net_pct=('net_return_pct','median'))
              .reset_index().round(4))


def main():
    p=argparse.ArgumentParser()
    p.add_argument('--signals',required=True)
    p.add_argument('--prices-dir',required=True)
    p.add_argument('--out-dir',default='reports/backtest_event_v108')
    p.add_argument('--hold',type=int,default=10)
    p.add_argument('--buy-fee-bps',type=float,default=15)
    p.add_argument('--sell-fee-bps',type=float,default=25)
    p.add_argument('--slippage-bps',type=float,default=10)
    args=p.parse_args()
    if min(args.buy_fee_bps,args.sell_fee_bps,args.slippage_bps)<0:
        p.error('Fees cannot be negative')
    signals=pd.read_csv(args.signals,encoding='utf-8-sig')
    details=run_event(signals,Path(args.prices_dir),args.hold,
                      args.buy_fee_bps,args.sell_fee_bps,args.slippage_bps)
    summary=summarize(details)
    dest=Path(args.out_dir)
    dest.mkdir(parents=True,exist_ok=True)
    details.to_csv(dest/'events.csv',index=False,encoding='utf-8-sig')
    summary.to_csv(dest/'summary.csv',index=False,encoding='utf-8-sig')
    print('[EVENT_STUDY]', 'signals=',len(signals),'valid_trades=',
          int(details.status.eq('OK').sum()) if not details.empty else 0)
    print('[REPORT]',str(dest.resolve()))
    print('[IMPORTANT] These are fixed-horizon event results; NOT AURA portfolio backtest, Sharpe or CAGR.')

if __name__=='__main__':
    main()
