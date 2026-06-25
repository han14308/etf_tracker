from __future__ import annotations

from datetime import date, timedelta


def recent_weekdays(days: int, end: date | None = None) -> list[date]:
    end = end or date.today()
    out: list[date] = []
    current = end
    while len(out) < days:
        if current.weekday() < 5:
            out.append(current)
        current -= timedelta(days=1)
    return list(reversed(out))
