from __future__ import annotations

from dataclasses import asdict, dataclass
from html import unescape
import re

import requests

from etf_track.download import HEADERS


@dataclass(frozen=True)
class EtfProduct:
    issuer: str
    etf_code: str
    source_id: str
    name: str
    ticker: str | None = None
    is_active: bool = True
    data: dict | None = None

    def to_dict(self) -> dict:
        return asdict(self)


def list_time_active_etfs() -> list[EtfProduct]:
    response = requests.get(
        "https://timeetf.co.kr/m31.php",
        headers={**HEADERS, "Referer": "https://timeetf.co.kr/"},
        timeout=30,
    )
    response.raise_for_status()

    products: dict[str, EtfProduct] = {}
    pattern = re.compile(
        r'<a\s+href="\./m11_view\.php\?idx=(\d+)[^"]*">\s*<div\s+class="name">(.+?)</div>',
        re.IGNORECASE | re.DOTALL,
    )
    for idx, name_html in pattern.findall(response.text):
        name = _strip_tags(name_html)
        if "액티브" not in name:
            continue
        products[idx] = EtfProduct(
            issuer="TIME",
            etf_code=f"TIME_{idx}",
            source_id=idx,
            name=name,
            data={"url": f"https://timeetf.co.kr/m11_view.php?idx={idx}"},
        )
    return list(products.values())


def list_kodex_active_etfs() -> list[EtfProduct]:
    session = requests.Session()
    session.headers.update({**HEADERS, "Referer": "https://www.samsungfund.com/etf/product/library/pdf.do"})

    products: dict[str, EtfProduct] = {}
    page = 1
    total_count: int | None = None
    while True:
        response = session.get(
            "https://www.samsungfund.com/api/v1/kodex/product.do",
            params={
                "ordrColm": "YIELD_WEEK",
                "ordrSort": "DESC",
                "pageNo": page,
                "pageRows": 100,
                "srchTerm": "w",
                "srchVal": "액티브",
            },
            timeout=30,
        )
        response.raise_for_status()
        rows = response.json()
        if not rows:
            break

        for row in rows:
            name = str(row.get("fNm") or "").strip()
            fid = str(row.get("fId") or "").strip()
            if not fid or "액티브" not in name:
                continue
            if total_count is None:
                total_count = _to_int(row.get("totalCnt"))
            products[fid] = EtfProduct(
                issuer="KODEX",
                etf_code=f"KODEX_{fid}",
                source_id=fid,
                name=name,
                ticker=_clean_text(row.get("stkTicker")),
                data={
                    "ticker": _clean_text(row.get("stkTicker")),
                    "type": _clean_text(row.get("typeNm")),
                    "theme": _clean_text(row.get("typeLnm")),
                    "nav": _clean_text(row.get("nav")),
                    "gijunYMD": _clean_text(row.get("gijunYMD")),
                },
            )

        if total_count is not None and len(products) >= total_count:
            break
        if page >= 20:
            break
        page += 1

    return list(products.values())


def list_all_active_etfs() -> list[EtfProduct]:
    return [*list_time_active_etfs(), *list_kodex_active_etfs()]


def _strip_tags(value: str) -> str:
    text = re.sub(r"<[^>]+>", "", unescape(value))
    return re.sub(r"\s+", " ", text).strip()


def _clean_text(value: object) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    return text or None


def _to_int(value: object) -> int | None:
    text = _clean_text(value)
    if not text:
        return None
    try:
        return int(text.replace(",", ""))
    except ValueError:
        return None
