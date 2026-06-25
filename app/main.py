from __future__ import annotations

from datetime import date
from pathlib import Path

from fastapi import FastAPI, HTTPException, Query
from fastapi.responses import HTMLResponse

from etf_track.backfill import get_backfill_status, start_backfill
from etf_track.config import BACKFILL_TOKEN
from etf_track.krx_backfill import get_krx_backfill_status, start_krx_backfill
from etf_track.db import (
    fetch_compare,
    fetch_dates,
    fetch_holdings,
    fetch_krx_dates,
    fetch_krx_rows,
    fetch_krx_summary,
    fetch_security_history,
    fetch_summary,
    init_db,
)

app = FastAPI(title="ETF Track")


@app.on_event("startup")
def startup() -> None:
    init_db()


@app.get("/", response_class=HTMLResponse)
def dashboard() -> str:
    return (Path(__file__).parent / "static" / "index.html").read_text(encoding="utf-8")


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


@app.get("/api/compare")
def compare(
    trade_date: date | None = Query(default=None),
    left: str = Query(default="TIME_KOSPI_ACTIVE"),
    right: str = Query(default="KODEX_200"),
) -> list[dict]:
    return fetch_compare(trade_date=trade_date, left=left, right=right)


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
    started = start_backfill(days)
    status = get_backfill_status()
    return {"started": started, "status": status}


@app.get("/api/admin/backfill/status")
def backfill_status(token: str = Query(default="")) -> dict:
    if not BACKFILL_TOKEN or token != BACKFILL_TOKEN:
        raise HTTPException(status_code=403, detail="Invalid backfill token")
    return get_backfill_status()


@app.post("/api/admin/krx/backfill")
@app.get("/api/admin/krx/backfill")
def trigger_krx_backfill(
    token: str = Query(default=""),
    days: int = Query(default=31, ge=1, le=31),
) -> dict:
    if not BACKFILL_TOKEN or token != BACKFILL_TOKEN:
        raise HTTPException(status_code=403, detail="Invalid backfill token")
    started = start_krx_backfill(days)
    status = get_krx_backfill_status()
    return {"started": started, "status": status}


@app.get("/api/admin/krx/backfill/status")
def krx_backfill_status(token: str = Query(default="")) -> dict:
    if not BACKFILL_TOKEN or token != BACKFILL_TOKEN:
        raise HTTPException(status_code=403, detail="Invalid backfill token")
    return get_krx_backfill_status()
