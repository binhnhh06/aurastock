"""AURA local portfolio ledger — no broker order execution or account integration.

SQLite trades are user-declared facts. Money calculations use Decimal; buys use
moving weighted-average cost, partial sells realize P/L without changing the
remaining per-share basis. Market values are estimates from separately dated SSI.
"""
from __future__ import annotations

from collections import defaultdict
from contextlib import contextmanager
from datetime import date, datetime
from decimal import Decimal, InvalidOperation
from pathlib import Path
import csv
import re
import sqlite3
from zoneinfo import ZoneInfo

VN_TZ = ZoneInfo("Asia/Ho_Chi_Minh")
SYMBOL_RE = re.compile(r"^[A-Z0-9]{2,10}$")
D0 = Decimal("0")
D100 = Decimal("100")


class PortfolioInputError(ValueError):
    pass


def today_vn() -> date:
    return datetime.now(VN_TZ).date()


def normalize_symbol(symbol: str) -> str:
    symbol = str(symbol).strip().upper()
    if not SYMBOL_RE.fullmatch(symbol):
        raise PortfolioInputError("Mã cần gồm 2–10 ký tự chữ/số, ví dụ FPT, HPG, VCB.")
    return symbol


def parse_price(raw: str, *, thousands: bool = True) -> Decimal:
    """Vietnamese decimal comma; '20,84' thousands => 20,840 VND.

    In đồng mode, `20.840` is interpreted as 20,840 and `20840,5` as
    20,840.5. In thousands mode prefer decimal comma (`20,84`).
    """
    s = str(raw).strip().replace(" ", "").replace("\u00a0", "")
    if not s:
        raise PortfolioInputError("Vui lòng nhập giá, ví dụ 20,84 nghìn đồng/CP.")
    if "," in s and "." in s:
        decimal_sep = "," if s.rfind(",") > s.rfind(".") else "."
        thousands_sep = "." if decimal_sep == "," else ","
        s = s.replace(thousands_sep, "").replace(decimal_sep, ".")
    elif "," in s:
        s = s.replace(",", ".")
    elif "." in s and not thousands:
        parts = s.split(".")
        if len(parts) > 1 and parts[0].isdigit() and all(len(p) == 3 and p.isdigit() for p in parts[1:]):
            s = "".join(parts)
    try:
        n = Decimal(s)
    except (InvalidOperation, ValueError):
        raise PortfolioInputError("Giá không hợp lệ. Thử nhập 20,84 (nghìn đồng) hoặc 20.840 (đồng).") from None
    if not n.is_finite() or n <= 0:
        raise PortfolioInputError("Giá phải lớn hơn 0.")
    price = n * (1000 if thousands else 1)
    if price > 50_000_000:
        raise PortfolioInputError("Giá vượt 50 triệu đồng/CP; vui lòng kiểm tra đơn vị.")
    return price


def parse_percent(value) -> Decimal:
    try:
        pct = Decimal(str(value))
    except (InvalidOperation, ValueError):
        raise PortfolioInputError("Phí/thuế không hợp lệ.") from None
    if not pct.is_finite() or pct < 0 or pct >= 20:
        raise PortfolioInputError("Phí/thuế cần từ 0 đến dưới 20%.")
    return pct


@contextmanager
def connect(db: Path):
    db = Path(db)
    db.parent.mkdir(parents=True, exist_ok=True)
    connection = sqlite3.connect(str(db), timeout=10)
    connection.row_factory = sqlite3.Row
    connection.execute("PRAGMA busy_timeout=10000")
    try:
        connection.executescript("""
        CREATE TABLE IF NOT EXISTS watched (
            symbol TEXT PRIMARY KEY, added_at TEXT NOT NULL);
        CREATE TABLE IF NOT EXISTS trades (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            symbol TEXT NOT NULL,
            trade_date TEXT NOT NULL,
            side TEXT NOT NULL CHECK(side IN ('BUY','SELL')),
            quantity INTEGER NOT NULL CHECK(quantity > 0),
            price_vnd TEXT NOT NULL,
            fee_pct TEXT NOT NULL DEFAULT '0',
            tax_pct TEXT NOT NULL DEFAULT '0',
            created_at TEXT NOT NULL);
        CREATE INDEX IF NOT EXISTS idx_trades_symbol_date ON trades(symbol, trade_date, id);
        """)
        yield connection
        connection.commit()
    except Exception:
        connection.rollback()
        raise
    finally:
        connection.close()


def watch(db: Path, symbol: str) -> None:
    sym = normalize_symbol(symbol)
    with connect(db) as conn:
        conn.execute("INSERT OR IGNORE INTO watched(symbol, added_at) VALUES(?,?)",
                     (sym, datetime.now(VN_TZ).isoformat()))


def unwatch(db: Path, symbol: str) -> None:
    sym = normalize_symbol(symbol)
    with connect(db) as conn:
        # Never erase trades; keep history even when a symbol leaves watchlist.
        conn.execute("DELETE FROM watched WHERE symbol=?", (sym,))


def watched_symbols(db: Path) -> list[str]:
    with connect(db) as conn:
        return [r[0] for r in conn.execute("SELECT symbol FROM watched ORDER BY symbol").fetchall()]


def all_trades(db: Path) -> list[dict]:
    with connect(db) as conn:
        return [dict(row) for row in conn.execute(
            "SELECT id,symbol,trade_date,side,quantity,price_vnd,fee_pct,tax_pct,created_at "
            "FROM trades ORDER BY trade_date,id").fetchall()]


def _snapshot(trades: list[dict], *, cutoff: date | None = None) -> dict:
    """Apply recorded transactions, moving weighted-average cost (incl. buy fee)."""
    state = defaultdict(lambda: {"quantity": 0, "cost_basis": D0, "realized": D0,
                                 "buy_count": 0, "sell_count": 0})
    for row in sorted(trades, key=lambda r: (r["trade_date"], int(r["id"]))):
        day = date.fromisoformat(row["trade_date"])
        if cutoff is not None and day > cutoff:
            continue
        sym = normalize_symbol(row["symbol"])
        p = Decimal(str(row["price_vnd"]))
        q = int(row["quantity"])
        fee = Decimal(str(row["fee_pct"])) / D100
        tax = Decimal(str(row["tax_pct"])) / D100
        s = state[sym]
        if row["side"] == "BUY":
            s["quantity"] += q
            s["cost_basis"] += p * q * (1 + fee)
            s["buy_count"] += 1
        elif row["side"] == "SELL":
            if s["quantity"] < q:
                raise PortfolioInputError(
                    f"{sym}: lệnh bán {q} CP vượt số dư {s['quantity']} CP ngày {day:%d/%m/%Y}.")
            allocated = s["cost_basis"] * q / s["quantity"]
            proceeds = p * q * (1 - fee - tax)
            s["realized"] += proceeds - allocated
            s["cost_basis"] -= allocated
            s["quantity"] -= q
            s["sell_count"] += 1
            if s["quantity"] == 0:
                s["cost_basis"] = D0
        else:
            raise PortfolioInputError("Giao dịch không hợp lệ.")
    return dict(state)


def holdings(trades: list[dict], *, cutoff: date | None = None) -> dict:
    return _snapshot(trades, cutoff=cutoff)


def record_trade(db: Path, symbol: str, side: str, quantity: int, price_vnd: Decimal,
                 trade_date: date, fee_pct=0, tax_pct=0) -> int:
    symbol = normalize_symbol(symbol)
    side = str(side).upper()
    if side not in ("BUY", "SELL"):
        raise PortfolioInputError("Chỉ hỗ trợ ghi nhận MUA và BÁN.")
    if isinstance(quantity, bool) or not isinstance(quantity, int) or not (1 <= quantity <= 1_000_000_000):
        raise PortfolioInputError("Số lượng phải là số nguyên dương.")
    if not isinstance(trade_date, date) or trade_date > today_vn():
        raise PortfolioInputError("Ngày giao dịch không được ở tương lai.")
    if trade_date < date(2000, 1, 1):
        raise PortfolioInputError("Ngày giao dịch không hợp lệ.")
    price = Decimal(str(price_vnd))
    if not price.is_finite() or not (D0 < price <= 50_000_000):
        raise PortfolioInputError("Giá giao dịch không hợp lệ.")
    fee, tax = parse_percent(fee_pct), parse_percent(tax_pct)
    if side == "BUY" and tax:
        raise PortfolioInputError("Thuế bán chỉ áp dụng với lệnh BÁN.")
    with connect(db) as conn:
        existing = [dict(r) for r in conn.execute(
            "SELECT id,symbol,trade_date,side,quantity,price_vnd,fee_pct,tax_pct "
            "FROM trades ORDER BY trade_date,id").fetchall()]
        # Simulate inserting after all existing trades of the given day. If a
        # backdated order makes a later SELL impossible, reject atomically.
        candidate = {"id": max([int(r["id"]) for r in existing], default=0) + 1,
                     "symbol": symbol, "trade_date": trade_date.isoformat(),
                     "side": side, "quantity": quantity, "price_vnd": str(price),
                     "fee_pct": str(fee), "tax_pct": str(tax)}
        _snapshot(existing + [candidate])
        cursor = conn.execute(
            "INSERT INTO trades(symbol,trade_date,side,quantity,price_vnd,fee_pct,tax_pct,created_at) "
            "VALUES (?,?,?,?,?,?,?,?)",
            (symbol, trade_date.isoformat(), side, quantity, str(price), str(fee), str(tax),
             datetime.now(VN_TZ).isoformat()))
        conn.execute("INSERT OR IGNORE INTO watched(symbol, added_at) VALUES(?,?)",
                     (symbol, datetime.now(VN_TZ).isoformat()))
        return int(cursor.lastrowid)


def delete_trade(db: Path, trade_id: int) -> None:
    """Correct mistakes only when the remaining ledger is still valid."""
    with connect(db) as conn:
        rows = [dict(r) for r in conn.execute(
            "SELECT id,symbol,trade_date,side,quantity,price_vnd,fee_pct,tax_pct "
            "FROM trades ORDER BY trade_date,id").fetchall()]
        if not any(int(r["id"]) == int(trade_id) for r in rows):
            raise PortfolioInputError("Không tìm thấy giao dịch cần xóa.")
        _snapshot([r for r in rows if int(r["id"]) != int(trade_id)])
        conn.execute("DELETE FROM trades WHERE id=?", (int(trade_id),))


def symbol_price_history(root: Path, symbol: str) -> dict[date, Decimal]:
    """Load local SSI EOD for charting; no API calls and no price fabrication."""
    symbol = normalize_symbol(symbol)
    source = Path(root) / "data" / "ssi_cache" / "ohlcv" / f"{symbol}.csv"
    if not source.is_file():
        return {}
    out = {}
    try:
        with source.open("r", encoding="utf-8-sig", newline="") as fh:
            for row in csv.DictReader(fh):
                raw_date = str(row.get("date") or row.get("time") or "").strip()[:10].replace("/", "-")
                try:
                    day = date.fromisoformat(raw_date)
                    close = Decimal(str(row["close"]))
                except (ValueError, InvalidOperation, KeyError, TypeError):
                    continue
                if close.is_finite() and close > 0:
                    # Follow AURA's existing daily-CSV VND price convention.
                    out[day] = close * 1000 if close < 1000 else close
    except (OSError, UnicodeError, csv.Error):
        return {}
    return out


def current_eod(root: Path, symbol: str):
    prices = symbol_price_history(root, symbol)
    if not prices:
        return None, None
    most_recent = max(prices)
    return prices[most_recent], most_recent


def daily_pnl_series(trades: list[dict], price_history: dict[str, dict[date, Decimal]],
                     *, end_date: date | None = None, max_days: int = 3650) -> tuple[list[dict], list[str]]:
    """Daily realized + unrealized P/L from user-recorded trades and dated SSI EOD.

    No BUY/SELL => no series (watch-only has 0 cost / P&L).
    Dates between market sessions use the last *available* SSI EOD close;
    future corporate action adjustments and dividends are not modeled.
    """
    if not trades:
        return [], []
    end = min(end_date or today_vn(), today_vn())
    first = min(date.fromisoformat(t["trade_date"]) for t in trades)
    if first > end:
        return [], []
    # Computation respects entire trade history, even if display is trimmed.
    import pandas as pd
    all_days = pd.date_range(first, end, freq="D")
    last_close = {}
    i = {sym: 0 for sym in price_history}
    lists = {sym: sorted(series.items()) for sym, series in price_history.items()}
    by_day = defaultdict(list)
    for row in trades:
        by_day[date.fromisoformat(row["trade_date"])].append(row)
    sorted_history = []
    held_state = defaultdict(lambda: {"quantity": 0, "cost_basis": D0, "realized": D0})
    warnings = set()
    last_valid_total = None
    for ts in all_days:
        day = ts.date()
        for sym, pairs in lists.items():
            idx = i[sym]
            while idx < len(pairs) and pairs[idx][0] <= day:
                last_close[sym] = pairs[idx][1]
                idx += 1
            i[sym] = idx
        for row in sorted(by_day.get(day, []), key=lambda t: int(t["id"])):
            sym = row["symbol"]
            state = held_state[sym]
            qty = int(row["quantity"])
            px = Decimal(str(row["price_vnd"]))
            fee = Decimal(str(row["fee_pct"])) / D100
            tax = Decimal(str(row["tax_pct"])) / D100
            if row["side"] == "BUY":
                state["quantity"] += qty
                state["cost_basis"] += px * qty * (1 + fee)
            else:
                if qty > state["quantity"]:
                    raise PortfolioInputError("Lịch sử giao dịch chứa lệnh bán vượt số dư.")
                allocated = state["cost_basis"] * qty / state["quantity"]
                state["realized"] += qty * px * (1 - fee - tax) - allocated
                state["cost_basis"] -= allocated
                state["quantity"] -= qty
                if state["quantity"] == 0:
                    state["cost_basis"] = D0
        realized = sum((v["realized"] for v in held_state.values()), D0)
        unrealized = D0
        complete = True
        for sym, state in held_state.items():
            if state["quantity"] > 0:
                if sym not in last_close:
                    warnings.add(sym)
                    complete = False
                else:
                    unrealized += state["quantity"] * last_close[sym] - state["cost_basis"]
        total = (realized + unrealized) if complete else None
        delta = (total - last_valid_total if last_valid_total is not None else total) if total is not None else None
        if total is not None:
            last_valid_total = total
        sorted_history.append({"Ngày": day, "Lãi/lỗ lũy kế (VND)": float(total) if total is not None else None,
                               "Thay đổi P/L ngày (VND)": float(delta) if delta is not None else None,
                               "Đã thực hiện (VND)": float(realized),
                               "Tạm tính (VND)": float(unrealized) if complete else None})
    return sorted_history[-max_days:], sorted(warnings)
