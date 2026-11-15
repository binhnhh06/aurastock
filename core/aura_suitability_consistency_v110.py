"""AURA V11.0: transparent comparison of original and preliminary suitability.

The original score is never modified. A separate preliminary context may include
R2 financial values when the authoritative pipeline has missing values.
"""
from __future__ import annotations

import math
from typing import Any, Callable, Mapping

# Limit display only: 80% is a *coverage rule*, not an investment rule.
MIN_COVERAGE = 0.80

RATIO_LABELS = {
    "roe": "ROE (%)",
    "bien_ln_rong": "Biên LN ròng (%)",
    "bien_ln_gop": "Biên LN gộp (%)",
    "no_vcsh": "Nợ / VCSH (lần)",
    "no_vay_vcsh": "Nợ vay / VCSH (lần)",
    "thanh_toan": "Thanh toán hiện hành (lần)",
    "cfo_lnst": "CFO / LNST (lần)",
    "tang_truong_lnst": "Tăng trưởng LNST (%)",
    "tang_truong_dt": "Tăng trưởng doanh thu (%)",
    "chi_tra_co_tuc": "Chi trả cổ tức / LNST (%)",
}


def is_missing(value: Any) -> bool:
    if value is None:
        return True
    if isinstance(value, str) and value.strip().lower() in ("", "n/a", "none", "nan", "null"):
        return True
    try:
        import pandas as pd
        test = pd.isna(value)
        if isinstance(test, bool):
            return test
    except (ImportError, TypeError, ValueError):
        pass
    return isinstance(value, float) and not math.isfinite(value)


def get_reference_ratios(symbol: str, price_vnd: Any) -> tuple[dict[str, float], dict[str, str]]:
    """Fetch read-only financial ratios from private R2; never creates placeholders.

    Returns values and their real data years. Errors are reported to the caller
    rather than silently changing the score.
    """
    import pandas as pd
    from core.aura_original_bctc_v99 import load_original
    from core.analysis import tinh_ty_so
    from core.aura_khauvi_reference_v105 import _last_real_value

    source = load_original(symbol)
    if not source or not source[0]:
        return {}, {}
    ratios = tinh_ty_so(source[0])
    if ratios is None or ratios.empty:
        return {}, {}
    values: dict[str, float] = {}
    years: dict[str, str] = {}
    for key, label in RATIO_LABELS.items():
        found = _last_real_value(ratios, label)
        if found is None:
            continue
        year, value = found
        if math.isfinite(float(value)):
            values[key], years[key] = float(value), str(year)

    # Three-year consecutive average only, not an invented estimate.
    if "ROE (%)" in ratios.index and not isinstance(ratios.loc["ROE (%)"], pd.DataFrame):
        series = pd.to_numeric(ratios.loc["ROE (%)"], errors="coerce")
        valid_years: dict[int, float] = {}
        for year, value in series.items():
            try:
                year_number = int(year)
                amount = float(value)
            except (ValueError, TypeError):
                continue
            if math.isfinite(amount):
                valid_years[year_number] = amount
        if len(valid_years) >= 3:
            latest = sorted(valid_years)[-3:]
            if latest == list(range(latest[0], latest[0] + 3)):
                values["roe_tb3"] = sum(valid_years[y] for y in latest) / 3
                years["roe_tb3"] = f"{latest[0]}–{latest[-1]}"

    # Never guess whether raw SSI prices use VND or thousands of VND.
    try:
        price = float(price_vnd)
    except (ValueError, TypeError, OverflowError):
        price = float("nan")
    if math.isfinite(price) and 1000 <= price <= 10_000_000:
        for key, label in (("pe", "EPS (đồng)"), ("pb", "BVPS (đồng)")):
            found = _last_real_value(ratios, label)
            if found is None or float(found[1]) <= 0:
                continue
            value = price / float(found[1])
            if math.isfinite(value) and 0 < value <= 500:
                values[key] = value
                years[key] = str(found[0]) + " + giá EOD"
    return values, years


def add_reference_to_context(verified_ctx: Mapping[str, Any], reference: Mapping[str, float]) -> tuple[dict[str, Any], list[str]]:
    """Copy verified context; fill only missing fields in a NEW preview context."""
    result = dict(verified_ctx)
    applied = []
    for key, value in reference.items():
        try:
            number = float(value)
        except (TypeError, ValueError):
            continue
        if not math.isfinite(number):
            continue
        if is_missing(result.get(key)):
            result[key] = number
            applied.append(key)
    return result, applied


def one_profile_row(code: str, name: str, profile_cfg: Mapping[str, Any], result: Mapping[str, Any], *, preliminary: bool) -> dict[str, Any]:
    total = len(profile_cfg)
    passed = int(result.get("dat", 0))
    failed = int(result.get("khong", 0))
    known = passed + failed
    if total < 0 or passed < 0 or failed < 0 or known > total:
        raise ValueError(f"Suitability count inconsistent for {code}: {passed}+{failed}>{total}")
    coverage = known / total if total else 0.0
    sufficiently_covered = total > 0 and coverage >= MIN_COVERAGE
    # A one-of-one score must not be presented as 100% suitable when most
    # required criteria are missing. Percentage is suppressed when coverage low.
    percent = round(100 * passed / known) if known and sufficiently_covered else None
    status = (str(result.get("hang") or "Đã tính") if sufficiently_covered
              else "Chưa đủ dữ liệu" if total else "Không có tiêu chí")
    return {
        "Khẩu vị": name,
        "% hợp": percent,
        "Đạt": f"{passed}/{total}",
        "Độ phủ": f"{known}/{total}",
        "Mức hợp": status,
        "_coverage": coverage,
        "_passed": passed,
        "_mode": "preliminary" if preliminary else "verified",
    }


def evaluate_all(context: Mapping[str, Any], profiles: Mapping[str, Mapping[str, Any]],
                 get_config: Callable[[str], Mapping[str, Any]],
                 assess: Callable[[Mapping[str, Any], Mapping[str, Any]], Mapping[str, Any]],
                 *, preliminary: bool) -> list[dict[str, Any]]:
    rows = []
    for code, info in profiles.items():
        if code == "tuy_chinh":
            continue
        config = get_config(code)
        result = assess(dict(context), config)
        rows.append(one_profile_row(code, str(info.get("ten", code)), config, result, preliminary=preliminary))
    rows.sort(key=lambda x: (x["% hợp"] is None, -(x["% hợp"] or 0), -x["_coverage"], x["Khẩu vị"]))
    return rows


def visible_rows(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    fields = ("Khẩu vị", "% hợp", "Đạt", "Độ phủ", "Mức hợp")
    return [{k: row[k] for k in fields} for row in rows]


def render_suitability_comparison(symbol: str, result: Mapping[str, Any], profiles,
                                  get_config, assess, get_context) -> None:
    """Render profile ranking. Never modifies result, original profile rules, or trades."""
    import pandas as pd
    import streamlit as st

    verified_ctx = get_context(result)
    if not isinstance(verified_ctx, Mapping):
        raise TypeError("AURA profile context is not a mapping")
    confirmed_rows = evaluate_all(verified_ctx, profiles, get_config, assess, preliminary=False)

    price = result.get("kq", {}).get("Giá đóng cửa")
    r2_values = {}
    years = {}
    error = None
    try:
        r2_values, years = get_reference_ratios(symbol, price)
    except (ImportError, ValueError, TypeError, KeyError, IndexError, AttributeError,
            RuntimeError, ZeroDivisionError, OSError) as exc:
        error = type(exc).__name__
    preview_ctx, applied = add_reference_to_context(verified_ctx, r2_values)
    preview_rows = evaluate_all(preview_ctx, profiles, get_config, assess, preliminary=True) if applied else []

    st.subheader("Mã này hợp khẩu vị nào nhất?")
    st.caption("Cùng bộ ngưỡng cho mọi nguồn; tỷ lệ chỉ hiển thị khi ≥80% tiêu chí có dữ liệu. "
               "Độ phủ = số tiêu chí có dữ liệu / tổng tiêu chí bật.")
    if preview_rows:
        st.markdown("**Đánh giá sơ bộ từ BCTC AURA**")
        st.caption("Nguồn BCTC: Kho AURA (R2). Nguồn giá (nếu có): SSI FastConnect V3. "
                   "Kết quả sơ bộ được trình bày riêng, không thay đổi tín hiệu mua/bán.")
        preview_df = pd.DataFrame(visible_rows(preview_rows))
        preview_df["% hợp"] = pd.to_numeric(preview_df["% hợp"], errors="coerce")
        st.dataframe(preview_df, hide_index=True, use_container_width=True,
                     column_config={"% hợp": st.column_config.ProgressColumn(
                         "% hợp", min_value=0, max_value=100, format="%d%%")})
        years_display = ", ".join(f"{key}:{years.get(key, '?')}" for key in applied)
        st.caption(f"Đã bổ sung {len(applied)} chỉ tiêu từ BCTC AURA (năm: {years_display}).")
    elif r2_values:
        st.info("BCTC R2 đã đọc được, nhưng không có chỉ tiêu thiếu phù hợp để bổ sung vào bộ lọc.")
    else:
        st.info("Chưa có tỷ số BCTC R2 để lập đánh giá sơ bộ cho mã này.")
    if error:
        st.caption("Lý do không đọc được tỷ số R2: " + error)
    with st.expander("Đánh giá theo dữ liệu đã xác minh", expanded=not bool(preview_rows)):
        st.caption("Giữ nguyên bộ đánh giá hiện có. Những tiêu chí thiếu dữ liệu không được coi là Đạt/Không đạt.")
        verified_df = pd.DataFrame(visible_rows(confirmed_rows))
        verified_df["% hợp"] = pd.to_numeric(verified_df["% hợp"], errors="coerce")
        st.dataframe(verified_df, hide_index=True, use_container_width=True,
                     column_config={"% hợp": st.column_config.ProgressColumn(
                         "% hợp", min_value=0, max_value=100, format="%d%%")})
