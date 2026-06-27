from __future__ import annotations

import os
from pathlib import Path
import sys

ROOT_DIR = Path(__file__).resolve().parents[1]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

import uvicorn

from etf_track.active_backfill import start_active_backfill
from etf_track.config import ACTIVE_BACKFILL_ON_START_DAYS


def main() -> None:
    if ACTIVE_BACKFILL_ON_START_DAYS > 0:
        started = start_active_backfill(ACTIVE_BACKFILL_ON_START_DAYS)
        print(
            f"ACTIVE_BACKFILL_ON_START days={ACTIVE_BACKFILL_ON_START_DAYS} started={started}",
            flush=True,
        )

    port = int(os.getenv("PORT", "8000"))
    uvicorn.run("app.main:app", host="0.0.0.0", port=port)


if __name__ == "__main__":
    main()
