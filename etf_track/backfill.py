from __future__ import annotations

import threading
import time
from datetime import datetime, timezone

from etf_track.calendar import recent_weekdays
from jobs.collect_holdings import collect_for_date

_lock = threading.Lock()
_status = {
    "running": False,
    "started_at": None,
    "finished_at": None,
    "days": 0,
    "total_rows": 0,
    "messages": [],
}


def get_backfill_status() -> dict:
    with _lock:
        return dict(_status)


def start_backfill(days: int) -> bool:
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

    thread = threading.Thread(target=_run_backfill, args=(days,), daemon=True)
    thread.start()
    return True


def _add_message(message: str) -> None:
    print(message, flush=True)
    with _lock:
        messages = list(_status["messages"])
        messages.append(message)
        _status["messages"] = messages[-80:]


def _run_backfill(days: int) -> None:
    total = 0
    try:
        for trade_date in recent_weekdays(days):
            try:
                count = collect_for_date(trade_date)
                total += count
                _add_message(f"OK {trade_date.isoformat()} rows={count}")
            except Exception as exc:
                _add_message(f"SKIP {trade_date.isoformat()} {exc}")
            time.sleep(1)
        _add_message(f"Backfill complete rows={total}")
    finally:
        with _lock:
            _status["running"] = False
            _status["finished_at"] = datetime.now(timezone.utc).isoformat()
            _status["total_rows"] = total
