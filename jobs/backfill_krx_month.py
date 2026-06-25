from __future__ import annotations

from pathlib import Path
import sys
import time

ROOT_DIR = Path(__file__).resolve().parents[1]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from etf_track.calendar import recent_weekdays
from etf_track.config import COLLECT_DAYS
from jobs.collect_krx import collect_krx_for_date


if __name__ == "__main__":
    total = 0
    for trade_date in recent_weekdays(COLLECT_DAYS):
        try:
            count = collect_krx_for_date(trade_date)
            total += count
            print(f"OK {trade_date.isoformat()} rows={count}", flush=True)
        except Exception as exc:
            print(f"SKIP {trade_date.isoformat()} {exc}", flush=True)
        time.sleep(1)
    print(f"KRX backfill complete rows={total}", flush=True)
