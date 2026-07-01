from __future__ import annotations

import argparse
from pathlib import Path
import sys
import time

ROOT_DIR = Path(__file__).resolve().parents[1]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from etf_track.calendar import recent_weekdays
from etf_track.config import DATABASE_URL
from etf_track.market_stats import collect_market_stats_for_date


def main() -> None:
    parser = argparse.ArgumentParser(description="Backfill KRX daily stock and ETF market statistics.")
    parser.add_argument("--days", type=int, default=31, help="Number of recent weekdays to collect.")
    parser.add_argument("--pause", type=float, default=0.5, help="Seconds to wait between dates.")
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

    total_security = 0
    total_etf = 0
    for trade_date in recent_weekdays(args.days):
        print(f"MARKET_STATS_START {trade_date.isoformat()}", flush=True)
        counts = collect_market_stats_for_date(trade_date)
        total_security += counts["security_daily_stats"]
        total_etf += counts["etf_daily_stats"]
        print(
            f"MARKET_STATS_DONE {trade_date.isoformat()} "
            f"security={counts['security_daily_stats']} etf={counts['etf_daily_stats']}",
            flush=True,
        )
        time.sleep(args.pause)

    print(f"Market stats complete security={total_security} etf={total_etf}", flush=True)


if __name__ == "__main__":
    main()
