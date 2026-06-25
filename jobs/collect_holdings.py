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
        print(f"START {trade_date.isoformat()} TIME_KOSPI_ACTIVE download", flush=True)
        time_raw = download_time_holdings(TIME_KOSPI_ACTIVE_IDX, trade_date)
        print(f"DONE {trade_date.isoformat()} TIME_KOSPI_ACTIVE download rows={len(time_raw)}", flush=True)
        time_frame = normalize_holdings(time_raw, "TIME_KOSPI_ACTIVE", trade_date)
        print(f"DONE {trade_date.isoformat()} TIME_KOSPI_ACTIVE normalize rows={len(time_frame)}", flush=True)
        frames.append(time_frame)
    except Exception as exc:
        errors.append(f"TIME_KOSPI_ACTIVE: {exc}")
        print(f"ERROR {trade_date.isoformat()} TIME_KOSPI_ACTIVE {exc}", flush=True)

    try:
        print(f"START {trade_date.isoformat()} KODEX_200 download", flush=True)
        kodex_raw = download_kodex_holdings(KODEX_200_FID, trade_date)
        print(f"DONE {trade_date.isoformat()} KODEX_200 download rows={len(kodex_raw)}", flush=True)
        kodex_frame = normalize_holdings(kodex_raw, "KODEX_200", trade_date)
        print(f"DONE {trade_date.isoformat()} KODEX_200 normalize rows={len(kodex_frame)}", flush=True)
        frames.append(kodex_frame)
    except Exception as exc:
        errors.append(f"KODEX_200: {exc}")
        print(f"ERROR {trade_date.isoformat()} KODEX_200 {exc}", flush=True)

    if not frames:
        raise RuntimeError("; ".join(errors))

    normalized = pd.concat(frames, ignore_index=True)
    print(f"START {trade_date.isoformat()} database upsert rows={len(normalized)}", flush=True)
    count = upsert_holdings(normalized)
    print(f"DONE {trade_date.isoformat()} database upsert rows={count}", flush=True)
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
