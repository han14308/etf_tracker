from __future__ import annotations

from datetime import date, timedelta
from pathlib import Path
import sys
import time

ROOT_DIR = Path(__file__).resolve().parents[1]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from etf_track.db import upsert_holdings, upsert_products
from etf_track.download import download_kodex_holdings, download_time_holdings
from etf_track.normalize import normalize_holdings
from etf_track.products import EtfProduct, list_all_active_etfs


def collect_active_for_date(
    trade_date: date,
    pause_seconds: float = 0.5,
    products: list[EtfProduct] | None = None,
) -> int:
    if products is None:
        products = list_all_active_etfs()
        upsert_products([product.to_dict() for product in products])
    print(f"ACTIVE_PRODUCTS count={len(products)}", flush=True)

    total_rows = 0
    errors: list[str] = []
    for product in products:
        try:
            print(f"START {trade_date.isoformat()} {product.etf_code} {product.name}", flush=True)
            raw = _download_product(product, trade_date)
            normalized = normalize_holdings(raw, product.etf_code, trade_date)
            count = upsert_holdings(normalized)
            total_rows += count
            print(f"DONE {trade_date.isoformat()} {product.etf_code} rows={count}", flush=True)
        except Exception as exc:
            message = f"SKIP {trade_date.isoformat()} {product.etf_code} {product.name}: {exc}"
            errors.append(message)
            print(message, flush=True)
        time.sleep(pause_seconds)

    if not total_rows and errors:
        raise RuntimeError("; ".join(errors[:5]))
    if errors:
        print(f"PARTIAL {trade_date.isoformat()} errors={len(errors)}", flush=True)
    return total_rows


def _download_product(product: EtfProduct, trade_date: date):
    if product.issuer == "TIME":
        return download_time_holdings(int(product.source_id), trade_date)
    if product.issuer == "KODEX":
        return download_kodex_holdings(product.source_id, trade_date)
    raise ValueError(f"Unknown issuer: {product.issuer}")


def latest_business_day(today: date | None = None) -> date:
    current = today or date.today()
    if current.weekday() == 5:
        return current - timedelta(days=1)
    if current.weekday() == 6:
        return current - timedelta(days=2)
    return current


if __name__ == "__main__":
    target = latest_business_day()
    count = collect_active_for_date(target)
    print(f"Collected {count} active ETF holding rows for {target.isoformat()}")
