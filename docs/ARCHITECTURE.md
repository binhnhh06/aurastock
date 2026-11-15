# AURA Architecture (teacher-required layers)

SSI FastConnect V3 (source; secrets kept outside code) -> `core/ssi_client.py`, `core/ssi_adapter.py` -> `scripts/market_sync.py` / `core/data.py` (collect/clean/cache) -> `core/analysis.py`, `core/pipeline.py`, `core/strategy.py`, ranking modules (financial logic) -> `app.py`, `pages/` (Streamlit interface).

Data freshness must show the actual EOD date, connection failures and fallbacks; all dates use Asia/Ho_Chi_Minh when displayed. Realtime worker is optional and NOT guaranteed to run in hosting.

Current app keeps `core/` and `pages/` layout instead of moving to `src/` to avoid breaking imports; the instructor's `src/` is illustrative, not mandatory.
