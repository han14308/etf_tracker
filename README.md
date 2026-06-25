# ETF Track

KODEX 200 and TIME 코스피액티브 holdings tracker.

The project downloads daily holdings Excel files, normalizes them, maps tickers to ISINs, stores the result in a database, and serves a small dashboard/API.

## Local Setup

```bash
python -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt
copy .env.example .env
python jobs/backfill_month.py
uvicorn app.main:app --reload
```

Open `http://127.0.0.1:8000`.

## Environment

`DATABASE_URL` is optional locally. If omitted, the app uses SQLite at `data/etf_track.db`.

For production, set `DATABASE_URL` to a Postgres URL, for example Supabase or Render Postgres.

## Daily Collection

Run this after market close:

```bash
python jobs/collect_holdings.py
```

Korea market close plus data publication delay is safer around `18:30 KST`, which is `09:30 UTC`.

Render cron expression:

```text
30 9 * * MON-FRI
```

## ISIN Mapping

Edit `data/security_master.csv`.

Columns:

```text
ticker,name,isin
005930,삼성전자,KR7005930003
000660,SK하이닉스,KR7000660001
```

Unknown tickers are stored with `isin = null`. Cash rows are stored as `CASH_KRW`.
