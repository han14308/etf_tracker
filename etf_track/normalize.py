from __future__ import annotations

from datetime import date

import pandas as pd

from etf_track.config import SECURITY_MASTER_PATH

COL_ALIASES = {
    "ticker": ["종목코드", "코드", "Ticker", "ticker", "itmNo"],
    "name": ["종목명", "종목", "Name", "secNm", "holding_nm"],
    "quantity": ["수량", "보유수량", "Number of Shares", "applyQ"],
    "market_value": ["평가금액(원)", "평가금액", "평가액", "Fair Value(KRW)", "evalA"],
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
    selected["ticker"] = selected["ticker"].map(_normalize_ticker)
    selected["name"] = selected["name"].astype(str).str.strip()
    selected = selected[selected["name"].ne("")]
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
        df["isin"] = df["ticker"].map(lambda x: "CASH_KRW" if x == "CASH" else None)
        return df
    df = df.merge(master[["ticker", "isin"]], on="ticker", how="left")
    df.loc[df["ticker"].eq("CASH"), "isin"] = "CASH_KRW"
    df["isin"] = df["isin"].where(df["isin"].notna(), None)
    return df


def _load_security_master() -> pd.DataFrame:
    if not SECURITY_MASTER_PATH.exists():
        return pd.DataFrame(columns=["ticker", "isin"])
    master = pd.read_csv(SECURITY_MASTER_PATH, dtype=str)
    master["ticker"] = master["ticker"].map(_normalize_ticker)
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
    if "현금" in text or "예금" in text:
        return "CASH"
    text = text.split(".")[0].replace(",", "")
    if text.isdigit():
        return text.zfill(6)
    return text


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
