from __future__ import annotations

from datetime import date

import pandas as pd

from etf_track.config import SECURITY_MASTER_PATH

COL_ALIASES = {
    "isin": ["ISIN", "isin", "isinCd", "isuCd", "ISU_CD", "표준코드"],
    "ticker": ["종목코드", "단축코드", "코드", "Ticker", "ticker", "itmNo", "isuSrtCd", "ISU_SRT_CD"],
    "name": ["종목명", "한글종목명", "Name", "secNm", "holding_nm", "isuKorNm", "ISU_NM"],
    "quantity": ["수량", "보유수량", "주식수", "Number of Shares", "applyQ"],
    "market_value": ["평가금액(원)", "평가금액", "평가 금액", "Fair Value(KRW)", "evalA"],
    "weight": ["비중(%)", "비중", "Weight(%)", "ratio"],
}


def normalize_holdings(df: pd.DataFrame, etf_code: str, trade_date: date) -> pd.DataFrame:
    df = df.copy()
    df.columns = [str(c).strip() for c in df.columns]
    selected = pd.DataFrame()
    for target, aliases in COL_ALIASES.items():
        col = _find_column(df, aliases)
        selected[target] = df[col] if col else None

    selected = selected.dropna(subset=["name"], how="all")
    selected["isin"] = selected["isin"].map(_clean_isin)
    selected["ticker"] = selected["ticker"].map(_normalize_ticker)
    selected["name"] = selected["name"].astype(str).str.strip()
    selected = selected[selected["name"].ne("")]
    selected.loc[selected["name"].map(_is_cash_name), "ticker"] = "CASH"
    selected.loc[selected["ticker"].eq("CASH"), "isin"] = "CASH_KRW"
    selected["quantity"] = selected["quantity"].map(_clean_number)
    selected["market_value"] = selected["market_value"].map(_clean_number)
    selected["weight"] = selected["weight"].map(_clean_number)
    selected["etf_code"] = etf_code
    selected["trade_date"] = trade_date
    selected = attach_isin(selected)
    return selected[["trade_date", "etf_code", "isin", "ticker", "name", "quantity", "market_value", "weight"]]


def attach_isin(df: pd.DataFrame) -> pd.DataFrame:
    df = df.copy()
    master = _load_security_master()
    if master.empty:
        df["isin"] = df.apply(lambda row: row["isin"] or _auto_isin(row["ticker"]), axis=1)
        return df

    df = df.merge(master[["ticker", "isin"]], on="ticker", how="left", suffixes=("", "_master"))
    df["isin"] = df.apply(lambda row: row["isin"] or row["isin_master"] or _auto_isin(row["ticker"]), axis=1)
    return df.drop(columns=["isin_master"])


def _load_security_master() -> pd.DataFrame:
    if not SECURITY_MASTER_PATH.exists():
        return pd.DataFrame(columns=["ticker", "isin"])
    master = pd.read_csv(SECURITY_MASTER_PATH, dtype=str)
    master["ticker"] = master["ticker"].map(_normalize_ticker)
    master["isin"] = master["isin"].map(_clean_isin)
    return master


def _find_column(df: pd.DataFrame, aliases: list[str]) -> str | None:
    normalized = {str(col).strip().lower(): col for col in df.columns}
    for alias in aliases:
        key = alias.strip().lower()
        if key in normalized:
            return normalized[key]
    for col in df.columns:
        col_text = str(col).strip().lower()
        if any(alias.strip().lower() in col_text for alias in aliases):
            return col
    return None


def _normalize_ticker(value: object) -> str:
    if pd.isna(value):
        return "CASH"
    text = str(value).strip()
    if text in {"", "nan", "None"}:
        return "CASH"
    if any(keyword in text for keyword in ["현금", "예금", "원화"]) or text.startswith("KRD"):
        return "CASH"
    text = text.split(".")[0].replace(",", "")
    if text.isdigit():
        return text.zfill(6)
    return text


def _is_cash_name(value: object) -> bool:
    if pd.isna(value):
        return False
    text = str(value)
    return any(keyword in text for keyword in ["현금", "예금", "원화"])


def _clean_isin(value: object) -> str | None:
    if pd.isna(value):
        return None
    text = str(value).strip().upper()
    if text in {"", "-", "NAN", "NONE", "NULL"}:
        return None
    return text


def _auto_isin(ticker: object) -> str | None:
    ticker_text = _normalize_ticker(ticker)
    if ticker_text == "CASH":
        return "CASH_KRW"
    if not ticker_text.isdigit() or len(ticker_text) != 6:
        return None
    body = f"KR7{ticker_text}00"
    return body + str(_isin_check_digit(body))


def _isin_check_digit(body: str) -> int:
    expanded = "".join(str(ord(ch) - 55) if ch.isalpha() else ch for ch in body.upper())
    total = 0
    for idx, digit in enumerate(reversed(expanded)):
        value = int(digit)
        if idx % 2 == 0:
            value *= 2
        total += value // 10 + value % 10
    return (10 - total % 10) % 10


def _clean_number(value: object) -> float | None:
    if pd.isna(value):
        return None
    text = str(value).replace(",", "").replace("%", "").strip()
    if text in {"", "-", "nan", "None"}:
        return None
    try:
        return float(text)
    except ValueError:
        return None
