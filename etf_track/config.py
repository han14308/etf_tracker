from __future__ import annotations

import os
from pathlib import Path
import json

from dotenv import load_dotenv

ROOT_DIR = Path(__file__).resolve().parents[1]
load_dotenv(ROOT_DIR / ".env")

DATA_DIR = ROOT_DIR / "data"
DATA_DIR.mkdir(exist_ok=True)

default_database_path = Path("/tmp/etf_track.db") if os.getenv("VERCEL") else DATA_DIR / "etf_track.db"
raw_database_url = os.getenv("DATABASE_URL", "").strip().strip("\"'")
if raw_database_url.startswith("DATABASE_URL="):
    raw_database_url = raw_database_url.split("=", 1)[1].strip().strip("\"'")
if raw_database_url in {"", "DATABASE_URL"}:
    raw_database_url = f"sqlite:///{default_database_path}"
DATABASE_URL = raw_database_url
KODEX_200_FID = os.getenv("KODEX_200_FID", "2ETF01")
TIME_KOSPI_ACTIVE_IDX = int(os.getenv("TIME_KOSPI_ACTIVE_IDX", "11"))
COLLECT_DAYS = int(os.getenv("COLLECT_DAYS", "31"))
ACTIVE_BACKFILL_ON_START_DAYS = int(os.getenv("ACTIVE_BACKFILL_ON_START_DAYS", "0"))
SECURITY_MASTER_PATH = Path(os.getenv("SECURITY_MASTER_PATH", DATA_DIR / "security_master.csv"))
SECURITY_SECTOR_PATH = Path(os.getenv("SECURITY_SECTOR_PATH", DATA_DIR / "security_sectors.csv"))
BACKFILL_TOKEN = os.getenv("BACKFILL_TOKEN", "")
KRX_USERNAME = os.getenv("KRX_USERNAME", os.getenv("KRX_ID", ""))
KRX_PASSWORD = os.getenv("KRX_PASSWORD", os.getenv("KRX_PW", ""))
KRX_COOKIE = os.getenv("KRX_COOKIE", "")
KRX_MENU_ID = os.getenv("KRX_MENU_ID", "MDC0201030108")
KRX_STAT_URL = os.getenv("KRX_STAT_URL", "dbms/MDC/STAT/standard/MDCSTAT13108")
KRX_EXTRA_PARAMS = json.loads(os.getenv("KRX_EXTRA_PARAMS", "{}"))

DEFAULT_ACTIVE_ISSUERS = [
    "KODEX",
    "TIGER",
    "HANARO",
    "RISE",
    "KIWOOM",
    "ACE",
    "PLUS",
    "SOL",
    "TIME",
    "1Q",
    "KoAct",
    "WON",
    "UNICORN",
    "IBK",
]
ACTIVE_ETF_ISSUERS = [
    issuer.strip()
    for issuer in os.getenv("ACTIVE_ETF_ISSUERS", ",".join(DEFAULT_ACTIVE_ISSUERS)).split(",")
    if issuer.strip()
]
