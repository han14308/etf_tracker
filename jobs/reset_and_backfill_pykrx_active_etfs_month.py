from __future__ import annotations

import argparse
from pathlib import Path
import sys
import time

ROOT_DIR = Path(__file__).resolve().parents[1]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from etf_track.calendar import recent_weekdays
from etf_track.config import ACTIVE_ETF_ISSUERS, DATABASE_URL
from etf_track.db import clear_etf_data
from etf_track.pykrx_active import collect_pykrx_active_for_date, list_pykrx_active_etfs


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Reset ETF tables and backfill domestic active ETFs from PyKRX."
    )
    parser.add_argument("--days", type=int, default=31, help="Number of recent weekdays to collect.")
    parser.add_argument("--yes", action="store_true", help="Required to delete existing ETF data.")
    parser.add_argument(
        "--pause",
        type=float,
        default=1.0,
        help="Seconds to wait between ETF portfolio downloads.",
    )
    parser.add_argument(
        "--allow-sqlite",
        action="store_true",
        help="Allow deleting and backfilling the local SQLite database.",
    )
    args = parser.parse_args()

    if not args.yes:
        raise SystemExit("This deletes etf_holdings, etf_products, and krx_rows. Re-run with --yes to continue.")
    if DATABASE_URL.startswith("sqlite") and not args.allow_sqlite:
        raise SystemExit(
            "DATABASE_URL points to local SQLite, not Supabase. "
            "Fix .env or add --allow-sqlite if you really want local data."
        )

    print(f"DATABASE_URL={_masked_database_url(DATABASE_URL)}", flush=True)
    print(f"ALLOWED_ISSUERS={', '.join(ACTIVE_ETF_ISSUERS)}", flush=True)
    print("RESET etf_holdings, etf_products, krx_rows", flush=True)
    clear_etf_data()

    dates = recent_weekdays(args.days)
    total = 0
    for trade_date in dates:
        try:
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
            )
            total += count
            print(f"OK {trade_date.isoformat()} rows={count}", flush=True)
        except Exception as exc:
            print(f"SKIP {trade_date.isoformat()} {exc}", flush=True)
        time.sleep(2)

    print(f"Backfill complete rows={total}", flush=True)


def _masked_database_url(value: str) -> str:
    if "@" not in value or "://" not in value:
        return value
    scheme, rest = value.split("://", 1)
    user_part, host_part = rest.rsplit("@", 1)
    user = user_part.split(":", 1)[0]
    return f"{scheme}://{user}:***@{host_part}"


if __name__ == "__main__":
    main()
