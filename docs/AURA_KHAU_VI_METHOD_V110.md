# AURA V11.0 — Phương pháp so sánh khẩu vị

Bản này giải quyết lỗi diễn giải **1/1 đạt = 100% rất hợp khẩu vị** khi các tiêu chí khác chưa có dữ liệu. **Không thay đổi hàm `danh_gia`, ngưỡng khẩu vị, điểm kỹ thuật hoặc điểm mua/bán.**

- Với mỗi hồ sơ có N tiêu chí bật: **Đạt** = số tiêu chí đạt / N; **Độ phủ** = số tiêu chí có dữ liệu / N.
- **% hợp** trên các tiêu chí có dữ liệu chỉ được hiển thị nếu độ phủ tối thiểu 80%. Dưới mức này hiện **Chưa đủ dữ liệu**, không xếp loại “Rất hợp”. 80% là ngưỡng chất lượng hiển thị, *không phải* ngưỡng giao dịch được backtest.
- **Theo dữ liệu đã xác minh**: chạy lại nguyên hàm `danh_gia` với ngữ cảnh cũ. N/A không được tính là Đạt hoặc Không đạt.
- **Đánh giá sơ bộ từ R2**: bổ sung chỉ tiêu tham khảo còn thiếu (ROE, biên LN, Nợ/VCSH, EPS/BVPS để tính P/E/P/B khi đủ điều kiện) vào một bản sao ngữ cảnh rồi chạy lại **cùng hàm `danh_gia`**. Có nhãn “chưa đối chiếu công bố chính thức”. Giá cổ phiếu không được tự nhân 1000 khi đơn vị không chắc chắn.
- Bảng sơ bộ không được sử dụng để sinh tín hiệu mua, bán, thay điểm X10/Smart Rating, lưu danh mục hoặc thay kết quả backtest.

Không được hứa hẹn tái tạo đúng số liệu local cũ nếu ngày giá, kỳ BCTC, ngưỡng cấu hình hoặc nguồn dữ liệu giữa local và Cloud khác nhau. Cần đối chiếu cùng mã, cùng ngày phiên, cùng bộ tiêu chí.

Kiểm thử ưu tiên: FPT, VJC, cổ phiếu ngân hàng, mã thiếu BCTC, cổ phiếu không có EPS, trường hợp 0/0 và 1/1. Trước khi triển khai cần xem `git diff`, kiểm thử local và xác nhận bản Cloud hiển thị đúng.
