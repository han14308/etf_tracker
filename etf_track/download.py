from __future__ import annotations

from datetime import date
from io import BytesIO
import time

import pandas as pd
import requests

HEADERS = {
    "User-Agent": "Mozilla/5.0",
    "Accept": "application/json, text/plain, */*",
    "Accept-Language": "ko-KR,ko;q=0.9,en-US;q=0.8,en;q=0.7",
}


def _read_excel(content: bytes) -> pd.DataFrame:
    raw = pd.read_excel(BytesIO(content), header=None)
    header_row = _find_header_row(raw)
    if header_row is None:
        return pd.read_excel(BytesIO(content))
    return pd.read_excel(BytesIO(content), header=header_row)


def _find_header_row(raw: pd.DataFrame) -> int | None:
    keywords = {"종목코드", "종목명"}
    for idx, row in raw.head(30).iterrows():
        values = {str(v).strip() for v in row.tolist() if pd.notna(v)}
        if len(keywords.intersection(values)) >= 2:
            return int(idx)
    return None


def download_time_holdings(idx: int, trade_date: date) -> pd.DataFrame:
    response = requests.get(
        "https://timeetf.co.kr/pdf_excel.php",
        params={"idx": idx, "pdfDate": trade_date.isoformat()},
        headers={**HEADERS, "Referer": f"https://timeetf.co.kr/m11_view.php?idx={idx}#constituentItems"},
        timeout=30,
    )
    response.raise_for_status()
    return _read_excel(response.content)


def download_kodex_holdings(fid: str, trade_date: date) -> pd.DataFrame:
    json_frame = _download_kodex_holdings_json(fid, trade_date)
    if not json_frame.empty:
        return json_frame

    last_error: Exception | None = None
    for attempt in range(5):
        try:
            response = requests.get(
                "https://www.samsungfund.com/excel_pdf.do",
                params={"fId": fid, "gijunYMD": trade_date.strftime("%Y%m%d")},
                headers={**HEADERS, "Referer": "https://www.samsungfund.com/etf/product/library/pdf.do"},
                timeout=30,
            )
            if response.status_code == 429:
                time.sleep(10 + attempt * 15)
                continue
            response.raise_for_status()
            return _read_excel(response.content)
        except Exception as exc:
            last_error = exc
            time.sleep(3 + attempt * 5)
    if last_error:
        raise last_error
    raise RuntimeError("KODEX Excel download failed without a response")


def _download_kodex_holdings_json(fid: str, trade_date: date) -> pd.DataFrame:
    session = requests.Session()
    session.headers.update(HEADERS)
    referer = "https://www.samsungfund.com/etf/product/library/pdf.do"
    params = {"gijunYMD": trade_date.strftime("%Y.%m.%d")}

    last_error: Exception | None = None
    for attempt in range(3):
        try:
            response = session.get(
                f"https://www.samsungfund.com/api/v1/kodex/product-pdf/{fid}.do",
                params=params,
                headers={"Referer": referer},
                timeout=30,
            )
            if response.status_code == 429:
                time.sleep(2 + attempt * 3)
                continue
            response.raise_for_status()
            payload = response.json()
            pdf = payload.get("pdf") or {}
            rows = pdf.get("list") or []
            return pd.DataFrame(rows)
        except Exception as exc:
            last_error = exc
            time.sleep(1 + attempt)

    if last_error:
        raise last_error
    return pd.DataFrame()
