# AURA — Checklist trước khi phát hành và nộp đồ án

## A. Giao diện / trải nghiệm
- [ ] Không còn chữ **local** trong tiêu đề/ghi chú BCTC và tỷ số ở trang online.
- [ ] Bỏ **X10** khỏi nội dung hiển thị người dùng; tên hàm/biến nội bộ không đổi.
- [ ] Nền khung 4 chỉ số tím dịu; 4 thẻ con và chữ đủ tương phản.
- [ ] Chú thích nguồn ngắn, không lặp khung vàng cảnh báo.
- [ ] Đúng tên doanh nghiệp (ví dụ FPT) dưới mã cổ phiếu.
- [ ] Kiểm tra desktop và mobile không cắt bảng, dòng, dấu tiếng Việt.

## B. Tính đúng đắn dữ liệu
- [ ] Xác minh phiên và đơn vị VNINDEX, VN30, HNXINDEX, UPCOMINDEX từ SSI; không tự suy ra GTGD.
- [ ] Kiểm tra cache, tính mới EOD và cảnh báo dữ liệu phiên cũ.
- [ ] Kiểm tra 3 bảng BCTC với FPT, SSI, TCB, VNM, HPG, VPB; thiếu năm có nhãn.
- [ ] Kho BCTC R2: báo cáo số mã đầy đủ, partial, failed; ba mã BCG, PSH, VE8 xác minh riêng.
- [ ] N/A không thành Đạt hoặc Không đạt; BCTC chưa xác minh không nâng điểm chính thức.
- [ ] Tab Hợp khẩu vị phản ánh đúng nguồn tỷ số (tham khảo vs đã xác minh).

## C. Vận hành và bảo mật
- [ ] Ảnh chụp SSI EOD trên R2 có ngày phiên và log đồng bộ.
- [ ] Tác vụ đồng bộ ngày giao dịch có retry, cảnh báo lỗi và kiểm tra đầy đủ sau upload.
- [ ] Không đẩy secrets, lịch sử giá hạn chế phân phối, dữ liệu cá nhân hoặc portfolio SQLite lên GitHub.
- [ ] Streamlit Secrets đúng R2 bucket/prefix/credentials; không in key vào logs.
- [ ] Xác thực và phân quyền danh mục nếu có nhiều người dùng; tránh dùng SQLite chung không có bảo vệ.

## D. Kiểm thử và nghiên cứu
- [ ] `python -m compileall -q app.py core` thành công trên clone.
- [ ] `git diff --check` thành công; push đúng các file đã kiểm tra.
- [ ] Thử mã sẵn dữ liệu, mã thiếu BCTC, mã mới/ít dữ liệu, mã ngân hàng/chứng khoán.
- [ ] Chạy kiểm thử hồi quy: điểm, chỉ báo MA/RSI, bộ lọc, danh mục không đổi khi chỉ sửa UI.
- [ ] Backtest không nhìn trước, có chi phí, ngoài mẫu và benchmark; có phiên bản luật cố định.
- [ ] README, sơ đồ và ảnh minh họa khớp đúng bản online đã triển khai.
