"""AURA V11.2: suitability rows, headline and rankings share ONE context.

When a fundamental metric is missing in the pipeline, look in the existing
AURA R2 report first, then the existing BCTC reader as an optional fallback.
Missing information never becomes a fabricated number or a passing result.
This code does not change original BCTC records, trading logic or backtests.
"""
from __future__ import annotations

from collections.abc import Mapping
from functools import lru_cache
import math
from typing import Any

FINANCIAL_KEYS = frozenset({
    "roe", "roe_tb3", "bien_ln_rong", "bien_ln_gop", "no_vcsh",
    "no_vay_vcsh", "thanh_toan", "cfo_lnst", "tang_truong_lnst",
    "tang_truong_dt", "chi_tra_co_tuc", "pe", "pb",
})


def _is_num(v: Any) -> bool:
    try:
        return math.isfinite(float(v)) and not isinstance(v, bool)
    except (ValueError, TypeError, OverflowError):
        return False


def _fallback_enabled() -> bool:
    import os
    return os.environ.get("AURA_KV_PROVIDER_FALLBACK", "1").strip().lower() not in {
        "0", "no", "false", "off"
    }


def _from_statements(statements: Mapping[str, Any], price_vnd: Any):
    """Derive only ratios defined by the project's own analysis module."""
    import pandas as pd
    from core.analysis import tinh_ty_so
    from core.aura_khauvi_reference_v105 import _last_real_value
    from core.aura_suitability_consistency_v110 import RATIO_LABELS

    ratios = tinh_ty_so(statements)
    if ratios is None or ratios.empty:
        return {}, {}
    vals, years = {}, {}
    for key, label in RATIO_LABELS.items():
        value = _last_real_value(ratios, label)
        if value is not None and _is_num(value[1]):
            vals[key] = float(value[1]); years[key] = str(value[0])

    if "ROE (%)" in ratios.index:
        roe = ratios.loc["ROE (%)"]
        if isinstance(roe, pd.Series):
            hist = {}
            for year, value in pd.to_numeric(roe, errors="coerce").items():
                try:
                    yr = int(year)
                except (ValueError, TypeError):
                    continue
                if _is_num(value):
                    hist[yr] = float(value)
            selected = sorted(hist)[-3:]
            if len(selected) == 3 and selected == list(range(selected[0], selected[0]+3)):
                vals["roe_tb3"] = sum(hist[y] for y in selected) / 3
                years["roe_tb3"] = f"{selected[0]}–{selected[-1]}"

    if _is_num(price_vnd) and 1000 <= float(price_vnd) <= 10_000_000:
        for key, label in (("pe", "EPS (đồng)"), ("pb", "BVPS (đồng)")):
            found = _last_real_value(ratios, label)
            if found and _is_num(found[1]) and float(found[1]) > 0:
                quotient = float(price_vnd) / float(found[1])
                if 0 < quotient <= 500 and math.isfinite(quotient):
                    vals[key] = quotient
                    years[key] = str(found[0]) + " + giá EOD"
    return vals, years


@lru_cache(maxsize=128)
def _provider_ratios(symbol: str, price_vnd: float | None):
    """Use only the project's pre-existing BCTC reader; no new providers/secrets.

    A cache keeps one analysis session from repeating an expensive provider call.
    The result is ratio data and provenance, not a changed local/R2 file.
    """
    from core.data import lay_bctc
    data = lay_bctc(symbol, so_nam=5)
    if not isinstance(data, Mapping) or not data:
        return {}, {}
    return _from_statements(data, price_vnd)


def combine_aura_context(base_context: Mapping[str, Any], symbol: str, price_vnd: Any):
    """Fill only absent metric keys. Priority pipeline > AURA R2 > BCTC fallback.

    Returns (context_copy, provenance_by_metric, added_count, error_summary).
    Errors are retained as diagnostics and never converted into numbers.
    """
    from core.aura_suitability_consistency_v110 import (
        add_reference_to_context, get_reference_ratios, is_missing
    )
    if not isinstance(base_context, Mapping):
        raise TypeError("Suitability context must be a mapping")
    ctx = dict(base_context)
    years: dict[str, str] = {}
    errors: list[str] = []
    added = 0
    try:
        vals, reported_years = get_reference_ratios(symbol, price_vnd)
        ctx, applied = add_reference_to_context(ctx, vals)
        added += len(applied)
        years.update({k: str(reported_years.get(k, "")) + " · BCTC AURA/R2" for k in applied})
    except (ImportError, ValueError, TypeError, KeyError, IndexError, AssertionError,
            RuntimeError, ZeroDivisionError, OSError, AttributeError) as exc:
        errors.append("R2:" + type(exc).__name__)

    needed = {k for k in FINANCIAL_KEYS if is_missing(ctx.get(k))}
    if needed and _fallback_enabled():
        try:
            price = float(price_vnd) if _is_num(price_vnd) else None
            vals, reported_years = _provider_ratios(str(symbol).upper(), price)
            subset = {k: vals[k] for k in needed if k in vals}
            ctx, applied = add_reference_to_context(ctx, subset)
            added += len(applied)
            years.update({k: str(reported_years.get(k, "")) + " · bộ đọc BCTC dự phòng" for k in applied})
        except (ImportError, ValueError, TypeError, KeyError, IndexError, AssertionError,
                RuntimeError, ZeroDivisionError, OSError, AttributeError) as exc:
            errors.append("BCTC dự phòng:" + type(exc).__name__)
    return ctx, years, added, "; ".join(errors)


def missing_financial_criteria(context: Mapping[str, Any], config: Mapping[str, Any], criteria):
    from core.aura_suitability_consistency_v110 import is_missing
    return [t["nhan"] for t in criteria
            if t.get("key") in config and t.get("key") in FINANCIAL_KEYS
            and is_missing(context.get(t["key"]))]


def make_profile_rows(context, profiles, get_config, assess):
    from core.aura_suitability_consistency_v110 import evaluate_all
    return evaluate_all(context, profiles, get_config, assess, preliminary=False)


def render_profile_table(context, profiles, get_config, assess):
    import pandas as pd
    import streamlit as st

    rows = make_profile_rows(context, profiles, get_config, assess)
    st.subheader("Mã này hợp khẩu vị nào nhất?")
    st.caption("Cùng bộ ngưỡng cho mọi khẩu vị; không xếp loại cao khi dữ liệu thiếu nhiều.")

    visible = [{k: row[k] for k in ("Khẩu vị", "% hợp", "Đạt", "Mức hợp")}
               for row in rows]
    frame = pd.DataFrame(visible, columns=["Khẩu vị", "% hợp", "Đạt", "Mức hợp"])
    frame["% hợp"] = pd.to_numeric(frame["% hợp"], errors="coerce")
    st.dataframe(frame, hide_index=True, use_container_width=True,
                 column_config={"% hợp": st.column_config.ProgressColumn(
                     "% hợp", min_value=0, max_value=100, format="%d%%")})
    if any(r.get("_coverage", 0) < 0.8 for r in rows):
        st.caption("Một số khẩu vị chưa đủ dữ liệu để xếp loại; tiêu chí thiếu không được tính là Đạt.")
