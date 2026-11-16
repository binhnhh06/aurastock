# Từ điển dữ liệu AURA Stock

Mọi ngày giao dịch là ngày theo lịch sàn Việt Nam; mọi dấu thời gian hệ thống (log, `retrieved_at`) theo **Asia/Ho_Chi_Minh (UTC+7)**.
Nguồn chính: **SSI FastConnect Data V3** qua `ssi-sdk` (chỉ đọc dữ liệu, không gọi dịch vụ giao dịch).

## 1. Nhóm API SSI được sử dụng

| Nhóm | Hàm `ssi-sdk` | Dùng ở | Mục đích trong sản phẩm |
|---|---|---|---|
| OHLCV ngày (DailyOhlc) | `market_data.get_ohlc_all(timeframe=DAY_1)` | `core/ssi_adapter.py`, `scripts/ssi_fetch_symbol.py` | MA, RSI, động lượng, thanh khoản → điểm kỹ thuật |
| Tổng hợp chỉ số (DailyIndex) | `get_index_summary`, `get_index_summary_historical` | `scripts/ssi_refresh_indices.py` | VN-Index/VN30/HNX/UPCoM, độ rộng thị trường, bộ lọc VN-Index ≥ MA50 |
| Tổng hợp cổ phiếu (DailyStockPrice) | `get_securities_summary_historical` | `scripts/aura_sync_foreign.py` | Mua/bán của khối ngoại theo mã |
| Danh mục chứng khoán (Securities) | `get_securities_info_by_board`, `get_securities_info_by_index` | `core/ssi_universe.py` | Danh sách mã toàn thị trường, phân loại cổ phiếu/CW/ETF |
| Luồng thời gian thực (WebSocket) | `Stream` → `subscribe_symbol_trade` | `core/aura_ssi_realtime_v97.py` | Giá khớp gần nhất trên thẻ giá (chỉ hiển thị, không đưa vào chấm điểm) |

Mỗi lần gọi REST đi qua `core/aura_log.py → SSI_REST_LIMITER` (mặc định cách nhau ≥ 1 giây, chỉnh bằng `SSI_MIN_INTERVAL_SEC`). Lỗi và các lần chuyển sang dùng cache được ghi vào `logs/aura.log` và stderr.

## 2. Bảng giá ngày — `data/ssi_cache/ohlcv/{SYMBOL}.csv`

| Trường | Kiểu | Đơn vị | Ý nghĩa | Kiểm tra chất lượng (`_normalize`) |
|---|---|---|---|---|
| `symbol` | str | — | Mã chứng khoán | Phải trùng mã yêu cầu |
| `date` | date | ngày | Ngày giao dịch | Không trùng ngày; sắp xếp tăng dần |
| `open`, `high`, `low`, `close` | float | VND | Giá mở/cao/thấp/đóng cửa | > 0; `high` ≥ max(O,L,C); `low` ≤ min(O,H,C); không tự nhân 1.000 |
| `volume` | float | cổ phiếu | Khối lượng khớp | ≥ 0; thiếu → loại cả bản ghi |

Giá **chưa điều chỉnh** theo cổ tức/chia tách (`attrs["gia_dieu_chinh"] = "chưa xác minh"`).

## 3. Chỉ số thị trường — `ssi_refresh_indices.py`

| Trường | Đơn vị | Ý nghĩa |
|---|---|---|
| `price` | điểm | Giá trị chỉ số (loại nếu ngoài 30–10.000) |
| `change`, `percent` | điểm, % | Thay đổi so với phiên trước |
| `volume`, `value` | cổ phiếu, VND | Tổng KLGD/GTGD (nếu thiếu thì dùng phần khớp lệnh, có ghi `volume_type`/`value_type`) |
| `advances`, `declines`, `nochanges` | số mã | Độ rộng thị trường |

## 4. Khối ngoại — `aura_sync_foreign.py`

| Trường | Đơn vị | Ý nghĩa |
|---|---|---|
| `scope` | — | `INDEX` hoặc `STOCK` |
| `buy_value_vnd`, `sell_value_vnd`, `net_value_vnd` | VND | Giá trị mua/bán/ròng của khối ngoại |
| `buy_volume`, `sell_volume`, `net_volume` | cổ phiếu | Khối lượng mua/bán/ròng |
| `source`, `retrieved_at` | — | Nguồn API và thời điểm tải (giờ VN) |

Bản ghi có ngày trong tương lai hoặc toàn bộ giá trị trống bị loại.

## 5. Trường suy diễn dùng cho chấm điểm

| Trường | Công thức | Dùng ở |
|---|---|---|
| `MA20`, `MA50`, `MA200` | trung bình `close` n phiên | `core/analysis.py`, `core/strategy.py` |
| `RSI14` | RSI Wilder 14 phiên | `core/analysis.py` |
| `ret3m` | close_t / close_{t−63} − 1 | điểm động lượng |
| `vol_ratio` | KL TB 20 phiên / KL TB 60 phiên | điểm thanh khoản |
| `gtgd20` | TB 20 phiên (close × volume) | lọc thanh khoản ≥ 2 tỷ |
| `dd60` | (đỉnh 60 phiên − close) / đỉnh | cảnh báo giảm ≥ 15% |

## 6. Nguồn ngoài SSI (bổ trợ, có ghi nhãn)

| Nguồn | Dùng cho | Điều kiện |
|---|---|---|
| Kho BCTC AURA trên Cloudflare R2 (`vnstock`/`vnfinancialdata`) | Bảng cân đối, KQKD, LCTT, tỷ số | Gắn `source_verified=false` cho tới khi đối chiếu báo cáo gốc |
| DNSE chart API, `vnstock` (giá) | Dự phòng giá khi SSI lỗi | Chỉ khi bật `BATDAY_CHO_PHEP_DU_PHONG_GIA`; mặc định tắt |
