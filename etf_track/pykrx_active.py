from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import date
import time
from typing import Any

import pandas as pd

from etf_track.config import ACTIVE_ETF_ISSUERS

ACTIVE_KEYWORD = "\uc561\ud2f0\ube0c"


@dataclass(frozen=True)
class PykrxEtfProduct:
    issuer: str
    etf_code: str
    source_id: str
    name: str
    ticker: str
    is_active: bool = True
    data: dict | None = None

    def to_dict(self) -> dict:
        return asdict(self)


def list_pykrx_active_etfs(
    trade_date: date,
    issuers: list[str] | set[str] | tuple[str, ...] | None = None,
) -> list[PykrxEtfProduct]:
    stock = _stock_module()
    ymd = trade_date.strftime("%Y%m%d")
    allowed_issuers = _normalize_issuer_set(issuers or ACTIVE_ETF_ISSUERS)
    products: list[PykrxEtfProduct] = []
    tickers = stock.get_etf_ticker_list(ymd)
    for ticker in tickers:
        name = str(stock.get_etf_ticker_name(ticker) or "").strip()
        if ACTIVE_KEYWORD not in name:
            continue
        issuer = _issuer_from_name(name)
        if allowed_issuers and issuer.upper() not in allowed_issuers:
            continue
        products.append(
            PykrxEtfProduct(
                issuer=issuer,
                etf_code=f"KRX_{ticker}",
                source_id=ticker,
                name=name,
                ticker=ticker,
                data={"provider": "pykrx", "trade_date": ymd},
            )
        )
    return products


def download_pykrx_active_holdings(product: PykrxEtfProduct, trade_date: date) -> pd.DataFrame:
    stock = _stock_module()
    ymd = trade_date.strftime("%Y%m%d")
    raw = stock.get_etf_portfolio_deposit_file(product.ticker, ymd)
    if raw is None or raw.empty:
        return _empty_frame()

    frame = raw.reset_index()
    ticker_col = _find_column(frame, ["\ud2f0\ucee4", "index", "\uc885\ubaa9\ucf54\ub4dc"])
    quantity_col = _find_column(frame, ["\uacc4\uc57d\uc218", "\uc218\ub7c9"])
    value_col = _find_column(frame, ["\uae08\uc561", "\ud3c9\uac00\uae08\uc561"])
    weight_col = _find_column(frame, ["\ube44\uc911"])

    rows = []
    for record in frame.to_dict("records"):
        ticker = _normalize_ticker(record.get(ticker_col) if ticker_col else None)
        rows.append(
            {
                "trade_date": trade_date,
                "etf_code": product.etf_code,
                "isin": None,
                "ticker": ticker,
                "name": _security_name(stock, ticker),
                "quantity": _clean_number(record.get(quantity_col) if quantity_col else None),
                "market_value": _clean_number(record.get(value_col) if value_col else None),
                "weight": _clean_number(record.get(weight_col) if weight_col else None),
            }
        )
    return pd.DataFrame(rows)


def collect_pykrx_active_for_date(
    trade_date: date,
    pause_seconds: float = 1.0,
    issuers: list[str] | set[str] | tuple[str, ...] | None = None,
) -> int:
    from etf_track.db import upsert_holdings, upsert_products

    products = list_pykrx_active_etfs(trade_date, issuers=issuers)
    upsert_products([product.to_dict() for product in products])
    print(f"PYKRX_ACTIVE_PRODUCTS date={trade_date.isoformat()} count={len(products)}", flush=True)

    total = 0
    for product in products:
        try:
            print(f"START {trade_date.isoformat()} {product.etf_code} {product.name}", flush=True)
            frame = download_pykrx_active_holdings(product, trade_date)
            count = upsert_holdings(frame)
            total += count
            print(f"DONE {trade_date.isoformat()} {product.etf_code} rows={count}", flush=True)
        except Exception as exc:
            print(f"SKIP {trade_date.isoformat()} {product.etf_code} {product.name}: {exc}", flush=True)
        time.sleep(pause_seconds)
    return total


def _empty_frame() -> pd.DataFrame:
    return pd.DataFrame(columns=["trade_date", "etf_code", "isin", "ticker", "name", "quantity", "market_value", "weight"])


def _stock_module():
    try:
        from pykrx import stock
    except ImportError as exc:
        raise RuntimeError("pykrx is not installed. Run `pip install -r requirements-collector.txt`.") from exc
    return stock


def _issuer_from_name(name: str) -> str:
    return name.split()[0] if name.split() else "KRX"


def _normalize_issuer_set(issuers: list[str] | set[str] | tuple[str, ...]) -> set[str]:
    return {str(issuer).strip().upper() for issuer in issuers if str(issuer).strip()}


def _find_column(frame: pd.DataFrame, candidates: list[str]) -> str | None:
    columns = {str(column).strip().lower(): column for column in frame.columns}
    for candidate in candidates:
        key = candidate.strip().lower()
        if key in columns:
            return columns[key]
    for column in frame.columns:
        text = str(column).strip().lower()
        if any(candidate.strip().lower() in text for candidate in candidates):
            return column
    return None


def _normalize_ticker(value: Any) -> str:
    if value is None or pd.isna(value):
        return "CASH"
    text = str(value).strip()
    if text == "" or text.lower() in {"nan", "none", "null"}:
        return "CASH"
    if text.isdigit():
        return text.zfill(6)
    return text


def _security_name(stock: Any, ticker: str) -> str:
    if ticker == "CASH":
        return "\ud604\uae08"
    try:
        name = stock.get_market_ticker_name(ticker)
        if name:
            return str(name)
    except Exception:
        pass
    return ticker


def _clean_number(value: Any) -> float | None:
    if value is None or pd.isna(value):
        return None
    text = str(value).replace(",", "").replace("%", "").strip()
    if text == "" or text == "-":
        return None
    try:
        return float(text)
    except ValueError:
        return None
