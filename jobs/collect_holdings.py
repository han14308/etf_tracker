from __future__ import annotations

from datetime import date, timedelta
from pathlib import Path
import sys

ROOT_DIR = Path(__file__).resolve().parents[1]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

import pandas as pd

from etf_track.config import KODEX_200_FID, TIME_KOSPI_ACTIVE_IDX
from etf_track.db import upsert_holdings
from etf_track.download import download_kodex_holdings, download_time_holdings
from etf_track.normalize import normalize_holdings


def collect_for_date(trade_date: date) -> int:
    frames = []

    errors = []
    try:
        time_raw = download_time_holdings(TIME_KOSPI_ACTIVE_IDX, trade_date)
        frames.append(normalize_holdings(time_raw, "TIME_KOSPI_ACTIVE", trade_date))
    except Exception as exc:
        errors.append(f"TIME_KOSPI_ACTIVE: {exc}")

    try:
        kodex_raw = download_kodex_holdings(KODEX_200_FID, trade_date)
        frames.append(normalize_holdings(kodex_raw, "KODEX_200", trade_date))
    except Exception as exc:
        errors.append(f"KODEX_200: {exc}")

    if not frames:
        raise RuntimeError("; ".join(errors))

    normalized = pd.concat(frames, ignore_index=True)
    count = upsert_holdings(normalized)
    if errors:
        print(f"PARTIAL {trade_date.isoformat()} {'; '.join(errors)}")
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
    count = collect_for_date(target)
    print(f"Collected {count} holding rows for {target.isoformat()}")
