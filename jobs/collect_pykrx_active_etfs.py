from __future__ import annotations

from datetime import date, timedelta
from pathlib import Path
import sys

ROOT_DIR = Path(__file__).resolve().parents[1]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from etf_track.pykrx_active import collect_pykrx_active_for_date


def latest_business_day(today: date | None = None) -> date:
    current = today or date.today()
    if current.weekday() == 5:
        return current - timedelta(days=1)
    if current.weekday() == 6:
        return current - timedelta(days=2)
    return current


if __name__ == "__main__":
    target = latest_business_day()
    count = collect_pykrx_active_for_date(target)
    print(f"Collected {count} pykrx active ETF holding rows for {target.isoformat()}")
