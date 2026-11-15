"""Read-only private R2 foreign-flow data for public Streamlit pages.

No SSI API calls and no credentials or R2 exceptions are exposed to visitors.
"""
from __future__ import annotations

import io
import pandas as pd

_MAX = 8 * 1024 * 1024


def _normalize_csv(data: bytes) -> pd.DataFrame:
    from core.aura_macro_foreign import FLOW_COLUMNS
    if not data or len(data) > _MAX:
        return pd.DataFrame(columns=FLOW_COLUMNS)
    frame = pd.read_csv(io.BytesIO(data), encoding="utf-8-sig", dtype={"scope": str, "code": str})
    if not {"scope", "code", "date", "source"}.issubset(frame.columns):
        return pd.DataFrame(columns=FLOW_COLUMNS)
    for col in FLOW_COLUMNS:
        if col not in frame.columns:
            frame[col] = float("nan") if col.endswith("_vnd") or col.endswith("_volume") else ""
    frame = frame[FLOW_COLUMNS].copy()
    frame["scope"] = frame["scope"].astype(str).str.strip().str.upper()
    frame["code"] = frame["code"].astype(str).str.strip().str.upper()
    frame["date"] = pd.to_datetime(frame["date"], errors="coerce").dt.normalize()
    frame["source"] = frame["source"].fillna("").astype(str).str.strip()
    for col in ("buy_value_vnd", "sell_value_vnd", "net_value_vnd",
                "buy_volume", "sell_volume", "net_volume"):
        frame[col] = pd.to_numeric(frame[col], errors="coerce")
    ok = (frame["date"].notna() & frame["source"].ne("") &
          frame["scope"].isin(("INDEX", "STOCK")) &
          frame["code"].str.fullmatch(r"[A-Z0-9]{2,12}"))
    frame = frame.loc[ok].copy()
    if frame.empty:
        return frame
    # Existing guard: do not display invented gross flows when only net is known.
    bad_gross = (frame["scope"].eq("INDEX") &
                 frame["buy_value_vnd"].eq(0) &
                 frame["sell_value_vnd"].eq(0) &
                 frame["net_value_vnd"].notna() &
                 frame["net_value_vnd"].abs().gt(1e6))
    frame.loc[bad_gross, ["buy_value_vnd", "sell_value_vnd"]] = float("nan")
    return frame.sort_values("date").drop_duplicates(["scope", "code", "date"], keep="last").reset_index(drop=True)


def load_foreign_r2() -> pd.DataFrame:
    import streamlit as st
    from core.aura_macro_foreign import FLOW_COLUMNS
    from core.aura_r2_market import enabled, client, prefix, setting
    empty = pd.DataFrame(columns=FLOW_COLUMNS)
    if not enabled():
        return empty

    @st.cache_data(ttl=900, max_entries=2, show_spinner=False)
    def _fetch():
        key = prefix().rstrip("/") + "/foreign_flow/v1/foreign_flow_eod.csv"
        response = client().get_object(Bucket=setting("AURA_R2_BUCKET"), Key=key)
        payload = response["Body"].read(_MAX + 1)
        return _normalize_csv(payload)

    try:
        return _fetch()
    except Exception:
        # Fail closed without exposing private R2 paths, keys, or SDK errors.
        return empty
