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

To collect every active ETF from TIME and KODEX:

```bash
python jobs/collect_active_etfs.py
```

To backfill the recent month for every active ETF from TIME and KODEX:

```bash
python jobs/backfill_active_etfs_month.py
```

Korea market close plus data publication delay is safer around `18:30 KST`, which is `09:30 UTC`.

Render cron expression:

```text
30 9 * * MON-FRI
```

## KRX PDF Data

KRX menu `MDC0201030108` requires a logged-in session. Store credentials only in environment variables or deployment secrets:

```bash
KRX_USERNAME=your_id
KRX_PASSWORD=your_password
KRX_COOKIE=
KRX_MENU_ID=MDC0201030108
KRX_STAT_URL=dbms/MDC/STAT/standard/MDCSTAT13108
KRX_EXTRA_PARAMS={}
```

If the direct KRX login fails because of browser security scripts, log in to KRX in a browser and copy the fresh `Cookie` request header for `data.krx.co.kr` into `KRX_COOKIE`. When `KRX_COOKIE` is set, the collector skips username/password login and uses that browser session.

Backfill the recent month:

```bash
python jobs/backfill_krx_month.py
```

Collect one day:

```bash
python jobs/collect_krx.py
```

KRX rows are stored separately in `krx_rows` as raw JSON so the original columns are preserved. Check the API with:

```text
/api/krx/dates
/api/krx/summary
/api/krx/rows?trade_date=2026-06-25
```

On Render, trigger a background KRX backfill with:

```text
/api/admin/krx/backfill?token=YOUR_BACKFILL_TOKEN&days=31
/api/admin/krx/backfill/status?token=YOUR_BACKFILL_TOKEN
```

## Active ETF Backfill

The app discovers active ETFs from:

- `https://timeetf.co.kr/m31.php`
- `https://www.samsungfund.com/etf/product/library/pdf.do`

On Render, trigger a background active ETF backfill with:

```text
/api/admin/active/backfill?token=YOUR_BACKFILL_TOKEN&days=31
/api/admin/active/backfill/status?token=YOUR_BACKFILL_TOKEN
```

Check discovered products with:

```text
/api/products
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

## Sector Exposure

Edit `data/security_sectors.csv` to classify holdings by market and sector:

```text
ticker,isin,name,market,sector
005930,KR7005930003,삼성전자,KOSPI,기술주
000660,KR7000660001,SK하이닉스,KOSPI,기술주
```

The dashboard shows market/sector exposure from:

```text
/api/exposure?trade_date=2026-06-25&group_by=sector
/api/exposure?trade_date=2026-06-25&group_by=market
```
