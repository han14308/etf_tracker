from __future__ import annotations

import argparse
from datetime import date
from pathlib import Path
import sys
import time

ROOT_DIR = Path(__file__).resolve().parents[1]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from etf_track.calendar import recent_weekdays, weekdays_between
from etf_track.config import ACTIVE_ETF_ISSUERS, DATABASE_URL
from etf_track.db import fetch_existing_holding_dates
from etf_track.pykrx_active import collect_pykrx_active_for_date, list_pykrx_active_etfs


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Backfill domestic active ETF holdings from PyKRX without deleting existing data."
    )
    parser.add_argument("--days", type=int, default=31, help="Number of recent weekdays to collect.")
    parser.add_argument("--start", type=date.fromisoformat, default=None, help="Start date YYYY-MM-DD.")
    parser.add_argument("--end", type=date.fromisoformat, default=None, help="End date YYYY-MM-DD.")
    parser.add_argument("--missing-only", action="store_true", help="Skip dates already present in etf_holdings.")
    parser.add_argument("--pause", type=float, default=0.2, help="Seconds to wait between ETF portfolio downloads.")
    parser.add_argument(
        "--allow-sqlite",
        action="store_true",
        help="Allow backfilling the local SQLite database.",
    )
    args = parser.parse_args()

    if DATABASE_URL.startswith("sqlite") and not args.allow_sqlite:
        raise SystemExit(
            "DATABASE_URL points to local SQLite, not Supabase. "
            "Fix .env or add --allow-sqlite if you really want local data."
        )

    dates = weekdays_between(args.start, args.end) if args.start and args.end else recent_weekdays(args.days)
    if args.missing_only:
        existing_dates = fetch_existing_holding_dates(start=dates[0] if dates else None, end=dates[-1] if dates else None)
        dates = [trade_date for trade_date in dates if trade_date not in existing_dates]
        print(f"MISSING_ONLY holdings dates={len(dates)}", flush=True)
    total = 0
    for trade_date in dates:
        products = list_pykrx_active_etfs(trade_date, issuers=ACTIVE_ETF_ISSUERS)
        print(
            f"PRODUCTS {trade_date.isoformat()} count={len(products)} "
            f"names={', '.join(product.name for product in products[:10])}",
            flush=True,
        )
        count = collect_pykrx_active_for_date(
            trade_date,
            pause_seconds=args.pause,
            issuers=ACTIVE_ETF_ISSUERS,
            products=products,
        )
        total += count
        print(f"OK {trade_date.isoformat()} rows={count}", flush=True)
        time.sleep(0.5)

    print(f"Holdings backfill complete rows={total}", flush=True)


if __name__ == "__main__":
    main()
