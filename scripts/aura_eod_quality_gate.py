"""Safe publication gate for AURA's PRIVATE R2 SSI EOD snapshots.

No secrets printed, no orders/trades, no R2 writes. Designed for the V9.5
GitHub Actions job. Verifies that the full-market restore works and prevents
publishing an older, shrunk, or incomplete snapshot when SSI is unavailable.
"""
from __future__ import annotations

import argparse
import json
import os
import sys
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))


class QualityGateError(RuntimeError):
    pass


def evaluate_quality(previous: dict, report: dict, target_day: str) -> tuple[str, str]:
    """Return ('PUBLISH'|'SKIP', reason) or fail closed.

    Designed for a known existing full-market snapshot. Calendar holidays
    without a fresh EOD return failure instead of publishing a false update.
    """
    previous_count = int(previous.get("ohlcv_files", 0))
    previous_enough = int(previous.get("at_least_200", 0))
    previous_date = str(previous.get("as_of", ""))
    current_count = int(report.get("with_any_bars", 0))
    current_enough = int(report.get("with_200_bars", 0))
    current_date = str(report.get("latest_eod", ""))
    current_fresh_enough = int(report.get("with_200_at_latest", 0))

    if previous_count < 100 or previous_enough < 50:
        raise QualityGateError("BASELINE_INVALID")
    if not previous_date or not current_date:
        raise QualityGateError("MISSING_EOD_DATES")
    try:
        old_day = date.fromisoformat(previous_date)
        new_day = date.fromisoformat(current_date)
        target = date.fromisoformat(target_day)
    except ValueError as exc:
        raise QualityGateError("INVALID_EOD_DATE") from exc

    if current_count < max(100, int(previous_count * 0.98)):
        raise QualityGateError("SYMBOL_COVERAGE_DROPPED")
    if current_enough < max(50, int(previous_enough * 0.95)):
        raise QualityGateError("HISTORICAL_COVERAGE_DROPPED")
    if new_day < old_day or new_day > target:
        raise QualityGateError("EOD_DATE_REGRESSED_OR_FUTURE")

    # Same latest EOD AND no coverage gain: avoid redundant uploads & bills.
    if new_day == old_day and current_count <= previous_count and current_enough <= previous_enough:
        if new_day == target:
            return "SKIP", "ALREADY_PUBLISHED"
        # On holidays and missing SSI data, don't pretend EOD was refreshed.
        raise QualityGateError("EOD_NOT_READY_OR_MARKET_HOLIDAY")

    if new_day != target:
        raise QualityGateError("EOD_NOT_READY_OR_MARKET_HOLIDAY")
    if current_fresh_enough < max(100, int(previous_enough * 0.50)):
        raise QualityGateError("NEW_EOD_COVERAGE_TOO_LOW")
    return "PUBLISH", "QUALITY_CHECKS_PASSED"


def get_manifest() -> dict:
    from core.aura_r2_market import client, prefix, setting
    obj = client().get_object(Bucket=setting("AURA_R2_BUCKET"), Key=f"{prefix()}/current.json")
    manifest = json.loads(obj["Body"].read(64_000).decode("utf-8"))
    if not isinstance(manifest, dict) or not manifest.get("zip_key"):
        raise QualityGateError("REMOTE_MANIFEST_INVALID")
    return manifest


def get_status() -> dict:
    from scripts.aura_fullmarket_snapshot import status
    return status(ROOT)


def run(mode: str) -> int:
    from scripts.aura_fullmarket_snapshot import target_date
    old = get_manifest()
    current = get_status()
    if mode == "verify":
        old_count = int(old.get("ohlcv_files", 0))
        if (old_count < 100 or
                int(current.get("with_any_bars", 0)) < max(100, int(old_count * 0.98)) or
                str(current.get("latest_eod", "")) < str(old.get("as_of", ""))):
            raise QualityGateError("RESTORED_SNAPSHOT_INCOMPLETE")
        print("[EOD-GATE] RESTORE_OK", "bars=", current["with_any_bars"], "as_of=", current["latest_eod"])
        return 0

    decision, reason = evaluate_quality(old, current, target_date())
    print("[EOD-GATE]", decision, reason, "bars=", current["with_any_bars"], "as_of=", current["latest_eod"])
    output = os.getenv("GITHUB_OUTPUT")
    if output:
        with open(output, "a", encoding="utf-8") as f:
            f.write(f"publish={'true' if decision == 'PUBLISH' else 'false'}\n")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("mode", choices=("verify", "publish"))
    args = parser.parse_args()
    try:
        return run(args.mode)
    except Exception as exc:
        # Never print provider exceptions, key names or sensitive response bodies.
        reason = str(exc) if isinstance(exc, QualityGateError) else type(exc).__name__
        print("[EOD-GATE] BLOCKED", reason)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
