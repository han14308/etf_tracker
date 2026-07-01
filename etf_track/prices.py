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
    stored = _fetch_stored_close_history(ticker, start=start, end=end)
    if stored:
        return stored
    return _fetch_close_history_cached(ticker, from_ymd, to_ymd)


def _fetch_stored_close_history(
    ticker: str,
    start: date | None = None,
    end: date | None = None,
) -> list[dict[str, Any]]:
    try:
        from etf_track.db import fetch_security_daily_stats
    except Exception:
        return []

    rows = fetch_security_daily_stats(ticker=ticker, start=start, end=end)
    result = []
    for row in rows:
        close = row.get("close_price")
        if close is None:
            continue
        result.append(
            {
                "trade_date": row["trade_date"],
                "ticker": ticker,
                "close_price": close,
            }
        )
    return result


def fetch_market_dates(
    start: date | None = None,
    end: date | None = None,
    ticker: str = "005930",
) -> list[str]:
    ticker = str(ticker or "005930").strip()
    if not ticker.isdigit() or len(ticker) != 6:
        ticker = "005930"

    from_ymd = (start or date(2020, 1, 1)).strftime("%Y%m%d")
    to_ymd = (end or date.today()).strftime("%Y%m%d")
    return _fetch_market_dates_cached(ticker, from_ymd, to_ymd)


@lru_cache(maxsize=2048)
def _fetch_close_history_cached(ticker: str, from_ymd: str, to_ymd: str) -> list[dict[str, Any]]:
    try:
        from pykrx import stock
    except Exception:
        return []

    try:
        frame = stock.get_market_ohlcv_by_date(from_ymd, to_ymd, ticker, adjusted=False)
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


@lru_cache(maxsize=512)
def _fetch_market_dates_cached(ticker: str, from_ymd: str, to_ymd: str) -> list[str]:
    try:
        from pykrx import stock
    except Exception:
        return []

    try:
        frame = stock.get_market_ohlcv_by_date(from_ymd, to_ymd, ticker)
    except Exception as exc:
        print(f"MARKET_DATES_FETCH_FAILED {ticker} {from_ymd}-{to_ymd}: {exc}", flush=True)
        return []

    if frame is None or frame.empty:
        return []
    return [index.strftime("%Y-%m-%d") for index in frame.index]
