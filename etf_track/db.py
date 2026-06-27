from __future__ import annotations

from datetime import date
from decimal import Decimal
from functools import lru_cache
import hashlib
import json
from typing import Any

import pandas as pd
from sqlalchemy import Boolean, Date, JSON, MetaData, Numeric, String, Table, create_engine, delete, desc, func, select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.engine import Engine
from sqlalchemy.sql import insert

from etf_track.config import DATABASE_URL, SECURITY_SECTOR_PATH

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

krx_rows = Table(
    "krx_rows",
    metadata,
    __import__("sqlalchemy").Column("trade_date", Date, primary_key=True),
    __import__("sqlalchemy").Column("source", String(64), primary_key=True),
    __import__("sqlalchemy").Column("row_hash", String(64), primary_key=True),
    __import__("sqlalchemy").Column("ticker", String(32), nullable=True),
    __import__("sqlalchemy").Column("isin", String(32), nullable=True),
    __import__("sqlalchemy").Column("name", String(255), nullable=True),
    __import__("sqlalchemy").Column("data", JSON, nullable=False),
)

etf_products = Table(
    "etf_products",
    metadata,
    __import__("sqlalchemy").Column("etf_code", String(64), primary_key=True),
    __import__("sqlalchemy").Column("issuer", String(32), nullable=False),
    __import__("sqlalchemy").Column("source_id", String(64), nullable=False),
    __import__("sqlalchemy").Column("name", String(255), nullable=False),
    __import__("sqlalchemy").Column("ticker", String(32), nullable=True),
    __import__("sqlalchemy").Column("is_active", Boolean, nullable=False, default=True),
    __import__("sqlalchemy").Column("data", JSON, nullable=True),
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


def _sum_decimal(left: Decimal | None, right: Decimal | None) -> Decimal | None:
    if left is None:
        return right
    if right is None:
        return left
    return left + right


def upsert_holdings(df: pd.DataFrame) -> int:
    if df.empty:
        return 0

    init_db()
    by_key: dict[tuple[Any, str, str], dict[str, Any]] = {}
    for record in df.to_dict("records"):
        row = {
            "trade_date": record["trade_date"],
            "etf_code": record["etf_code"],
            "ticker": str(record["ticker"]),
            "isin": _clean_text(record.get("isin")),
            "name": str(record["name"]),
            "quantity": _clean_number(record.get("quantity")),
            "market_value": _clean_number(record.get("market_value")),
            "weight": _clean_number(record.get("weight")),
        }
        key = (row["trade_date"], row["etf_code"], row["ticker"])
        if key in by_key:
            existing = by_key[key]
            existing["quantity"] = _sum_decimal(existing["quantity"], row["quantity"])
            existing["market_value"] = _sum_decimal(existing["market_value"], row["market_value"])
            existing["weight"] = _sum_decimal(existing["weight"], row["weight"])
            if row["isin"]:
                existing["isin"] = row["isin"]
            if row["name"] and row["name"] not in existing["name"].split(" / "):
                existing["name"] = f'{existing["name"]} / {row["name"]}'
        else:
            by_key[key] = row
    rows = list(by_key.values())

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


def upsert_krx_rows(df: pd.DataFrame, trade_date: date, source: str = "KRX_PDF") -> int:
    if df.empty:
        return 0

    init_db()
    rows = []
    for record in df.to_dict("records"):
        clean_record = {_clean_text(k) or str(k): _json_value(v) for k, v in record.items()}
        row_hash = hashlib.sha256(
            json.dumps(clean_record, ensure_ascii=False, sort_keys=True, default=str).encode("utf-8")
        ).hexdigest()
        rows.append(
            {
                "trade_date": trade_date,
                "source": source,
                "row_hash": row_hash,
                "ticker": _guess_field(clean_record, ["종목코드", "단축코드", "isuSrtCd", "ISU_SRT_CD", "ticker"]),
                "isin": _guess_field(clean_record, ["ISIN", "표준코드", "isin", "ISU_CD"]),
                "name": _guess_field(clean_record, ["종목명", "한글종목명", "isuKorNm", "ISU_NM", "name"]),
                "data": clean_record,
            }
        )

    engine = get_engine()
    with engine.begin() as conn:
        if engine.dialect.name == "postgresql":
            stmt = pg_insert(krx_rows).values(rows)
            stmt = stmt.on_conflict_do_update(
                index_elements=["trade_date", "source", "row_hash"],
                set_={
                    "ticker": stmt.excluded.ticker,
                    "isin": stmt.excluded.isin,
                    "name": stmt.excluded.name,
                    "data": stmt.excluded.data,
                },
            )
            conn.execute(stmt)
        else:
            conn.execute(delete(krx_rows).where(krx_rows.c.trade_date == trade_date, krx_rows.c.source == source))
            conn.execute(insert(krx_rows), rows)
    return len(rows)


def upsert_products(products: list[dict[str, Any]]) -> int:
    if not products:
        return 0

    init_db()
    rows = []
    for product in products:
        rows.append(
            {
                "etf_code": str(product["etf_code"]),
                "issuer": str(product["issuer"]),
                "source_id": str(product["source_id"]),
                "name": str(product["name"]),
                "ticker": _clean_text(product.get("ticker")),
                "is_active": bool(product.get("is_active", True)),
                "data": product.get("data") or {},
            }
        )

    engine = get_engine()
    with engine.begin() as conn:
        if engine.dialect.name == "postgresql":
            stmt = pg_insert(etf_products).values(rows)
            stmt = stmt.on_conflict_do_update(
                index_elements=["etf_code"],
                set_={
                    "issuer": stmt.excluded.issuer,
                    "source_id": stmt.excluded.source_id,
                    "name": stmt.excluded.name,
                    "ticker": stmt.excluded.ticker,
                    "is_active": stmt.excluded.is_active,
                    "data": stmt.excluded.data,
                },
            )
            conn.execute(stmt)
        else:
            for row in rows:
                conn.execute(delete(etf_products).where(etf_products.c.etf_code == row["etf_code"]))
            conn.execute(insert(etf_products), rows)
    return len(rows)


def fetch_products(active_only: bool = True) -> list[dict]:
    init_db()
    stmt = select(etf_products).order_by(etf_products.c.issuer, etf_products.c.name)
    if active_only:
        stmt = stmt.where(etf_products.c.is_active.is_(True))
    with get_engine().connect() as conn:
        return [_row_to_dict(row) for row in conn.execute(stmt)]


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


def fetch_holding_history(
    etf_code: str,
    ticker: str | None = None,
    isin: str | None = None,
) -> list[dict]:
    init_db()
    ticker = _clean_text(ticker)
    isin = _clean_text(isin)
    if not etf_code or (not ticker and not isin):
        return []

    stmt = select(holdings).where(holdings.c.etf_code == etf_code)
    if isin:
        stmt = stmt.where(holdings.c.isin == isin)
    else:
        stmt = stmt.where(holdings.c.ticker == ticker)
    stmt = stmt.order_by(holdings.c.trade_date.asc())

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
            func.sum(holdings.c.market_value).label("total_market_value"),
            func.sum(holdings.c.quantity).label("total_quantity"),
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


def fetch_exposure(
    trade_date: date | None = None,
    group_by: str = "sector",
    left: str = "TIME_KOSPI_ACTIVE",
    right: str = "KODEX_200",
) -> list[dict]:
    if group_by not in {"sector", "market"}:
        group_by = "sector"

    rows = fetch_compare(trade_date=trade_date, left=left, right=right)
    if not rows:
        return []

    sector_master = _load_sector_master()
    by_group: dict[str, dict] = {}
    for row in rows:
        meta = _find_security_meta(sector_master, row.get("ticker"), row.get("isin"))
        group = meta.get(group_by) or "미분류"
        bucket = by_group.setdefault(
            group,
            {
                "group": group,
                "time_weight": 0.0,
                "kodex_weight": 0.0,
                "time_market_value": 0.0,
                "kodex_market_value": 0.0,
                "time_count": 0,
                "kodex_count": 0,
                "common_count": 0,
            },
        )
        time_weight = float(row.get("time_weight") or 0)
        kodex_weight = float(row.get("kodex_weight") or 0)
        bucket["time_weight"] += time_weight
        bucket["kodex_weight"] += kodex_weight
        bucket["time_market_value"] += float(row.get("time_market_value") or 0)
        bucket["kodex_market_value"] += float(row.get("kodex_market_value") or 0)
        if time_weight > 0:
            bucket["time_count"] += 1
        if kodex_weight > 0:
            bucket["kodex_count"] += 1
        if time_weight > 0 and kodex_weight > 0:
            bucket["common_count"] += 1

    result = list(by_group.values())
    for row in result:
        row["weight_diff"] = row["time_weight"] - row["kodex_weight"]
    return sorted(result, key=lambda row: max(row["time_weight"], row["kodex_weight"]), reverse=True)


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


def fetch_krx_dates(source: str = "KRX_PDF") -> list[date]:
    init_db()
    stmt = select(krx_rows.c.trade_date).where(krx_rows.c.source == source).distinct().order_by(krx_rows.c.trade_date.desc()).limit(90)
    with get_engine().connect() as conn:
        return list(conn.execute(stmt).scalars())


def fetch_krx_rows(trade_date: date | None = None, source: str = "KRX_PDF", limit: int = 500) -> list[dict]:
    init_db()
    stmt = select(krx_rows).where(krx_rows.c.source == source).order_by(krx_rows.c.trade_date.desc()).limit(limit)
    if trade_date:
        stmt = stmt.where(krx_rows.c.trade_date == trade_date)
    with get_engine().connect() as conn:
        return [_row_to_dict(row) for row in conn.execute(stmt)]


def fetch_krx_summary(start: date | None = None, end: date | None = None, source: str = "KRX_PDF") -> list[dict]:
    init_db()
    stmt = (
        select(
            krx_rows.c.trade_date,
            krx_rows.c.source,
            func.count().label("row_count"),
            func.count(krx_rows.c.ticker).label("ticker_count"),
            func.count(krx_rows.c.isin).label("isin_count"),
        )
        .where(krx_rows.c.source == source)
        .group_by(krx_rows.c.trade_date, krx_rows.c.source)
        .order_by(krx_rows.c.trade_date.desc())
    )
    if start:
        stmt = stmt.where(krx_rows.c.trade_date >= start)
    if end:
        stmt = stmt.where(krx_rows.c.trade_date <= end)
    with get_engine().connect() as conn:
        return [_row_to_dict(row) for row in conn.execute(stmt)]


def _json_value(value: Any) -> Any:
    if pd.isna(value):
        return None
    if isinstance(value, Decimal):
        return float(value)
    if isinstance(value, date):
        return value.isoformat()
    if hasattr(value, "item"):
        return value.item()
    return value


def _guess_field(record: dict[str, Any], candidates: list[str]) -> str | None:
    normalized = {str(key).replace(" ", "").lower(): value for key, value in record.items()}
    for candidate in candidates:
        value = normalized.get(candidate.replace(" ", "").lower())
        text = _clean_text(value)
        if text:
            return text
    return None


@lru_cache(maxsize=1)
def _load_sector_master() -> dict[str, dict[str, str]]:
    if not SECURITY_SECTOR_PATH.exists():
        return {}
    frame = pd.read_csv(SECURITY_SECTOR_PATH, dtype=str).fillna("")
    frame.columns = [str(col).strip().lower() for col in frame.columns]
    result: dict[str, dict[str, str]] = {}
    for record in frame.to_dict("records"):
        ticker = _clean_text(record.get("ticker"))
        isin = _clean_text(record.get("isin"))
        meta = {
            "ticker": ticker or "",
            "isin": isin or "",
            "name": _clean_text(record.get("name")) or "",
            "market": _clean_text(record.get("market")) or "",
            "sector": _clean_text(record.get("sector")) or "",
        }
        if ticker:
            result[f"ticker:{ticker}"] = meta
        if isin:
            result[f"isin:{isin}"] = meta
    return result


def _find_security_meta(master: dict[str, dict[str, str]], ticker: Any, isin: Any) -> dict[str, str]:
    isin_text = _clean_text(isin)
    ticker_text = _clean_text(ticker)
    if isin_text and f"isin:{isin_text}" in master:
        return master[f"isin:{isin_text}"]
    if ticker_text and f"ticker:{ticker_text}" in master:
        return master[f"ticker:{ticker_text}"]
    return {}
