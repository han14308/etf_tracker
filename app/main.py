from __future__ import annotations

from datetime import date
from pathlib import Path

from fastapi import FastAPI, Query
from fastapi.responses import HTMLResponse

from etf_track.db import fetch_compare, fetch_dates, fetch_holdings, fetch_summary, init_db

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
