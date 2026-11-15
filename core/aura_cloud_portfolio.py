"""Isolate a temporary demo SQLite file for each Streamlit browser session.

No auth, no cross-device persistence. Local Windows uses existing portfolio DB.
"""
import os
import tempfile
from pathlib import Path


def is_cloud_demo():
    return os.name != "nt" or os.getenv("AURA_CLOUD_DEMO_PORTFOLIO", "").lower() in ("1", "true", "yes")


def session_db(state):
    key = "_aura_cloud_portfolio_db_v92"
    if key not in state:
        directory = tempfile.mkdtemp(prefix="aura_demo_")
        state[key] = str(Path(directory) / "portfolio.sqlite3")
    return Path(state[key])
