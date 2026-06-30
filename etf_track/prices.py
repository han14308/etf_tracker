from __future__ import annotations

from datetime import date
from functools import lru_cache
from typing import Any


def fetch_close_history(
    ticker: str,
    start: date | None = None,
    end: date | None = None,
) -> list[dict[str, Any]]:
    ticker = str(ticker or "").strip()
    if not ticker.isdigit() or len(ticker) != 6:
        return []

    from_ymd = (start or date(2020, 1, 1)).strftime("%Y%m%d")
    to_ymd = (end or date.today()).strftime("%Y%m%d")
    return _fetch_close_history_cached(ticker, from_ymd, to_ymd)


@lru_cache(maxsize=2048)
def _fetch_close_history_cached(ticker: str, from_ymd: str, to_ymd: str) -> list[dict[str, Any]]:
    try:
        from pykrx import stock
    except Exception:
        return []

    try:
        frame = stock.get_market_ohlcv_by_date(from_ymd, to_ymd, ticker)
    except Exception as exc:
        print(f"CLOSE_HISTORY_FETCH_FAILED {ticker} {from_ymd}-{to_ymd}: {exc}", flush=True)
        return []

    if frame is None or frame.empty or "종가" not in frame.columns:
        return []

    rows: list[dict[str, Any]] = []
    for index, record in frame.iterrows():
        close = record.get("종가")
        try:
            close_value = float(close)
        except Exception:
            continue
        if close_value <= 0:
            continue
        rows.append(
            {
                "trade_date": index.strftime("%Y-%m-%d"),
                "ticker": ticker,
                "close_price": close_value,
            }
        )
    return rows
