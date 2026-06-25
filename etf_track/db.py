from __future__ import annotations

from datetime import date
from decimal import Decimal
from functools import lru_cache
from typing import Any

import pandas as pd
from sqlalchemy import Date, MetaData, Numeric, String, Table, create_engine, delete, desc, func, select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.engine import Engine
from sqlalchemy.sql import insert

from etf_track.config import DATABASE_URL

metadata = MetaData()

holdings = Table(
    "etf_holdings",
    metadata,
    # Date + ETF + ticker is the practical uniqueness key. ISIN can be null for unknown rows.
    # SQLAlchemy primary key handles SQLite and Postgres consistently here.
    __import__("sqlalchemy").Column("trade_date", Date, primary_key=True),
    __import__("sqlalchemy").Column("etf_code", String(64), primary_key=True),
    __import__("sqlalchemy").Column("ticker", String(32), primary_key=True),
    __import__("sqlalchemy").Column("isin", String(32), nullable=True),
    __import__("sqlalchemy").Column("name", String(255), nullable=False),
    __import__("sqlalchemy").Column("quantity", Numeric(24, 6), nullable=True),
    __import__("sqlalchemy").Column("market_value", Numeric(24, 2), nullable=True),
    __import__("sqlalchemy").Column("weight", Numeric(12, 6), nullable=True),
)


@lru_cache(maxsize=1)
def get_engine() -> Engine:
    database_url = DATABASE_URL
    if database_url.startswith("postgresql://"):
        database_url = database_url.replace("postgresql://", "postgresql+psycopg://", 1)
    connect_args: dict[str, Any] = {"check_same_thread": False} if database_url.startswith("sqlite") else {}
    if database_url.startswith("postgresql"):
        connect_args["prepare_threshold"] = None
        return create_engine(
            database_url,
            future=True,
            connect_args=connect_args,
            pool_pre_ping=True,
            pool_size=1,
            max_overflow=0,
            pool_recycle=300,
        )
    return create_engine(database_url, future=True, connect_args=connect_args, pool_pre_ping=True)


def init_db() -> None:
    metadata.create_all(get_engine())


def _clean_number(value: Any) -> Decimal | None:
    if pd.isna(value) or value == "":
        return None
    if isinstance(value, str):
        value = value.replace(",", "").replace("%", "").strip()
    try:
        return Decimal(str(value))
    except Exception:
        return None


def _clean_text(value: Any) -> str | None:
    if value is None or pd.isna(value):
        return None
    text = str(value).strip()
    if text == "" or text.lower() in {"nan", "none", "null"}:
        return None
    return text


def upsert_holdings(df: pd.DataFrame) -> int:
    if df.empty:
        return 0

    init_db()
    rows = []
    for record in df.to_dict("records"):
        rows.append(
            {
                "trade_date": record["trade_date"],
                "etf_code": record["etf_code"],
                "ticker": str(record["ticker"]),
                "isin": _clean_text(record.get("isin")),
                "name": str(record["name"]),
                "quantity": _clean_number(record.get("quantity")),
                "market_value": _clean_number(record.get("market_value")),
                "weight": _clean_number(record.get("weight")),
            }
        )

    engine = get_engine()
    with engine.begin() as conn:
        if engine.dialect.name == "postgresql":
            stmt = pg_insert(holdings).values(rows)
            stmt = stmt.on_conflict_do_update(
                index_elements=["trade_date", "etf_code", "ticker"],
                set_={
                    "isin": stmt.excluded.isin,
                    "name": stmt.excluded.name,
                    "quantity": stmt.excluded.quantity,
                    "market_value": stmt.excluded.market_value,
                    "weight": stmt.excluded.weight,
                },
            )
            conn.execute(stmt)
        else:
            keys = {(r["trade_date"], r["etf_code"]) for r in rows}
            for trade_date, etf_code in keys:
                conn.execute(delete(holdings).where(holdings.c.trade_date == trade_date, holdings.c.etf_code == etf_code))
            conn.execute(insert(holdings), rows)
    return len(rows)


def fetch_dates() -> list[date]:
    init_db()
    stmt = select(holdings.c.trade_date).distinct().order_by(holdings.c.trade_date.desc()).limit(90)
    with get_engine().connect() as conn:
        return list(conn.execute(stmt).scalars())


def _row_to_dict(row: Any) -> dict:
    data = dict(row._mapping)
    for key, value in list(data.items()):
        if isinstance(value, Decimal):
            data[key] = float(value)
        elif isinstance(value, date):
            data[key] = value.isoformat()
    return data


def fetch_holdings(trade_date: date | None = None, etf_code: str | None = None) -> list[dict]:
    init_db()
    stmt = select(holdings)
    if trade_date:
        stmt = stmt.where(holdings.c.trade_date == trade_date)
    if etf_code:
        stmt = stmt.where(holdings.c.etf_code == etf_code)
    stmt = stmt.order_by(holdings.c.trade_date.desc(), holdings.c.etf_code, desc(holdings.c.weight))
    with get_engine().connect() as conn:
        return [_row_to_dict(row) for row in conn.execute(stmt)]


def fetch_summary(start: date | None = None, end: date | None = None) -> list[dict]:
    init_db()
    stmt = (
        select(
            holdings.c.trade_date,
            holdings.c.etf_code,
            func.count().label("holding_count"),
            func.sum(holdings.c.weight).label("total_weight"),
        )
        .group_by(holdings.c.trade_date, holdings.c.etf_code)
        .order_by(holdings.c.trade_date.desc(), holdings.c.etf_code)
    )
    if start:
        stmt = stmt.where(holdings.c.trade_date >= start)
    if end:
        stmt = stmt.where(holdings.c.trade_date <= end)
    with get_engine().connect() as conn:
        return [_row_to_dict(row) for row in conn.execute(stmt)]


def fetch_compare(trade_date: date | None = None, left: str = "TIME_KOSPI_ACTIVE", right: str = "KODEX_200") -> list[dict]:
    init_db()
    if trade_date is None:
        dates = fetch_dates()
        if not dates:
            return []
        trade_date = dates[0]

    records = fetch_holdings(trade_date=trade_date)
    by_key: dict[str, dict] = {}
    for row in records:
        if row["etf_code"] not in {left, right}:
            continue
        isin = _clean_text(row["isin"])
        key = isin or row["ticker"]
        bucket = by_key.setdefault(
            key,
            {
                "trade_date": str(trade_date),
                "isin": isin,
                "ticker": row["ticker"],
                "name": row["name"],
                "time_weight": 0.0,
                "time_quantity": None,
                "time_market_value": None,
                "kodex_weight": 0.0,
                "kodex_quantity": None,
                "kodex_market_value": None,
            },
        )
        if row["etf_code"] == left:
            bucket["time_weight"] = float(row["weight"] or 0)
            bucket["time_quantity"] = row["quantity"]
            bucket["time_market_value"] = row["market_value"]
            bucket["name"] = row["name"]
        elif row["etf_code"] == right:
            bucket["kodex_weight"] = float(row["weight"] or 0)
            bucket["kodex_quantity"] = row["quantity"]
            bucket["kodex_market_value"] = row["market_value"]

    result = []
    for row in by_key.values():
        row["weight_diff"] = row["time_weight"] - row["kodex_weight"]
        result.append(row)
    return result


def fetch_security_history(
    ticker: str | None = None,
    isin: str | None = None,
    left: str = "TIME_KOSPI_ACTIVE",
    right: str = "KODEX_200",
) -> list[dict]:
    init_db()
    ticker = _clean_text(ticker)
    isin = _clean_text(isin)
    if not ticker and not isin:
        return []

    stmt = select(holdings).where(holdings.c.etf_code.in_([left, right]))
    if isin:
        stmt = stmt.where(holdings.c.isin == isin)
    else:
        stmt = stmt.where(holdings.c.ticker == ticker)
    stmt = stmt.order_by(holdings.c.trade_date.asc(), holdings.c.etf_code)

    with get_engine().connect() as conn:
        records = [_row_to_dict(row) for row in conn.execute(stmt)]

    by_date: dict[str, dict] = {}
    for row in records:
        trade_date = row["trade_date"]
        bucket = by_date.setdefault(
            trade_date,
            {
                "trade_date": trade_date,
                "ticker": row["ticker"],
                "isin": row["isin"],
                "name": row["name"],
                "time_weight": 0.0,
                "time_quantity": None,
                "time_market_value": None,
                "kodex_weight": 0.0,
                "kodex_quantity": None,
                "kodex_market_value": None,
            },
        )
        if row["etf_code"] == left:
            bucket["time_weight"] = float(row["weight"] or 0)
            bucket["time_quantity"] = row["quantity"]
            bucket["time_market_value"] = row["market_value"]
            bucket["name"] = row["name"]
        elif row["etf_code"] == right:
            bucket["kodex_weight"] = float(row["weight"] or 0)
            bucket["kodex_quantity"] = row["quantity"]
            bucket["kodex_market_value"] = row["market_value"]
    result = list(by_date.values())
    for row in result:
        row["weight_diff"] = row["time_weight"] - row["kodex_weight"]
    return result
