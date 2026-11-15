"""BatDayStox SSI - bổ sung tối đa N năm nến NGÀY cho danh mục cổ phiếu.

Một lệnh cho toàn danh mục, có checkpoint và tiếp tục sau Ctrl+C.
Không tác động X10, Worker, BCTC, danh mục hay luồng đặt lệnh.

    python scripts/ssi_backfill_market.py --years 10
    python scripts/ssi_backfill_market.py --years 10 --dry-run
    python scripts/ssi_backfill_market.py --years 10 --symbols FPT,HPG

Yêu cầu: core.ssi_universe, scripts.ssi_fetch_symbol, ssi-sdk và .env SSI
đã tồn tại trong dự án BatDayStox hiện hành.
"""
from __future__ import annotations

import argparse
import os
import sys
import time
from dataclasses import dataclass
from datetime import date, datetime, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

import pandas as pd

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from core.ssi_universe import screener_symbols, validate_symbol
from scripts.ssi_fetch_symbol import from_ohlc, persist

TZ = ZoneInfo("Asia/Ho_Chi_Minh")
CACHE = ROOT / "data" / "ssi_cache" / "ohlcv"
LEDGER = ROOT / "data" / "ssi_cache" / "history_backfill_status.csv"
FIELDS = [
    "symbol", "status", "attempted_at", "requested_from", "requested_to",
    "oldest_before", "oldest_after", "bars_added", "windows", "error",
]


@dataclass(frozen=True)
class Job:
    symbol: str
    oldest: date
    newest: date
    start: date
    end: date


def cutoff_date(now: datetime) -> date:
    """Không sử dụng giá phiên đang hình thành; ngày nghỉ lễ do SSI quyết định."""
    local = now.astimezone(TZ)
    d = local.date() if (local.hour, local.minute) >= (15, 30) else local.date() - timedelta(days=1)
    while d.weekday() > 4:
        d -= timedelta(days=1)
    return d


def read_cache_dates(symbol: str, cache: Path = CACHE) -> tuple[date, date] | None:
    """Chỉ đọc cột ngày; KHÔNG tự tạo dữ liệu cho mã thiếu lịch sử."""
    path = cache / f"{symbol}.csv"
    if not path.is_file():
        return None
    dates = pd.to_datetime(pd.read_csv(path, usecols=["date"], encoding="utf-8-sig")["date"], errors="coerce")
    if dates.empty or dates.isna().all() or dates.isna().any():
        raise ValueError(f"{symbol}: file cache có ngày không hợp lệ")
    return dates.min().date(), dates.max().date()


def load_ledger(path: Path = LEDGER) -> dict[str, dict[str, str]]:
    if not path.is_file():
        return {}
    df = pd.read_csv(path, dtype=str, encoding="utf-8-sig", keep_default_na=False)
    if not set(FIELDS).issubset(df.columns):
        raise ValueError("Nhật ký backfill không đúng định dạng; dừng để tránh tải lặp")
    return {str(row["symbol"]): row.to_dict() for _, row in df.iterrows()}


def save_ledger(records: dict[str, dict[str, str]], path: Path = LEDGER) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    df = pd.DataFrame([records[s] for s in sorted(records)], columns=FIELDS)
    temp = path.with_suffix(".tmp")
    df.to_csv(temp, index=False, encoding="utf-8-sig")
    os.replace(temp, path)


def complete_for_target(record: dict[str, str] | None, start: date, oldest: date) -> bool:
    """Chỉ bỏ qua lịch sử đã kiểm tra nếu đầu file giá chưa đổi."""
    if not record or record.get("status") not in ("OK", "NO_OLDER_BARS"):
        return False
    try:
        checked = date.fromisoformat(record["requested_from"])
        return checked <= start and record.get("oldest_after") == oldest.isoformat()
    except (ValueError, TypeError, KeyError):
        return False


def cooling_down(record: dict[str, str] | None, now: datetime, hours: float) -> bool:
    if not record or record.get("status") != "ERROR" or hours <= 0:
        return False
    try:
        tried_at = datetime.fromisoformat(record["attempted_at"])
        if tried_at.tzinfo is None:
            tried_at = tried_at.replace(tzinfo=TZ)
        return now - tried_at < timedelta(hours=hours)
    except (ValueError, TypeError, KeyError):
        return False


def plan(symbols: list[str], years: int, cutoff: date, records: dict[str, dict[str, str]],
         now: datetime, cooldown_hours: float, cache: Path = CACHE) -> tuple[list[Job], dict[str, int]]:
    start = (pd.Timestamp(cutoff) - pd.DateOffset(years=years)).date()
    counts = {"COVERED": 0, "PREVIOUSLY_CHECKED": 0, "NO_CACHE": 0,
              "COOLDOWN": 0, "INVALID_CACHE": 0, "NEED_BACKFILL": 0}
    jobs = []
    for symbol in symbols:
        try:
            dates = read_cache_dates(symbol, cache)
        except (OSError, ValueError, KeyError, pd.errors.ParserError):
            counts["INVALID_CACHE"] += 1
            print(f"  Bỏ qua {symbol}: file ngày không đọc được (không chỉnh sửa).")
            continue
        if dates is None:
            counts["NO_CACHE"] += 1
            continue
        oldest, newest = dates
        if oldest <= start:
            counts["COVERED"] += 1
            continue
        record = records.get(symbol)
        if complete_for_target(record, start, oldest):
            counts["PREVIOUSLY_CHECKED"] += 1
            continue
        if cooling_down(record, now, cooldown_hours):
            counts["COOLDOWN"] += 1
            continue
        jobs.append(Job(symbol=symbol, oldest=oldest, newest=newest,
                        start=start, end=oldest - timedelta(days=1)))
    counts["NEED_BACKFILL"] = len(jobs)
    return jobs, counts


def _exception_kind(exc: Exception) -> str:
    """Không ghi thông báo nguyên văn của API/SDK (có thể chứa thông tin nhạy cảm)."""
    code = getattr(exc, "status_code", None)
    return f"{type(exc).__name__} HTTP={code}" if code else type(exc).__name__


def _is_rate_limit(exc: Exception) -> bool:
    code = getattr(exc, "status_code", None)
    name = type(exc).__name__.lower()
    return str(code) == "429" or "ratelimit" in name or "toomanyrequests" in name


def fetch_older_bars(job: Job, service, *, pause: float = 1.5,
                     window_days: int = 600, retries: int = 2,
                     sleep=time.sleep) -> tuple[pd.DataFrame, int]:
    """Lấy phần cũ, không chạm file gốc nếu bất kỳ request nào thất bại.

    600 ngày lịch < 1000 nến giao dịch, ngay cả trên thị trường mở 7 ngày/tuần.
    Giữ nguyên nến ngày; không tự điều chỉnh giá chia tách/cổ tức.
    """
    from ssi_sdk.enums import Timeframe

    segments = []
    windows = 0
    left = job.start
    while left <= job.end:
        right = min(left + timedelta(days=window_days - 1), job.end)
        windows += 1
        for attempt in range(retries + 1):
            try:
                result = service.market_data.get_ohlc_all(
                    symbol=job.symbol,
                    timeframe=Timeframe.DAY_1,
                    from_date=left.strftime("%Y/%m/%d 00:00:00"),
                    to_date=right.strftime("%Y/%m/%d 23:59:59"),
                    size=1000,
                    ascending=True,
                )
                frame = from_ohlc(job.symbol, result)
                if len(frame) >= 1000:
                    raise ValueError("Đạt giới hạn 1000 nến/cửa sổ: không ghi file thiếu")
                if not frame.empty:
                    # Không cho API trả nến vượt cửa sổ hoặc trộn mã ngoài truy vấn.
                    dates = pd.to_datetime(frame["date"], errors="coerce")
                    if dates.isna().any() or (dates.dt.date < left).any() or (dates.dt.date > right).any():
                        raise ValueError("SSI trả ngày nằm ngoài cửa sổ yêu cầu")
                    segments.append(frame)
                print(f"     {left} → {right}: {len(frame)} nến", flush=True)
                sleep(pause)
                break
            except Exception as exc:
                if isinstance(exc, ValueError) or attempt >= retries or _is_rate_limit(exc):
                    raise
                sleep(max(2., pause) * (2 ** attempt))
        left = right + timedelta(days=1)
    if not segments:
        return from_ohlc(job.symbol, []), windows
    return pd.concat(segments, ignore_index=True), windows


def one_symbol(job: Job, service, cutoff: date, *, pause: float, cache: Path = CACHE,
               sleep=time.sleep) -> tuple[str, int, int, date]:
    new, windows = fetch_older_bars(job, service, pause=pause, sleep=sleep)
    if new.empty:
        return "NO_OLDER_BARS", 0, windows, job.oldest
    target = cache / f"{job.symbol}.csv"
    before = len(pd.read_csv(target, usecols=["date"], encoding="utf-8-sig"))
    after = persist(job.symbol, new, target, cutoff)
    oldest_after = read_cache_dates(job.symbol, cache)[0]
    return "OK", max(0, after - before), windows, oldest_after


def _save_status(records, job, status, oldest_after, added, windows, error="", *,
                 path: Path = LEDGER, now=None) -> None:
    now = now or datetime.now(TZ)
    records[job.symbol] = {
        "symbol": job.symbol,
        "status": status,
        "attempted_at": now.isoformat(timespec="seconds"),
        "requested_from": job.start.isoformat(),
        "requested_to": job.end.isoformat(),
        "oldest_before": job.oldest.isoformat(),
        "oldest_after": oldest_after.isoformat(),
        "bars_added": str(added),
        "windows": str(windows),
        "error": error,
    }
    save_ledger(records, path)


def run_batch(args, *, now=None, cache: Path = CACHE,
              ledger_path: Path = LEDGER) -> int:
    now = now or datetime.now(TZ)
    cutoff = cutoff_date(now)
    catalogue = screener_symbols(ROOT, include_candidates=False)
    if not catalogue:
        raise RuntimeError("Chưa có danh mục EQUITY SSI; cần market_symbols.csv")
    if args.symbols:
        wanted = [validate_symbol(s.strip(), ROOT) for s in args.symbols.split(",") if s.strip()]
        valid = set(catalogue)
        invalid = [s for s in wanted if s not in valid]
        if invalid:
            raise ValueError("Mã không nằm trong danh mục EQUITY: " + ", ".join(invalid))
        catalogue = list(dict.fromkeys(wanted))
    records = load_ledger(ledger_path)
    jobs, counts = plan(catalogue, args.years, cutoff, records, now,
                        args.cooldown_hours, cache)
    selected = jobs[:args.limit]
    print(f"Danh mục: {len(catalogue)} mã | Lịch sử yêu cầu: {args.years} năm | Ngày chốt: {cutoff}")
    print("Trạng thái:", ", ".join(f"{k}={v}" for k,v in counts.items()))
    print(f"Cần bổ sung: {len(jobs)} | Đợt này: {len(selected)}")
    print("Mẫu mã:", ", ".join(job.symbol for job in selected[:15]) or "(Không còn mã cần tải)")
    if args.dry_run or not selected:
        return 0

    try:
        from dotenv import load_dotenv
        load_dotenv(ROOT / ".env", override=False)
    except ImportError:
        pass
    required = ("SSI_CLIENT_ID", "SSI_API_KEY", "SSI_API_SECRET")
    if any(not os.getenv(key) for key in required):
        raise RuntimeError("Thiếu SSI_CLIENT_ID / SSI_API_KEY / SSI_API_SECRET trong .env")

    from ssi_sdk import Auth, Config, Data
    cfg = Config(client_id=os.environ["SSI_CLIENT_ID"],
                 api_key=os.environ["SSI_API_KEY"],
                 api_secret=os.environ["SSI_API_SECRET"])
    stats = {"OK": 0, "NO_OLDER_BARS": 0, "ERROR": 0}
    finished = 0
    for pos in range(0, len(selected), args.chunk):
        batch = selected[pos:pos + args.chunk]
        print(f"\n======= LÔ {pos // args.chunk + 1} / {((len(selected)-1)//args.chunk)+1} =======", flush=True)
        try:
            with Auth(cfg) as auth:
                auth.authenticate()
                with Data(auth) as service:
                    for job in batch:
                        try:
                            status, added, windows, new_oldest = one_symbol(
                                job, service, cutoff, pause=args.pause, cache=cache)
                            _save_status(records, job, status, new_oldest, added, windows,
                                         path=ledger_path)
                            stats[status] += 1
                            finished += 1
                            print(f"[{finished}/{len(selected)}] {job.symbol}: {status} | +{added} nến | đầu {new_oldest}", flush=True)
                        except KeyboardInterrupt:
                            print("\nĐã dừng. Các mã HOÀN TẤT trước đó vẫn được giữ trong CSV và nhật ký.")
                            return 130
                        except Exception as exc:
                            kind = _exception_kind(exc)
                            _save_status(records, job, "ERROR", job.oldest, 0, 0,
                                         error=kind, path=ledger_path)
                            stats["ERROR"] += 1
                            finished += 1
                            print(f"[{finished}/{len(selected)}] {job.symbol}: ERROR ({kind})", flush=True)
                            if _is_rate_limit(exc):
                                print("SSI đang giới hạn số request; dừng để tránh tiếp tục gọi API.")
                                print("Có thể chạy lại sau khi hết giới hạn và thời gian chờ lỗi.")
                                return 2
        except KeyboardInterrupt:
            print("\nĐã dừng. Chạy lại cùng lệnh sẽ bỏ qua mã đã xử lý thành công.")
            return 130
        except Exception as exc:
            print(f"Không thể mở phiên SSI cho lô: {_exception_kind(exc)}. Dừng an toàn.")
            return 2
    print("\n===== TỔNG KẾT =====")
    print(" | ".join(f"{k}: {v}" for k, v in stats.items()))
    print("Nhật ký:", ledger_path)
    _, final_counts = plan(catalogue, args.years, cutoff, records, datetime.now(TZ),
                           args.cooldown_hours, cache)
    print("TÌNH TRẠNG SAU ĐỢT:", ", ".join(f"{k}={v}" for k,v in final_counts.items()))
    print("Đã kiểm tra toàn bộ hàng đợi của đợt này; mã đã kiểm tra được bỏ qua lần sau.")
    return 0 if not stats["ERROR"] else 1


def main():
    p = argparse.ArgumentParser(description="SSI: bổ sung lịch sử 10 năm cho toàn bộ cổ phiếu, lưu tiến độ")
    p.add_argument("--years", type=int, default=10, help="Số năm lịch sử mong muốn (3–20); mặc định 10")
    p.add_argument("--limit", type=int, default=2000, help="Số mã tối đa trong một lần chạy; mặc định toàn bộ")
    p.add_argument("--chunk", type=int, default=20, help="Số mã mỗi phiên xác thực SSI; mặc định 20")
    p.add_argument("--pause", type=float, default=1.5, help="Giây nghỉ SAU mỗi request; mặc định 1.5")
    p.add_argument("--cooldown-hours", type=float, default=12, help="Thời gian chờ thử lại mã ERROR; mặc định 12h")
    p.add_argument("--symbols", type=str, default="", help="Chỉ xử lý các mã được chỉ định, ví dụ FPT,HPG")
    p.add_argument("--dry-run", action="store_true", help="Chỉ thống kê, KHÔNG gọi API")
    a = p.parse_args()
    if not (3 <= a.years <= 20 and 1 <= a.limit <= 5000 and
            1 <= a.chunk <= 100 and a.pause >= .5 and a.cooldown_hours >= 0):
        p.error("--years 3..20; --limit 1..5000; --chunk 1..100; --pause >= 0.5; cooldown >= 0")
    try:
        sys.exit(run_batch(a))
    except (OSError, ValueError, RuntimeError) as exc:
        print(f"Không thể chạy: {type(exc).__name__}: {exc if type(exc) in (ValueError,RuntimeError) else 'lỗi file'}")
        sys.exit(2)


if __name__ == "__main__":
    main()
