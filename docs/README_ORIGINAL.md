# BatDayStox SSI – Giao diện 2 trang (Tabs UI)

## Mục tiêu
Giữ nguyên trang `app.py` của BatDayStox (phân tích một mã và X10 gốc).
Thay 3 trang phụ (`Bộ lọc`, `Smart Rating`, `Tra cứu toàn thị trường`) bằng **1 trang duy nhất** `Trạm lọc thị trường` với 4 tabs:
- Tra cứu cổ phiếu: HOSE/HNX/UPCoM, giá EOD, MA, xuất CSV, tải riêng mã qua SSI.
- Bộ lọc thị trường: quét **khi bấm nút**, không tự gọi API theo 1.518 mã; lọc điểm, rủi ro, thanh khoản, sàn.
- Smart Rating & BCTC: điểm kỹ thuật, điểm đa nhân tố nếu có dữ liệu đủ nguồn, bảng ROE/ROA/EPS **sơ bộ**.
- Dữ liệu & phương pháp: phân biệt giá EOD / live và giới hạn tin cậy.

Không sao chép mã nguồn từ trang tham khảo. Giao diện là mã tự viết bằng Streamlit.

## Cài đặt (PowerShell trong thư mục dự án)
1. Sao lưu dự án hoặc commit Git trước.
2. Giải nén ZIP vào thư mục dự án.
3. Kiểm tra:

```powershell
.\.venv\Scripts\python.exe .\install_two_pages.py --dry-run
```

4. Cài:

```powershell
.\.venv\Scripts\python.exe .\install_two_pages.py
.\.venv\Scripts\python.exe -m streamlit run app.py
```

Installer sẽ chuyển **đúng ba trang phụ cũ** vào `backups/unified_ui_.../pages/`. Không xóa, không sửa app.py và core.

## Điều kiện
- Đã có `core/smart_screener.py`, `core/ssi_universe.py`, `scripts/ssi_fetch_symbol.py` từ các bước trước.
- Đã đồng bộ `data/ssi_cache/market_symbols.csv` (danh mục HOSE/HNX/UPCoM).
- Dữ liệu giá đã có tại `data/ssi_cache/ohlcv/*.csv`.
- `core/smart_rating_v2.py` là tùy chọn; nếu chưa cài, chỉ hiển thị bảng BCTC sơ bộ.
- Snapshot live là tùy chọn. Không có worker => không giả lập realtime.

## Những gì chưa hoàn thành
- Realtime WebSocket SSI chưa thể tự hoạt động chỉ bằng thay giao diện. Cần chạy và kiểm thử worker / quyền API riêng.
- Chưa có BCTC được xác minh theo ngày công bố và nguồn chính thức: không chấm điểm cơ bản hoặc định giá ảo.
- Bộ lọc quét các mã có dữ liệu đủ điều kiện tại ngày EOD, không phải xếp hạng tức thời toàn thị trường.
- Không tự động gửi lệnh giao dịch.

## Lưu ý triển khai
- Trên Streamlit Cloud, dữ liệu lưu trên filesystem có thể mất sau khi app khởi động lại. Dữ liệu toàn thị trường và kết quả chấm điểm nên được cập nhật theo lịch ở backend rồi tải vào ứng dụng từ kho lưu trữ bền vững.
- Phần mềm nên giữ một `app.py` và một trang phụ. Nếu trong `pages/` có các trang khác không thuộc ba tên cũ, cần xem và di chuyển thủ công nếu muốn giao diện chỉ có 2 mục.

## Nguồn tham khảo do giảng viên gợi ý
- https://github.com/soitang733/taikhoanx10_bot_tele — repository tham khảo về cách tổ chức tính năng; **chưa xác minh mã nguồn bên trong trong phiên xây dựng này**.
- https://stocklens-investment.vercel.app/ — liên kết tham khảo trải nghiệm sản phẩm; **chưa xác minh nội dung trang trong phiên xây dựng này**.

Mã giao diện trong gói này được viết riêng, không sao chép các tác phẩm đó. Nếu cần tích hợp đúng module của giảng viên, cần kiểm tra nội dung repository, giấy phép và thử nghiệm tương thích SSI trước.
