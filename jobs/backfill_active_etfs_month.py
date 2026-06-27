from __future__ import annotations

from pathlib import Path
import sys
import time

ROOT_DIR = Path(__file__).resolve().parents[1]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from etf_track.calendar import recent_weekdays
from etf_track.db import upsert_products
from etf_track.products import list_all_active_etfs
from jobs.collect_active_etfs import collect_active_for_date


def main() -> None:
    total = 0
    products = list_all_active_etfs()
    upsert_products([product.to_dict() for product in products])
    print(f"ACTIVE_PRODUCTS count={len(products)}", flush=True)
    for trade_date in recent_weekdays(31):
        try:
            count = collect_active_for_date(trade_date, products=products)
            total += count
            print(f"OK {trade_date.isoformat()} rows={count}", flush=True)
        except Exception as exc:
            print(f"SKIP {trade_date.isoformat()} {exc}", flush=True)
        time.sleep(2)
    print(f"Active ETF backfill complete rows={total}", flush=True)


if __name__ == "__main__":
    main()
