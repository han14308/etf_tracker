from __future__ import annotations

from datetime import date
from typing import Any

import pandas as pd

from etf_track.db import (
    fetch_holdings,
    fetch_products,
    upsert_etf_daily_stats,
    upsert_security_daily_stats,
)


def collect_market_stats_for_date(trade_date: date) -> dict[str, int]:
    security_records = list_security_daily_stats(trade_date)
    etf_records = list_etf_daily_stats(trade_date)
    return {
        "security_daily_stats": upsert_security_daily_stats(security_records),
        "etf_daily_stats": upsert_etf_daily_stats(etf_records),
    }


def list_security_daily_stats(trade_date: date) -> list[dict[str, Any]]:
    tickers = sorted(
        {
            str(row.get("ticker") or "").strip()
            for row in fetch_holdings(trade_date=trade_date)
            if _is_real_krx_ticker(row.get("ticker"))
        }
    )
    if not tickers:
        return []

    ymd = trade_date.strftime("%Y%m%d")
    try:
        from pykrx import stock

        ohlcv = stock.get_market_ohlcv_by_ticker(ymd, market="ALL")
        market_cap = stock.get_market_cap_by_ticker(ymd, market="ALL")
    except Exception as exc:
        print(f"SECURITY_STATS_FETCH_FAILED {trade_date.isoformat()}: {exc}", flush=True)
        return []

    name_by_ticker = _holding_name_by_ticker(trade_date)
    isin_by_ticker = _holding_isin_by_ticker(trade_date)
    rows = []
    for ticker in tickers:
        ohlcv_record = _record_for_index(ohlcv, ticker)
        cap_record = _record_for_index(market_cap, ticker)
        if not ohlcv_record and not cap_record:
            continue
        rows.append(
            {
                "trade_date": trade_date,
                "ticker": ticker,
                "isin": isin_by_ticker.get(ticker),
                "name": name_by_ticker.get(ticker),
                "close_price": _field_number(ohlcv_record, "종가"),
                "trading_value": _field_number(ohlcv_record, "거래대금") or _field_number(cap_record, "거래대금"),
                "market_cap": _field_number(cap_record, "시가총액"),
                "listed_shares": _field_number(cap_record, "상장주식수"),
            }
        )
    return rows


def list_etf_daily_stats(trade_date: date) -> list[dict[str, Any]]:
    ymd = trade_date.strftime("%Y%m%d")
    products = fetch_products(active_only=True)
    product_by_ticker = {
        str(product.get("ticker") or product.get("source_id") or "").strip(): product
        for product in products
        if product.get("ticker") or product.get("source_id")
    }
    if not product_by_ticker:
        return []

    frame = _fetch_etf_all_stats_frame(ymd)
    if frame is None or frame.empty:
        return []

    rows = []
    for ticker, record in _frame_records_by_ticker(frame).items():
        product = product_by_ticker.get(ticker)
        if not product:
            continue
        close_price = _field_number(record, "종가", "TDD_CLSPRC")
        nav = _field_number(record, "NAV", "LST_NAV")
        rows.append(
            {
                "trade_date": trade_date,
                "etf_code": product["etf_code"],
                "ticker": ticker,
                "isin": (product.get("data") or {}).get("isin"),
                "name": product.get("name") or _field_text(record, "종목명", "ISU_ABBRV"),
                "close_price": close_price,
                "nav": nav,
                "deviation_rate": _deviation_rate(close_price, nav),
                "trading_value": _field_number(record, "거래대금", "ACC_TRDVAL"),
                "market_cap": _field_number(record, "시가총액", "MKTCAP"),
                "net_asset": _field_number(record, "순자산총액", "INVSTASST_NETASST_TOTAMT"),
                "listed_shares": _field_number(record, "상장좌수", "상장주식수", "LIST_SHRS"),
                "index_value": _field_number(record, "기초지수", "OBJ_STKPRC_IDX"),
            }
        )
    return rows


def _fetch_etf_all_stats_frame(ymd: str) -> pd.DataFrame | None:
    try:
        from pykrx.website.krx.etx.core import 전종목시세_ETF

        raw = 전종목시세_ETF().fetch(ymd)
        if raw is not None and not raw.empty:
            return raw
    except Exception as exc:
        print(f"ETF_STATS_RAW_FETCH_FAILED {ymd}: {exc}", flush=True)

    try:
        from pykrx import stock

        return stock.get_etf_ohlcv_by_ticker(ymd)
    except Exception as exc:
        print(f"ETF_STATS_FETCH_FAILED {ymd}: {exc}", flush=True)
        return None


def _frame_records_by_ticker(frame: pd.DataFrame) -> dict[str, dict[str, Any]]:
    if frame is None or frame.empty:
        return {}
    records: dict[str, dict[str, Any]] = {}
    for index, record in frame.iterrows():
        data = dict(record)
        ticker = _field_text(data, "티커", "ISU_SRT_CD") or str(index)
        ticker = ticker.strip()
        if _is_real_krx_ticker(ticker):
            records[ticker] = data
    return records


def _holding_name_by_ticker(trade_date: date) -> dict[str, str]:
    return {
        str(row.get("ticker")): str(row.get("name") or "")
        for row in fetch_holdings(trade_date=trade_date)
        if _is_real_krx_ticker(row.get("ticker"))
    }


def _holding_isin_by_ticker(trade_date: date) -> dict[str, str]:
    return {
        str(row.get("ticker")): str(row.get("isin") or "")
        for row in fetch_holdings(trade_date=trade_date)
        if _is_real_krx_ticker(row.get("ticker")) and row.get("isin")
    }


def _record_for_index(frame: pd.DataFrame, ticker: str) -> dict[str, Any]:
    if frame is None or frame.empty:
        return {}
    try:
        record = frame.loc[ticker]
    except Exception:
        return {}
    if isinstance(record, pd.DataFrame):
        record = record.iloc[0]
    return dict(record)


def _field_text(record: dict[str, Any], *names: str) -> str | None:
    for name in names:
        value = record.get(name)
        if value is None:
            continue
        text = str(value).replace(",", "").strip()
        if text and text.lower() not in {"nan", "none", "null", "-"}:
            return text
    return None


def _field_number(record: dict[str, Any], *names: str) -> float | None:
    text = _field_text(record, *names)
    if text is None:
        return None
    try:
        return float(text)
    except Exception:
        return None


def _deviation_rate(close_price: float | None, nav: float | None) -> float | None:
    if close_price is None or nav is None or nav == 0:
        return None
    return (close_price - nav) / nav * 100


def _is_real_krx_ticker(value: Any) -> bool:
    text = str(value or "").strip()
    return text.isdigit() and len(text) == 6 and int(text) >= 1000
