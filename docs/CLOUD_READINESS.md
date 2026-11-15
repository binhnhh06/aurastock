# Cloud pre-flight — BLOCKERS

- Current release is **source-only**: SSI EOD cache is excluded pending redistribution rights and a permitted refresh/persistent-data plan. A GitHub repo is NOT proof that the hosted app works offline.
- Do NOT upload `.env`, `.streamlit/secrets.toml`, API keys, private SQLite, watchlists or any personal data.
- **Portfolio multi-user**: existing local SQLite must NOT be shared on a public host. Hide/disable page 3 for public deployment until real login + per-user authorization + durable DB are tested, or implement a visibly temporary, session-only demonstration without saving real investors' transactions.
- Realtime SSI worker not tested on cloud; no claim of realtime when laptop is off. Public release of SSI market data needs licence check.
- GitHub private source repository can be pushed first; production deploy needs separate smoke test with no laptop and cold restart.
- No live trading orders. This is academic research, not a buy/sell recommendation.
