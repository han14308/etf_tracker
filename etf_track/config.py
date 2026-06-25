from __future__ import annotations

import os
from pathlib import Path
import json

from dotenv import load_dotenv

load_dotenv()

ROOT_DIR = Path(__file__).resolve().parents[1]
DATA_DIR = ROOT_DIR / "data"
DATA_DIR.mkdir(exist_ok=True)

DATABASE_URL = os.getenv("DATABASE_URL", f"sqlite:///{DATA_DIR / 'etf_track.db'}")
KODEX_200_FID = os.getenv("KODEX_200_FID", "2ETF01")
TIME_KOSPI_ACTIVE_IDX = int(os.getenv("TIME_KOSPI_ACTIVE_IDX", "11"))
COLLECT_DAYS = int(os.getenv("COLLECT_DAYS", "31"))
SECURITY_MASTER_PATH = Path(os.getenv("SECURITY_MASTER_PATH", DATA_DIR / "security_master.csv"))
BACKFILL_TOKEN = os.getenv("BACKFILL_TOKEN", "")
KRX_USERNAME = os.getenv("KRX_USERNAME", "")
KRX_PASSWORD = os.getenv("KRX_PASSWORD", "")
KRX_MENU_ID = os.getenv("KRX_MENU_ID", "MDC0201030108")
KRX_STAT_URL = os.getenv("KRX_STAT_URL", "dbms/MDC/STAT/standard/MDCSTAT13108")
KRX_EXTRA_PARAMS = json.loads(os.getenv("KRX_EXTRA_PARAMS", "{}"))
