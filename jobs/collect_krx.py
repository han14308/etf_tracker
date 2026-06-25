from __future__ import annotations

from datetime import date, timedelta
from pathlib import Path
import sys

ROOT_DIR = Path(__file__).resolve().parents[1]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from etf_track.db import upsert_krx_rows
from etf_track.krx import download_krx_pdf_rows


def collect_krx_for_date(trade_date: date) -> int:
    print(f"START {trade_date.isoformat()} KRX_PDF download", flush=True)
    raw = download_krx_pdf_rows(trade_date)
    print(f"DONE {trade_date.isoformat()} KRX_PDF download rows={len(raw)}", flush=True)
    print(f"START {trade_date.isoformat()} KRX_PDF database upsert rows={len(raw)}", flush=True)
    count = upsert_krx_rows(raw, trade_date)
    print(f"DONE {trade_date.isoformat()} KRX_PDF database upsert rows={count}", flush=True)
    return count


def latest_business_day(today: date | None = None) -> date:
    current = today or date.today()
    if current.weekday() == 5:
        return current - timedelta(days=1)
    if current.weekday() == 6:
        return current - timedelta(days=2)
    return current


if __name__ == "__main__":
    target = latest_business_day()
    count = collect_krx_for_date(target)
    print(f"Collected {count} KRX rows for {target.isoformat()}")
