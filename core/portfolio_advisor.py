"""AURA position calculator and *rule-based* decision support.

Pure functions only. No order placement, brokerage API access, or investment
recommendation. Cost basis/fees are supplied by the person, not guessed.
"""
from __future__ import annotations

from dataclasses import dataclass
from math import isfinite


@dataclass(frozen=True)
class PositionResult:
    quantity: int
    cost_price: float
    market_price: float
    invested: float
    market_value: float
    gross_pnl: float
    gross_pct: float
    net_pnl: float
    net_pct: float
    break_even: float
    estimated_buy_fee: float
    estimated_sell_cost: float
    weight_pct: float | None


def _positive(value: float, what: str) -> float:
    try:
        n = float(value)
    except (ValueError, TypeError, OverflowError) as exc:
        raise ValueError(f'{what} phải là số hợp lệ') from exc
    if not isfinite(n) or n <= 0:
        raise ValueError(f'{what} phải lớn hơn 0')
    return n


def calculate_position(quantity: int, cost_price: float, market_price: float, *,
                       buy_fee_pct: float = 0.0, sell_fee_pct: float = 0.0,
                       sell_tax_pct: float = 0.0,
                       total_portfolio_value: float | None = None) -> PositionResult:
    if isinstance(quantity, bool) or int(quantity) != quantity or quantity <= 0:
        raise ValueError('Số lượng phải là số nguyên dương')
    cost = _positive(cost_price, 'Giá vốn')
    market = _positive(market_price, 'Giá thị trường')
    costs = (buy_fee_pct, sell_fee_pct, sell_tax_pct)
    if any(not isfinite(float(p)) or p < 0 or p >= 20 for p in costs):
        raise ValueError('Các mức phí/thuế phải từ 0 đến dưới 20%')
    if total_portfolio_value is not None:
        total_portfolio_value = _positive(total_portfolio_value, 'Tổng giá trị danh mục')
    invested = quantity * cost
    value = quantity * market
    buy_fee = invested * buy_fee_pct / 100
    sell_cost = value * (sell_fee_pct + sell_tax_pct) / 100
    base = invested + buy_fee
    pnl_net = value - sell_cost - base
    pct_net = 100 * pnl_net / base
    be = cost * (1 + buy_fee_pct / 100) / (1 - (sell_fee_pct + sell_tax_pct) / 100)
    return PositionResult(
        quantity=int(quantity), cost_price=cost, market_price=market,
        invested=invested, market_value=value,
        gross_pnl=value - invested, gross_pct=100 * (market / cost - 1),
        net_pnl=pnl_net, net_pct=pct_net, break_even=be,
        estimated_buy_fee=buy_fee, estimated_sell_cost=sell_cost,
        weight_pct=100 * value / total_portfolio_value if total_portfolio_value else None,
    )


def prospective_signal(analysis: dict | None) -> tuple[str, list[str]]:
    """Watchlist label; deliberately NOT an instruction to trade."""
    if not analysis:
        return 'CHƯA PHÂN TÍCH', ['Chưa có điểm và bộ tiêu chí cho mã đang xem.']
    total = analysis.get('diem_tong')
    try:
        total = float(total)
    except (TypeError, ValueError):
        return 'CHƯA ĐỦ DỮ LIỆU', ['Không có điểm đánh giá hợp lệ.']
    buy = analysis.get('dk_mua') or []
    risks = analysis.get('dk_ban') or []
    count = sum(item[1] == 'Kích hoạt' for item in risks if len(item) > 1)
    required = [item for item in buy if len(item) >= 2 and item[1] in ('Đạt', 'Không đạt')]
    passes = bool(required) and all(item[1] == 'Đạt' for item in required)
    if count >= 2 or total < 35:
        return 'TRÁNH / RỦI RO CAO', [f'{count} cảnh báo kỹ thuật kích hoạt; điểm {total:.1f}/100.']
    if passes and total >= 60 and count == 0:
        return 'CÓ THỂ XEM XÉT MUA', [f'Đạt các tiêu chí kiểm tra, điểm {total:.1f}/100.', 'Cần xác minh tài chính và khẩu vị trước khi giao dịch.']
    if count:
        return 'THEO DÕI · CẢNH BÁO', [f'{count} cảnh báo rủi ro; cần đợi tín hiệu cải thiện.']
    return 'THEO DÕI', [f'Điểm {total:.1f}/100; chưa đủ điều kiện mở vị thế.']


def review_holding(position: PositionResult, *, analysis: dict | None,
                   price_fresh: bool, stop_loss_pct: float = 8.0,
                   take_profit_pct: float = 20.0, max_weight_pct: float = 20.0) -> tuple[str, list[str]]:
    """Scenario-oriented prompts, never a personalized trade recommendation.

    'Mua thêm' is withheld without financial verification or portfolio
    concentration data; neither an unrealized loss nor low P/E is a reason
    to average down.
    """
    if not price_fresh:
        return 'CHỜ GIÁ MỚI', ['Giá chưa đủ mới để đánh giá hành động; lãi/lỗ chỉ là ước tính theo giá cuối có sẵn.']
    if not analysis:
        return 'CẦN PHÂN TÍCH MÃ', ['Cần chạy Phân tích cho cùng mã trước khi xem gợi ý hành động.']
    total = float(analysis.get('diem_tong') or 0)
    risk_count = sum(item[1] == 'Kích hoạt' for item in (analysis.get('dk_ban') or []) if len(item) > 1)
    base = [f'Lãi/lỗ tạm tính sau các chi phí đã nhập: {position.net_pct:+.2f}%.',
            f'Điểm quy tắc hiện tại: {total:.1f}/100; số cảnh báo kỹ thuật: {risk_count}.']
    if position.gross_pct <= -stop_loss_pct:
        return 'XEM XÉT GIẢM / BÁN THEO KẾ HOẠCH', base + [
            f'Giá giảm {abs(position.gross_pct):.1f}% so với giá vốn, vượt mức rủi ro giả định {stop_loss_pct:.1f}%.',
            'Việc bán để kiểm soát thua lỗ có thể hợp lý, không cần đợi trở lại có lãi.']
    if risk_count >= 2 or total < 35:
        return 'XEM XÉT GIẢM TỶ TRỌNG', base + [
            'Nhiều cảnh báo kỹ thuật cùng kích hoạt; kiểm tra lý do và mức chịu rủi ro trước khi quyết định.']
    if position.gross_pct >= take_profit_pct:
        return 'CÂN NHẮC CHỐT LỜI MỘT PHẦN', base + [
            f'Giá cao hơn giá vốn {position.gross_pct:.1f}%, vượt mục tiêu tham khảo {take_profit_pct:.1f}%.',
            'Không bắt buộc bán chỉ vì có lãi; nên xét xu hướng, kế hoạch và thuế phí.']
    if position.weight_pct is not None and position.weight_pct > max_weight_pct:
        return 'GIỮ / HẠN CHẾ MUA THÊM', base + [
            f'Mã này đang chiếm {position.weight_pct:.1f}% giá trị danh mục khai báo, vượt mức tham khảo {max_weight_pct:.1f}%.']
    if total >= 65 and risk_count == 0:
        if analysis.get('co_fa') and position.weight_pct is not None:
            return 'THEO DÕI ĐIỂM MUA THÊM', base + [
                'Điều kiện kỹ thuật khá tích cực nhưng cần xác minh BCTC, định giá và sức mua.',
                'Chỉ cân nhắc tăng vị thế nếu còn phù hợp tỷ trọng danh mục và kế hoạch đầu tư.']
        return 'GIỮ / THEO DÕI ĐIỂM MUA THÊM', base + [
            'Chưa đủ dữ liệu tài chính được kiểm chứng hoặc chưa khai báo quy mô danh mục.',
            'Không suy ra lệnh mua thêm từ điểm kỹ thuật hoặc từ việc giá đang giảm.']
    return 'GIỮ / THEO DÕI RỦI RO', base + [
        'Chưa có điều kiện rõ để tăng vị thế; tiếp tục theo dõi mức chịu lỗ và cảnh báo xu hướng.']
