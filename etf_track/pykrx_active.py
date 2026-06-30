from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import date
import os
import time
from typing import Any

import pandas as pd

from etf_track.config import ACTIVE_ETF_ISSUERS, KRX_COOKIE, KRX_PASSWORD, KRX_USERNAME
from etf_track.filters import is_equity_active_etf_name


class KrxAuthRequiredError(RuntimeError):
    pass


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
    try:
        ticker_names = _get_etf_ticker_names(stock, ymd)
    except RuntimeError as exc:
        return _list_active_etfs_from_search(trade_date, allowed_issuers, exc)

    for ticker, name, isin in ticker_names:
        if not is_equity_active_etf_name(name):
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
                data={"provider": "pykrx", "trade_date": ymd, "isin": isin},
            )
        )
    return products


def validate_pykrx_active_access(
    trade_date: date,
    issuers: list[str] | set[str] | tuple[str, ...] | None = None,
) -> list[PykrxEtfProduct]:
    products = list_pykrx_active_etfs(trade_date, issuers=issuers)
    if not products:
        raise RuntimeError(
            f"PyKRX returned no active ETF products for {trade_date.isoformat()}. "
            "Check the date and PyKRX/KRX connectivity before resetting data."
        )
    return products


def download_pykrx_active_holdings(product: PykrxEtfProduct, trade_date: date) -> pd.DataFrame:
    stock = _stock_module()
    ymd = trade_date.strftime("%Y%m%d")
    raw = _get_etf_portfolio_deposit_file(stock, product, ymd)
    if raw is None or raw.empty:
        return _empty_frame()

    frame = raw.reset_index()
    ticker_col = _find_column(frame, ["\ud2f0\ucee4", "index", "\uc885\ubaa9\ucf54\ub4dc", "COMPST_ISU_CD"])
    name_col = _find_column(frame, ["\uad6c\uc131\uc885\ubaa9\uba85", "\uc885\ubaa9\uba85", "COMPST_ISU_NM"])
    quantity_col = _find_column(frame, ["\uacc4\uc57d\uc218", "\uc218\ub7c9", "COMPST_ISU_CU1_SHRS"])
    value_col = _find_column(frame, ["\uae08\uc561", "\ud3c9\uac00\uae08\uc561", "VALU_AMT", "COMPST_AMT"])
    weight_col = _find_column(frame, ["\ube44\uc911", "COMPST_RTO"])

    rows = []
    for record in frame.to_dict("records"):
        ticker = _normalize_ticker(record.get(ticker_col) if ticker_col else None)
        name = _coerce_text(record.get(name_col) if name_col else None) or _security_name(stock, ticker)
        rows.append(
            {
                "trade_date": trade_date,
                "etf_code": product.etf_code,
                "isin": None,
                "ticker": ticker,
                "name": name,
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
    products: list[PykrxEtfProduct] | None = None,
) -> int:
    from etf_track.db import upsert_holdings, upsert_products

    if products is None:
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
    if KRX_USERNAME:
        os.environ.setdefault("KRX_ID", KRX_USERNAME)
    if KRX_PASSWORD:
        os.environ.setdefault("KRX_PW", KRX_PASSWORD)
    try:
        from pykrx import stock
    except ImportError as exc:
        raise RuntimeError("pykrx is not installed. Run `pip install -r requirements-collector.txt`.") from exc
    return stock


def _get_etf_ticker_names(stock: Any, ymd: str) -> list[tuple[str, str, str | None]]:
    tickers = _get_etf_ticker_list(stock, ymd)
    result = []
    for ticker in tickers:
        name = _coerce_text(stock.get_etf_ticker_name(ticker))
        result.append((str(ticker), name, _safe_get_etf_isin(stock, str(ticker))))
    return result


def _get_etf_ticker_list(stock: Any, ymd: str) -> list[str]:
    try:
        tickers = stock.get_etf_ticker_list(ymd)
    except KeyError as exc:
        missing_key = str(exc).strip("'\"")
        raise RuntimeError(
            f"PyKRX failed to read ETF ticker data for {ymd}; missing response field {missing_key!r}. "
            "This usually means the KRX response was empty or changed shape. "
            "If you see a KRX login warning, set KRX_ID/KRX_PW or KRX_USERNAME/KRX_PASSWORD."
        ) from exc
    except Exception as exc:
        raise RuntimeError(f"PyKRX failed to fetch ETF tickers for {ymd}: {exc}") from exc
    return [str(ticker) for ticker in tickers]


def _list_active_etfs_from_search(
    trade_date: date,
    allowed_issuers: set[str],
    original_exc: Exception,
) -> list[PykrxEtfProduct]:
    ymd = trade_date.strftime("%Y%m%d")
    try:
        frame = _fetch_etf_search_frame()
    except Exception as exc:
        raise RuntimeError(f"{original_exc}; ETF search fallback also failed: {exc}") from original_exc

    required_columns = {"full_code", "short_code", "codeName"}
    if frame.empty or not required_columns.issubset({str(column) for column in frame.columns}):
        raise RuntimeError(f"{original_exc}; ETF search fallback returned no usable rows.") from original_exc

    products: list[PykrxEtfProduct] = []
    for record in frame.to_dict("records"):
        ticker = str(record.get("short_code") or "").strip()
        name = str(record.get("codeName") or "").strip()
        isin = str(record.get("full_code") or "").strip() or None
        if not ticker or not is_equity_active_etf_name(name):
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
                data={"provider": "pykrx_search_fallback", "trade_date": ymd, "isin": isin},
            )
        )
    return products


def _fetch_etf_search_frame() -> pd.DataFrame:
    import importlib

    etx_core = importlib.import_module("pykrx.website.krx.etx.core")
    search_cls = getattr(etx_core, "\uc0c1\uc7a5\uc885\ubaa9\uac80\uc0c9")
    return search_cls().fetch("ETF")


def _get_etf_portfolio_deposit_file(stock: Any, product: PykrxEtfProduct, ymd: str) -> pd.DataFrame:
    isin = _product_isin(product)
    if isin:
        try:
            import importlib

            etx_core = importlib.import_module("pykrx.website.krx.etx.core")
            pdf_cls = getattr(etx_core, "PDF")
            frame = pdf_cls().fetch(ymd, isin)
            if frame is not None and not frame.empty:
                return frame
        except Exception as exc:
            print(f"PYKRX_PDF_DIRECT_FAIL {ymd} {product.ticker} {isin}: {exc}", flush=True)

        frame = _fetch_pdf_frame_direct(ymd, isin)
        if frame is not None and not frame.empty:
            return frame

        raise RuntimeError(f"KRX PDF returned no rows for {product.ticker} {product.name} on {ymd} using ISIN {isin}")
    return stock.get_etf_portfolio_deposit_file(product.ticker, ymd)


def _fetch_pdf_frame_direct(ymd: str, isin: str) -> pd.DataFrame:
    import requests

    session = requests.Session()
    headers = {
        "User-Agent": "Mozilla/5.0",
        "Accept": "application/json, text/plain, */*",
        "Accept-Language": "ko-KR,ko;q=0.9,en-US;q=0.8,en;q=0.7",
        "Referer": "https://data.krx.co.kr/contents/MDC/MDI/outerLoader/index.cmd",
        "X-Requested-With": "XMLHttpRequest",
    }
    if KRX_COOKIE:
        headers["Cookie"] = KRX_COOKIE
    session.get(
        "https://data.krx.co.kr/contents/MDC/MDI/outerLoader/index.cmd",
        headers=headers,
        timeout=30,
    )
    response = session.post(
        "https://data.krx.co.kr/comm/bldAttendant/getJsonData.cmd",
        data={
            "bld": "dbms/MDC/STAT/standard/MDCSTAT05001",
            "locale": "ko_KR",
            "trdDd": ymd,
            "isuCd": isin,
            "csvxls_isNo": "false",
        },
        headers=headers,
        timeout=30,
    )
    if response.status_code >= 400:
        if "LOGOUT" in response.text:
            raise KrxAuthRequiredError("KRX PDF endpoint returned LOGOUT. Set a fresh KRX_COOKIE from data.krx.co.kr.")
        raise RuntimeError(f"KRX PDF HTTP {response.status_code}: {response.text[:200]}")
    data = response.json()
    rows = data.get("output") or data.get("block1") or []
    return pd.DataFrame(rows)


def _product_isin(product: PykrxEtfProduct) -> str | None:
    if not isinstance(product.data, dict):
        return None
    return _clean_text(product.data.get("isin"))


def _safe_get_etf_isin(stock: Any, ticker: str) -> str | None:
    try:
        return _clean_text(stock.get_etf_isin(ticker))
    except Exception:
        return None


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


def _clean_text(value: Any) -> str | None:
    if value is None or pd.isna(value):
        return None
    text = str(value).strip()
    if text == "" or text.lower() in {"nan", "none", "null"}:
        return None
    return text


def _coerce_text(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, pd.Series):
        value = value.dropna()
        if value.empty:
            return ""
        value = value.iloc[0]
    if pd.isna(value):
        return ""
    return str(value).strip()


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
