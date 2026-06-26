from __future__ import annotations

from datetime import date
from io import BytesIO, StringIO
from typing import Any

import pandas as pd
import requests

from etf_track.config import KRX_COOKIE, KRX_EXTRA_PARAMS, KRX_MENU_ID, KRX_PASSWORD, KRX_STAT_URL, KRX_USERNAME

BASE_URL = "https://data.krx.co.kr"
HEADERS = {
    "User-Agent": "Mozilla/5.0",
    "Accept": "application/json, text/plain, */*",
    "Accept-Language": "ko-KR,ko;q=0.9,en-US;q=0.8,en;q=0.7",
}


def download_krx_pdf_rows(trade_date: date) -> pd.DataFrame:
    session = _login()
    otp = _generate_otp(session, trade_date)
    response = session.post(
        f"{BASE_URL}/comm/fileDn/download_csv/download.cmd",
        data={"code": otp},
        headers={
            "Referer": _referer(),
            "Content-Type": "application/x-www-form-urlencoded; charset=UTF-8",
        },
        timeout=30,
    )
    response.raise_for_status()
    return _read_download(response.content)


def _login() -> requests.Session:
    session = requests.Session()
    session.headers.update(HEADERS)
    if KRX_COOKIE:
        session.headers.update({"Cookie": KRX_COOKIE})
        return session

    if not KRX_USERNAME or not KRX_PASSWORD:
        raise RuntimeError("Set KRX_COOKIE, or set both KRX_USERNAME and KRX_PASSWORD")

    session.get(
        f"{BASE_URL}/contents/MDC/COMS/client/MDCCOMS001.cmd",
        params={"locale": "ko_KR", "redirectURL": f"/contents/MDC/MDI/mdiLoader/index.cmd?menuId={KRX_MENU_ID}"},
        timeout=30,
    )
    session.get(f"{BASE_URL}/contents/MDC/COMS/client/view/login.jsp", params={"site": "mdc"}, timeout=30)
    response = session.post(
        f"{BASE_URL}/contents/MDC/COMS/client/MDCCOMS001D1.cmd",
        data={"mbrId": KRX_USERNAME, "pw": KRX_PASSWORD},
        headers={
            "Referer": f"{BASE_URL}/contents/MDC/COMS/client/view/login.jsp?site=mdc",
            "Content-Type": "application/x-www-form-urlencoded; charset=UTF-8",
            "X-Requested-With": "XMLHttpRequest",
        },
        timeout=30,
    )
    response.raise_for_status()
    text = response.text.strip()
    if "LOGOUT" in text or "ERROR" in text or "CD" in text[:80]:
        raise RuntimeError(f"KRX login failed. Use a fresh KRX_COOKIE from a browser login. Response: {text[:120]}")
    return session


def _generate_otp(session: requests.Session, trade_date: date) -> str:
    params: dict[str, Any] = {
        "locale": "ko_KR",
        "trdDd": trade_date.strftime("%Y%m%d"),
        "csvxls_isNo": "false",
        "name": "fileDown",
        "url": KRX_STAT_URL,
    }
    params.update({k: v for k, v in KRX_EXTRA_PARAMS.items() if v is not None})
    response = session.post(
        f"{BASE_URL}/comm/fileDn/GenerateOTP/generate.cmd",
        data=params,
        headers={
            "Referer": _referer(),
            "Content-Type": "application/x-www-form-urlencoded; charset=UTF-8",
            "X-Requested-With": "XMLHttpRequest",
        },
        timeout=30,
    )
    response.raise_for_status()
    otp = response.text.strip()
    if not otp or otp == "LOGOUT" or "<html" in otp.lower():
        raise RuntimeError(f"KRX OTP failed: {otp[:120]}")
    return otp


def _read_download(content: bytes) -> pd.DataFrame:
    if content[:8].startswith(b"\xd0\xcf\x11\xe0") or content[:2] == b"PK":
        return pd.read_excel(BytesIO(content))

    for encoding in ("cp949", "euc-kr", "utf-8-sig", "utf-8"):
        try:
            text = content.decode(encoding)
            break
        except UnicodeDecodeError:
            continue
    else:
        text = content.decode("utf-8", errors="replace")

    if ("로그인" in text and "필요" in text) or "LOGOUT" in text:
        raise RuntimeError("KRX download requires a valid login session")
    return pd.read_csv(StringIO(text))


def _referer() -> str:
    return f"{BASE_URL}/contents/MDC/MDI/mdiLoader/index.cmd?menuId={KRX_MENU_ID}"
