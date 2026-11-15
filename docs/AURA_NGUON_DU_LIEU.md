# Nguồn dữ liệu & cách trình bày trên AURA

## Các nguồn được hệ thống sử dụng

- **Giá cổ phiếu, chỉ số và dữ liệu khối ngoại:** SSI FastConnect V3. Đây là dữ liệu thị trường, **không phải** là nguồn đã xác định của các bảng BCTC trong kho hiện tại.
- **Báo cáo tài chính (BCTC):** các bảng `balance_sheet`, `income_statement`, `cash_flow` đã xuất từ kho CSV staging của AURA lên Cloudflare R2 private. Dữ liệu dự phòng cho một số mã có thể đến từ luồng `vnfinancialdata`/`vnstock` của V9.9.
- **Các tỷ số tài chính:** được tính từ cùng dữ liệu BCTC trên R2; P/E và P/B còn sử dụng giá EOD khi đơn vị và EPS/BVPS hợp lệ.
- **Cloudflare R2:** phương tiện lưu trữ dữ liệu; **không phải nhà phát hành BCTC**.

## Metadata hiện có

Nguồn trong R2 đối với các file tải từ staging được gắn `source = "AURA local staging CSV, original publisher/audit status unverified"` và `source_verified = false`. Đây là mô tả xuất xứ kỹ thuật, không phải kết luận BCTC sai.

Để ghi rõ đơn vị công bố/đã kiểm toán, dữ liệu cần có thêm `publisher`, `report_url`, `report_type`, `audit_status`, `published_at`, `verified_at`. Không được tự gắn `source_verified=true` chỉ vì BCTC đã được tải lên R2 hoặc đã tính ra tỷ số.

## Cách đọc kết quả khẩu vị

Bảng **Đánh giá sơ bộ** có thể dùng thêm các tỷ số BCTC AURA và vẫn giữ nguyên ngưỡng cũ. Đánh giá theo dữ liệu có đối chiếu nguồn giữ riêng. Không gộp hai kết quả và không dùng điểm sơ bộ làm tín hiệu mua/bán đã kiểm định.

## Khi trích dẫn trong báo cáo đồ án

> Dữ liệu giá và chỉ số được cung cấp qua SSI FastConnect V3; dữ liệu báo cáo tài chính sử dụng kho tài chính AURA, lưu trên Cloudflare R2. Các tỷ số được tính toán từ BCTC hiện có, với tình trạng xuất xứ và đối chiếu trình bày theo metadata từng mã.
