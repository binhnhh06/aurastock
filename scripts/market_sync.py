"""BatDayStox: incremental SSI EOD sync for the whole equity universe.

Install in <project>/scripts/market_sync.py. Never sends orders.
Examples:
  python scripts/market_sync.py --mode missing --limit 100
  python scripts/market_sync.py --mode missing --limit 100 --dry-run
  python scripts/market_sync.py --mode stale --limit 100

Requires existing core.ssi_universe and scripts.ssi_fetch_symbol modules.
"""
from __future__ import annotations

import argparse
import os
import sys
import time
from datetime import datetime, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

import pandas as pd

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
from core.ssi_universe import screener_symbols
from scripts.ssi_fetch_symbol import download_with_service

TZ = ZoneInfo("Asia/Ho_Chi_Minh")
PRICES = ROOT / "data" / "ssi_cache" / "ohlcv"
LEDGER = ROOT / "data" / "ssi_cache" / "market_sync_status.csv"
FIELDS = ["symbol", "status", "attempted_at", "bars", "last_date", "error"]


def price_summary(symbol: str) -> tuple[int, str]:
    path = PRICES / f"{symbol}.csv"
    if not path.is_file():
        return 0, ""
    try:
        dates = pd.to_datetime(pd.read_csv(path, usecols=["date"])["date"], errors="coerce")
        dates = dates.dropna()
        return len(dates), dates.max().strftime("%Y-%m-%d") if not dates.empty else ""
    except (OSError, ValueError, KeyError, pd.errors.ParserError):
        return 0, ""


def load_ledger() -> dict[str, dict]:
    if not LEDGER.exists():
        return {}
    try:
        df = pd.read_csv(LEDGER, dtype=str, keep_default_na=False)
        if not set(FIELDS).issubset(df.columns):
            return {}
        return {str(r["symbol"]): r.to_dict() for _, r in df.iterrows()}
    except (OSError, pd.errors.ParserError):
        return {}


def save_ledger(items: dict[str, dict]) -> None:
    LEDGER.parent.mkdir(parents=True, exist_ok=True)
    out = pd.DataFrame([items[k] for k in sorted(items)], columns=FIELDS)
    tmp = LEDGER.with_suffix(".tmp")
    out.to_csv(tmp, index=False, encoding="utf-8-sig")
    os.replace(tmp, LEDGER)


def cooldown_active(record: dict | None, now: datetime, hours: float) -> bool:
    if not record or hours <= 0:
        return False
    try:
        prev = datetime.fromisoformat(str(record.get("attempted_at", "")))
        if prev.tzinfo is None:
            prev = prev.replace(tzinfo=TZ)
        return now - prev < timedelta(hours=hours)
    except (ValueError, TypeError):
        return False


def target_date(now: datetime) -> str:
    """Conservative last-completed-business-day target, not a holiday calendar."""
    if now.hour < 15 or (now.hour == 15 and now.minute < 30):
        now = now - timedelta(days=1)
    while now.weekday() >= 5:
        now = now - timedelta(days=1)
    return now.date().isoformat()


def queue_symbols(symbols: list[str], *, mode: str, target: str,
                  ledger: dict[str, dict], now: datetime,
                  cooldown_hours: float) -> list[str]:
    result = []
    for symbol in symbols:
        bars, last = price_summary(symbol)
        if mode == "missing":
            needed = bars == 0
        else:
            needed = bars == 0 or not last or last < target
        if needed and not cooldown_active(ledger.get(symbol), now, cooldown_hours):
            result.append(symbol)
    return result


def coverage(symbols: list[str]) -> dict[str, int | str]:
    summaries = [price_summary(s) for s in symbols]
    dates = [last for bars, last in summaries if bars > 0 and last]
    latest = max(dates) if dates else ""
    return {
        "all_equities": len(symbols),
        "cached": sum(bars > 0 for bars, _ in summaries),
        "at_least_200_bars": sum(bars >= 200 for bars, _ in summaries),
        "latest_date_in_cache": latest,
        "at_least_200_bars_at_latest_date": sum(
            bars >= 200 and last == latest for bars, last in summaries
        ),
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="SSI all-market incremental EOD synchronization")
    parser.add_argument("--mode", choices=["missing", "stale"], default="missing")
    parser.add_argument("--limit", type=int, default=100)
    parser.add_argument("--chunk", type=int, default=20)
    parser.add_argument("--pause", type=float, default=1.5)
    parser.add_argument("--days", type=int, default=900)
    parser.add_argument("--cooldown-hours", type=float, default=12)
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()
    if not (1 <= args.limit <= 1518 * 2 and 1 <= args.chunk <= 100
            and 220 <= args.days <= 3000 and args.pause >= 0
            and args.cooldown_hours >= 0):
        parser.error("Invalid limit/chunk/days/pause/cooldown")

    symbols = screener_symbols(include_candidates=False)
    if not symbols:
        parser.error("Danh mục cổ phiếu trống. Chạy scripts/ssi_sync_universe.py trước.")
    now = datetime.now(TZ)
    cutoff = target_date(now)
    ledger = load_ledger()
    todo = queue_symbols(symbols, mode=args.mode, target=cutoff, ledger=ledger,
                         now=now, cooldown_hours=args.cooldown_hours)
    chosen = todo[:args.limit]
    print(f"Danh mục EQUITY: {len(symbols)} | chế độ: {args.mode} | chốt kiểm tra: {cutoff}")
    print(f"Cần đồng bộ (trừ mã đang cooldown): {len(todo)} | lô này: {len(chosen)}")
    if args.dry_run or not chosen:
        print("Mẫu mã:", ", ".join(chosen[:20]) or "(Không còn mã trong hàng đợi)")
        print("Độ phủ:", coverage(symbols))
        return

    try:
        from dotenv import load_dotenv
        load_dotenv(ROOT / ".env", override=False)
    except ImportError:
        pass
    required = ("SSI_CLIENT_ID", "SSI_API_KEY", "SSI_API_SECRET")
    if any(not os.getenv(k) for k in required):
        parser.error("Thiếu cấu hình SSI trong .env (không in thông tin bí mật)")

    from ssi_sdk import Auth, Config, Data
    config = Config(client_id=os.environ["SSI_CLIENT_ID"],
                    api_key=os.environ["SSI_API_KEY"],
                    api_secret=os.environ["SSI_API_SECRET"])
    totals = {"OK": 0, "NO_BARS": 0, "ERROR": 0}
    for start in range(0, len(chosen), args.chunk):
        batch = chosen[start:start + args.chunk]
        print(f"\n===== LÔ {start // args.chunk + 1}: {len(batch)} MÃ =====", flush=True)
        try:
            with Auth(config) as auth:
                auth.authenticate()
                with Data(auth) as data:
                    for i, symbol in enumerate(batch, start + 1):
                        status, n, err = "ERROR", 0, ""
                        try:
                            status, n = download_with_service(data, symbol, days=args.days)
                        except Exception as exc:
                            err = type(exc).__name__
                        bars, last = price_summary(symbol)
                        status = status if status in totals else "ERROR"
                        totals[status] += 1
                        ledger[symbol] = {"symbol": symbol, "status": status,
                                          "attempted_at": datetime.now(TZ).isoformat(timespec="seconds"),
                                          "bars": bars, "last_date": last, "error": err}
                        save_ledger(ledger)  # Resume even after an interrupted run
                        print(f"[{i}/{len(chosen)}] {symbol}: {status}, {bars} phiên"
                              + (f" ({err})" if err else ""), flush=True)
                        if args.pause and i < len(chosen):
                            time.sleep(args.pause)
        except Exception as exc:
            print(f"Không thể mở phiên SSI cho lô này: {type(exc).__name__}. Dừng an toàn.")
            break

    print("\n===== TỔNG KẾT =====")
    print("OK:", totals["OK"], "| NO_BARS:", totals["NO_BARS"], "| ERROR:", totals["ERROR"])
    print("Độ phủ:", coverage(symbols))
    print("Nhật ký đồng bộ:", LEDGER)
    print("Chạy lại cùng lệnh để lấy tiếp các mã chưa có file (bỏ qua mã vừa lỗi theo cooldown).")


if __name__ == "__main__":
    main()
