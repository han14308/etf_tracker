from __future__ import annotations

from datetime import datetime, timezone
import threading
import time

from etf_track.calendar import recent_weekdays
from etf_track.db import upsert_products
from etf_track.products import list_all_active_etfs
from jobs.collect_active_etfs import collect_active_for_date

_lock = threading.Lock()
_status = {
    "running": False,
    "started_at": None,
    "finished_at": None,
    "days": 0,
    "total_rows": 0,
    "messages": [],
}


def get_active_backfill_status() -> dict:
    with _lock:
        return dict(_status)


def start_active_backfill(days: int) -> bool:
    with _lock:
        if _status["running"]:
            return False
        _status.update(
            {
                "running": True,
                "started_at": datetime.now(timezone.utc).isoformat(),
                "finished_at": None,
                "days": days,
                "total_rows": 0,
                "messages": [],
            }
        )

    thread = threading.Thread(target=_run_active_backfill, args=(days,), daemon=True)
    thread.start()
    return True


def _add_message(message: str) -> None:
    print(message, flush=True)
    with _lock:
        messages = list(_status["messages"])
        messages.append(message)
        _status["messages"] = messages[-120:]


def _run_active_backfill(days: int) -> None:
    total = 0
    try:
        products = list_all_active_etfs()
        upsert_products([product.to_dict() for product in products])
        _add_message(f"ACTIVE_PRODUCTS count={len(products)}")
        for trade_date in recent_weekdays(days):
            try:
                count = collect_active_for_date(trade_date, products=products)
                total += count
                _add_message(f"OK {trade_date.isoformat()} rows={count}")
            except Exception as exc:
                _add_message(f"SKIP {trade_date.isoformat()} {exc}")
            time.sleep(2)
        _add_message(f"Active ETF backfill complete rows={total}")
    except Exception as exc:
        _add_message(f"FAILED active ETF backfill: {exc}")
    finally:
        with _lock:
            _status["running"] = False
            _status["finished_at"] = datetime.now(timezone.utc).isoformat()
            _status["total_rows"] = total
