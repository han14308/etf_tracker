from __future__ import annotations

import argparse
from datetime import date
from pathlib import Path
import sys
import time

ROOT_DIR = Path(__file__).resolve().parents[1]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from etf_track.calendar import recent_weekdays, weekdays_between
from etf_track.config import ACTIVE_ETF_ISSUERS, DATABASE_URL
from etf_track.db import clear_etf_data
from etf_track.pykrx_active import (
    KrxAuthRequiredError,
    PykrxEtfProduct,
    collect_pykrx_active_for_date,
    download_pykrx_active_holdings,
    list_pykrx_active_etfs,
    validate_pykrx_active_access,
)


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Reset ETF tables and backfill domestic active ETFs from PyKRX."
    )
    parser.add_argument("--days", type=int, default=31, help="Number of recent weekdays to collect.")
    parser.add_argument("--start", type=date.fromisoformat, default=None, help="Start date YYYY-MM-DD.")
    parser.add_argument("--end", type=date.fromisoformat, default=None, help="End date YYYY-MM-DD.")
    parser.add_argument("--yes", action="store_true", help="Required to delete existing ETF data.")
    parser.add_argument(
        "--pause",
        type=float,
        default=1.0,
        help="Seconds to wait between ETF portfolio downloads.",
    )
    parser.add_argument(
        "--allow-sqlite",
        action="store_true",
        help="Allow deleting and backfilling the local SQLite database.",
    )
    args = parser.parse_args()

    if not args.yes:
        raise SystemExit("This deletes etf_holdings, etf_products, and krx_rows. Re-run with --yes to continue.")
    if DATABASE_URL.startswith("sqlite") and not args.allow_sqlite:
        raise SystemExit(
            "DATABASE_URL points to local SQLite, not Supabase. "
            "Fix .env or add --allow-sqlite if you really want local data."
        )

    dates = weekdays_between(args.start, args.end) if args.start and args.end else recent_weekdays(args.days)

    print(f"DATABASE_URL={_masked_database_url(DATABASE_URL)}", flush=True)
    print(f"ALLOWED_ISSUERS={', '.join(ACTIVE_ETF_ISSUERS)}", flush=True)
    preflight_date, preflight_products = _find_preflight_date(dates)

    print("RESET etf_holdings, etf_products, krx_rows, security_daily_stats, etf_daily_stats", flush=True)
    clear_etf_data()

    total = 0
    for trade_date in dates:
        products = (
            preflight_products
            if trade_date == preflight_date
            else list_pykrx_active_etfs(trade_date, issuers=ACTIVE_ETF_ISSUERS)
        )
        print(
            f"PRODUCTS {trade_date.isoformat()} count={len(products)} "
            f"names={', '.join(product.name for product in products[:10])}",
            flush=True,
        )
        count = collect_pykrx_active_for_date(
            trade_date,
            pause_seconds=args.pause,
            issuers=ACTIVE_ETF_ISSUERS,
            products=products,
        )
        total += count
        print(f"OK {trade_date.isoformat()} rows={count}", flush=True)
        time.sleep(2)

    print(f"Backfill complete rows={total}", flush=True)


def _find_preflight_date(dates) -> tuple[object, list[PykrxEtfProduct]]:
    errors = []
    for trade_date in reversed(dates):
        try:
            print(f"PYKRX_PREFLIGHT {trade_date.isoformat()}", flush=True)
            products = validate_pykrx_active_access(trade_date, issuers=ACTIVE_ETF_ISSUERS)
            _validate_holdings_preflight(trade_date, products)
            return trade_date, products
        except Exception as exc:
            if _has_auth_required_error(exc):
                raise SystemExit(str(exc)) from exc
            errors.append(f"{trade_date.isoformat()}: {exc}")
            print(f"PYKRX_PREFLIGHT_SKIP {trade_date.isoformat()} {exc}", flush=True)
    raise SystemExit(
        "PyKRX preflight failed before reset for every requested date. "
        "Recent failures: "
        + " | ".join(errors[:5])
    )


def _masked_database_url(value: str) -> str:
    if "@" not in value or "://" not in value:
        return value
    scheme, rest = value.split("://", 1)
    user_part, host_part = rest.rsplit("@", 1)
    user = user_part.split(":", 1)[0]
    return f"{scheme}://{user}:***@{host_part}"


def _has_auth_required_error(exc: BaseException) -> bool:
    current: BaseException | None = exc
    while current is not None:
        if isinstance(current, KrxAuthRequiredError):
            return True
        current = current.__cause__ or current.__context__
    return False


def _validate_holdings_preflight(trade_date, products: list[PykrxEtfProduct]) -> None:
    errors = []
    for product in products[:10]:
        try:
            frame = download_pykrx_active_holdings(product, trade_date)
            if not frame.empty:
                print(
                    f"PYKRX_PDF_PREFLIGHT {trade_date.isoformat()} {product.etf_code} rows={len(frame)}",
                    flush=True,
                )
                return
            errors.append(f"{product.etf_code}: empty")
        except KrxAuthRequiredError:
            raise
        except Exception as exc:
            errors.append(f"{product.etf_code}: {exc}")
    raise RuntimeError(
        "PyKRX PDF preflight failed before reset. "
        "No ETF holdings were downloadable for the first 10 products: "
        + "; ".join(errors)
    )


if __name__ == "__main__":
    main()
