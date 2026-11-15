# AURA — Giao thức backtest trước khi tuyên bố hiệu quả

**Tình trạng:** thiết kế phương pháp; **chưa chạy và chưa có hiệu suất thực nghiệm**.

## 1. Bất biến phương pháp

- Chỉ sử dụng dữ liệu đã biết tại đóng cửa **t**, không nhìn trước t+1.
- Giao dịch sớm nhất ở **giá mở cửa phiên t+1**; nếu không có open/không khớp do hạn chế thanh khoản thì bỏ lệnh và ghi lý do.
- Tín hiệu phải lấy từ **phiên bản quy tắc AURA được đóng băng**, không chọn ngưỡng sau khi xem kết quả test.
- Bộ BCTC chưa có `published_at` hợp lệ chỉ dùng để **nghiên cứu tham khảo**, không backtest Quality & Value theo kiểu đã kiểm toán.
- Không giả định giá chưa điều chỉnh cho cổ tức/chia tách là total return.
- Đo chi phí giao dịch, thuế phí bán, slippage theo kịch bản; không chọn một mức phí “đúng cho mọi sàn”.
- Lưu danh sách mã tại thời điểm lịch sử, bao gồm hủy niêm yết nếu có; nếu chỉ có VN30 hiện tại phải công bố survivorship bias.

## 2. Kịch bản

| Thiết kế | Mặc định để kiểm thử | Cần kiểm định thêm |
|---|---|---|
| Phong cách | Trend Following, Breakout, Pullback | Quy tắc được triển khai trong `core/aura_investment_policy.py` |
| Thị trường tham chiếu | VN-Index | Ngày phiên và chuẩn hóa chỉ số |
| Tập mã | Theo universe có lịch sử | Tránh chỉ dùng mã còn niêm yết hôm nay |
| Giai đoạn | Khi có dữ liệu 2021–2026 | Tách thời gian trước/sau và walk-forward |
| Khớp lệnh | Open t+1 (giả lập) | Không dự báo khả năng khớp chỉ từ OHLCV |
| Thoát lệnh | Quy tắc rõ ràng được đóng băng trước | Không thiết kế dựa trên kết quả |
| Chi phí | Kịch bản nhạy cảm nhiều mức | Phí thực tế theo thời kỳ, thuế, slippage |

## 3. Chỉ tiêu báo cáo

- Tổng lợi suất, CAGR, biến động năm, Sharpe (ghi rõ risk-free), max drawdown và độ dài drawdown.
- Tỷ lệ thắng, profit factor, số giao dịch, lợi suất bình quân lệnh, turnover.
- Alpha/beta mô tả so với VN-Index khi cùng lịch, không suy diễn nhân quả.
- Dải kết quả theo nhóm ngành, vốn hóa, chế độ thị trường (ví dụ VN-Index trên/dưới MA50).
- Stress test phí, khoảng trống dữ liệu, giá điều chỉnh và thời điểm khớp.

## 4. Kiểm định mã nguồn

1. Cố định commit và hash file tín hiệu.
2. Kiểm tra CSV có ngày tăng dần, không trùng mã/ngày, không sai đơn vị, giá/khối lượng >0 nơi yêu cầu.
3. Kiểm thử thuật toán không dùng `shift(-1)` để sinh tín hiệu.
4. Backtest so với baseline mua–nắm giữ trong cùng khoảng thời gian.
5. Tách in-sample/out-of-sample, báo cáo cả trường hợp lỗ và mã không đủ dữ liệu.
6. Lưu tham số, mã, phiên, trade log, equity curve, kết quả và giới hạn vào `reports/backtest/` (không commit dữ liệu hạn chế phân phối).

**Chỉ sau khi kiểm thử mới bổ sung số liệu thực nghiệm vào README.**
