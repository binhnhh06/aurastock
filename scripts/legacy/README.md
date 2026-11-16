# scripts/legacy

Các script một lần (kiểm tra kết nối SSI, chuẩn bị dữ liệu, vá cài đặt) dùng trong quá trình phát triển.
**Không được ứng dụng web import** và không cần để chạy sản phẩm. Giữ lại để truy vết cách dữ liệu ban đầu
được tải và kiểm tra. Chạy từ thư mục gốc dự án, ví dụ: `python scripts/legacy/check_ssi_auth.py`.
Một số script gọi SSI API thật: cần `.env` và không chạy song song với worker realtime.
