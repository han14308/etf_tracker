from __future__ import annotations

from datetime import date
from io import BytesIO

import pandas as pd
import requests

HEADERS = {
    "User-Agent": "Mozilla/5.0",
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
    response = requests.get(
        "https://www.samsungfund.com/excel_pdf.do",
        params={"fId": fid, "gijunYMD": trade_date.strftime("%Y%m%d")},
        headers={**HEADERS, "Referer": "https://www.samsungfund.com/etf/product/library/pdf.do"},
        timeout=30,
    )
    response.raise_for_status()
    return _read_excel(response.content)
