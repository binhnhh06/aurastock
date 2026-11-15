"""Small local, single-installation watchlist for BatDayStox.

Data is saved only on the user's computer in data/user/watchlist.json.
Do not use as independent per-user storage on a public multi-user server.
No remote calls, no SSI credentials, and no trading actions.
"""
from __future__ import annotations

import json
import os
import re
from pathlib import Path
from typing import Iterable

DEFAULT_ROOT = Path(__file__).resolve().parent.parent
VALID = re.compile(r"^[A-Z0-9]{2,12}$")
MAX_ITEMS = 100


def _path(root: Path | None = None) -> Path:
    return Path(root or DEFAULT_ROOT) / "data" / "user" / "watchlist.json"


def normalize(symbols: Iterable[str]) -> list[str]:
    if isinstance(symbols, str):
        symbols = [symbols]
    result = []
    for sym in symbols:
        name = str(sym).upper().strip()
        if VALID.fullmatch(name) and name not in result:
            result.append(name)
        if len(result) >= MAX_ITEMS:
            break
    return result


def load_watchlist(root: Path | None = None) -> list[str]:
    path = _path(root)
    if not path.is_file():
        return []
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
        return normalize(raw.get("symbols", []) if isinstance(raw, dict) else raw)
    except (OSError, ValueError, TypeError):
        return []


def save_watchlist(symbols: Iterable[str], root: Path | None = None) -> list[str]:
    normalized = normalize(symbols)
    target = _path(root)
    target.parent.mkdir(parents=True, exist_ok=True)
    tmp = target.with_suffix(".tmp")
    try:
        tmp.write_text(json.dumps({"version": 1, "symbols": normalized}, ensure_ascii=False, indent=2), encoding="utf-8")
        os.replace(tmp, target)
    finally:
        if tmp.exists():
            tmp.unlink()
    return normalized
