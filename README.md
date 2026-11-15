# AURA — Smart Stock Filter (SSI FastConnect V3)

**Academic FinTech prototype. Not investment advice; no real-money order placement.**

## Problem and users
Retail investors need to screen liquid listed equities, understand trend and market context, and monitor simulated portfolios. AURA uses SSI FastConnect as the core market-data source; supporting preliminary financial ratios must be labeled as unverified.

## Architecture
`SSI FastConnect V3 -> scripts / core (acquisition + storage) -> core (financial analysis and ranking) -> app.py + pages/ (Streamlit)`.
See `docs/ARCHITECTURE.md` and instructor checklist in `docs/CHECKLIST_DE_THAY.md`.

## Run locally
1. Install Python 3.12 and create a virtual environment (`python -m venv .venv`).
2. Install `python -m pip install -r requirements.txt` (check API library licence/version compatibility; pin dependencies after release verification).
3. Copy `.env.example` to `.env` and fill credentials **only on your own machine**, never on GitHub.
4. Populate permitted SSI market data using the scripts documented in your project (subject to API rights, rate limits and available credentials).
5. Run `python -m streamlit run app.py`.

## Key folders
- `app.py`: main analysis page.
- `pages/`: screening and simulated portfolio pages.
- `core/`: SSI adapters, market data processing, scoring, strategies, portfolio calculations.
- `scripts/`: operational data collection, refresh and diagnostics.
- `tests/`: reproducible tests.
- `data_sample/`: synthetic schema example; **NOT** live data.
- `docs/`: architecture, test/checklist and cloud limitations.
- `report/`: final submission report.

## Status and honest limitations
- Technical and preliminary fundamental **research** scores are not a verified 50/35/15 Smart Rating and are **not** validated trading recommendations or backtest signals.
- Current compiled repository deliberately **excludes** 1,481+ local SSI EOD CSV caches, reports, all `.env` keys and personal portfolio databases. Therefore, pushing this source repository **does not by itself produce a functioning self-updating cloud dashboard**.
- Public multi-user portfolio requires authenticated, access-controlled durable storage. Current local SQLite MUST NOT be shared online.
- Realtime/refresh off-laptop requires separately tested cloud architecture and SSI redistribution permission. See `docs/CLOUD_READINESS.md`.
