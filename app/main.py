from __future__ import annotations

from datetime import date
import os
from pathlib import Path

from fastapi import FastAPI, HTTPException, Query
from fastapi.responses import HTMLResponse

from etf_track.config import ACTIVE_BACKFILL_ON_START_DAYS, BACKFILL_TOKEN
from etf_track.db import (
    fetch_compare,
    fetch_dates,
    fetch_etf_daily_stats,
    fetch_exposure,
    fetch_holding_history,
    fetch_holdings,
    fetch_krx_dates,
    fetch_krx_rows,
    fetch_krx_summary,
    fetch_products,
    fetch_security_daily_stats,
    fetch_security_history,
    fetch_summary,
    init_db,
)
from etf_track.prices import fetch_close_history, fetch_market_dates

app = FastAPI(title="ETF Track")


@app.on_event("startup")
def startup() -> None:
    try:
        init_db()
    except Exception as exc:
        print(f"STARTUP_INIT_DB_FAILED {type(exc).__name__}: {exc}", flush=True)
    if ACTIVE_BACKFILL_ON_START_DAYS > 0:
        from etf_track.active_backfill import start_active_backfill

        started = start_active_backfill(ACTIVE_BACKFILL_ON_START_DAYS)
        print(
            f"ACTIVE_BACKFILL_ON_START startup days={ACTIVE_BACKFILL_ON_START_DAYS} started={started}",
            flush=True,
        )


@app.get("/", response_class=HTMLResponse)
def dashboard() -> str:
    return (Path(__file__).parent / "static" / "index.html").read_text(encoding="utf-8")


@app.get("/api/health")
def health() -> dict:
    database_url = os.getenv("DATABASE_URL", "")
    return {
        "ok": True,
        "database_url_set": bool(database_url),
        "database_url_scheme": database_url.split(":", 1)[0] if database_url else None,
        "active_backfill_on_start_days": ACTIVE_BACKFILL_ON_START_DAYS,
    }


@app.get("/api/dates")
def dates() -> list[str]:
    return [str(x) for x in fetch_dates()]


@app.get("/api/summary")
def summary(
    start: date | None = Query(default=None),
    end: date | None = Query(default=None),
) -> list[dict]:
    return fetch_summary(start=start, end=end)


@app.get("/api/holdings")
def holdings(
    trade_date: date | None = Query(default=None),
    etf_code: str | None = Query(default=None),
) -> list[dict]:
    return fetch_holdings(trade_date=trade_date, etf_code=etf_code)


@app.get("/api/holding-history")
def holding_history(
    etf_code: str = Query(default=""),
    ticker: str | None = Query(default=None),
    isin: str | None = Query(default=None),
    name: str | None = Query(default=None),
) -> list[dict]:
    return fetch_holding_history(etf_code=etf_code, ticker=ticker, isin=isin, name=name)


@app.get("/api/close-history")
def close_history(
    ticker: str = Query(default=""),
    start: date | None = Query(default=None),
    end: date | None = Query(default=None),
) -> list[dict]:
    return fetch_close_history(ticker=ticker, start=start, end=end)


@app.get("/api/market-dates")
def market_dates(
    start: date | None = Query(default=None),
    end: date | None = Query(default=None),
) -> list[str]:
    return fetch_market_dates(start=start, end=end)


@app.get("/api/security-daily-stats")
def security_daily_stats(
    ticker: str | None = Query(default=None),
    isin: str | None = Query(default=None),
    start: date | None = Query(default=None),
    end: date | None = Query(default=None),
) -> list[dict]:
    return fetch_security_daily_stats(ticker=ticker, isin=isin, start=start, end=end)


@app.get("/api/etf-daily-stats")
def etf_daily_stats(
    etf_code: str | None = Query(default=None),
    ticker: str | None = Query(default=None),
    start: date | None = Query(default=None),
    end: date | None = Query(default=None),
) -> list[dict]:
    return fetch_etf_daily_stats(etf_code=etf_code, ticker=ticker, start=start, end=end)


@app.get("/api/products")
def products(active_only: bool = Query(default=True)) -> list[dict]:
    return fetch_products(active_only=active_only)


@app.get("/api/compare")
def compare(
    trade_date: date | None = Query(default=None),
    left: str = Query(default="TIME_KOSPI_ACTIVE"),
    right: str = Query(default="KODEX_200"),
) -> list[dict]:
    return fetch_compare(trade_date=trade_date, left=left, right=right)


@app.get("/api/exposure")
def exposure(
    trade_date: date | None = Query(default=None),
    group_by: str = Query(default="sector"),
    left: str = Query(default="TIME_KOSPI_ACTIVE"),
    right: str = Query(default="KODEX_200"),
) -> list[dict]:
    return fetch_exposure(trade_date=trade_date, group_by=group_by, left=left, right=right)


@app.get("/api/security-history")
def security_history(
    ticker: str | None = Query(default=None),
    isin: str | None = Query(default=None),
    left: str = Query(default="TIME_KOSPI_ACTIVE"),
    right: str = Query(default="KODEX_200"),
) -> list[dict]:
    return fetch_security_history(ticker=ticker, isin=isin, left=left, right=right)


@app.get("/api/krx/dates")
def krx_dates() -> list[str]:
    return [str(x) for x in fetch_krx_dates()]


@app.get("/api/krx/summary")
def krx_summary(
    start: date | None = Query(default=None),
    end: date | None = Query(default=None),
) -> list[dict]:
    return fetch_krx_summary(start=start, end=end)


@app.get("/api/krx/rows")
def krx_rows(
    trade_date: date | None = Query(default=None),
    limit: int = Query(default=500, ge=1, le=5000),
) -> list[dict]:
    return fetch_krx_rows(trade_date=trade_date, limit=limit)


@app.post("/api/admin/backfill")
@app.get("/api/admin/backfill")
def trigger_backfill(
    token: str = Query(default=""),
    days: int = Query(default=3, ge=1, le=31),
) -> dict:
    if not BACKFILL_TOKEN or token != BACKFILL_TOKEN:
        raise HTTPException(status_code=403, detail="Invalid backfill token")
    from etf_track.backfill import get_backfill_status, start_backfill

    started = start_backfill(days)
    status = get_backfill_status()
    return {"started": started, "status": status}


@app.get("/api/admin/backfill/status")
def backfill_status(token: str = Query(default="")) -> dict:
    if not BACKFILL_TOKEN or token != BACKFILL_TOKEN:
        raise HTTPException(status_code=403, detail="Invalid backfill token")
    from etf_track.backfill import get_backfill_status

    return get_backfill_status()


@app.post("/api/admin/krx/backfill")
@app.get("/api/admin/krx/backfill")
def trigger_krx_backfill(
    token: str = Query(default=""),
    days: int = Query(default=31, ge=1, le=31),
) -> dict:
    if not BACKFILL_TOKEN or token != BACKFILL_TOKEN:
        raise HTTPException(status_code=403, detail="Invalid backfill token")
    from etf_track.krx_backfill import get_krx_backfill_status, start_krx_backfill

    started = start_krx_backfill(days)
    status = get_krx_backfill_status()
    return {"started": started, "status": status}


@app.get("/api/admin/krx/backfill/status")
def krx_backfill_status(token: str = Query(default="")) -> dict:
    if not BACKFILL_TOKEN or token != BACKFILL_TOKEN:
        raise HTTPException(status_code=403, detail="Invalid backfill token")
    from etf_track.krx_backfill import get_krx_backfill_status

    return get_krx_backfill_status()


@app.post("/api/admin/active/backfill")
@app.get("/api/admin/active/backfill")
def trigger_active_backfill(
    token: str = Query(default=""),
    days: int = Query(default=31, ge=1, le=31),
) -> dict:
    if not BACKFILL_TOKEN or token != BACKFILL_TOKEN:
        raise HTTPException(status_code=403, detail="Invalid backfill token")
    from etf_track.active_backfill import get_active_backfill_status, start_active_backfill

    started = start_active_backfill(days)
    status = get_active_backfill_status()
    return {"started": started, "status": status}


@app.get("/api/admin/active/backfill/status")
def active_backfill_status(token: str = Query(default="")) -> dict:
    if not BACKFILL_TOKEN or token != BACKFILL_TOKEN:
        raise HTTPException(status_code=403, detail="Invalid backfill token")
    from etf_track.active_backfill import get_active_backfill_status

    return get_active_backfill_status()


@app.get("/api/active/backfill/status")
def public_active_backfill_status() -> dict:
    from etf_track.active_backfill import get_active_backfill_status

    return get_active_backfill_status()
