"""Deployable polling entrypoint for the price-tracking job."""
from __future__ import annotations

import logging
import signal
import time
from collections.abc import Callable

from .database import SessionLocal
from .jobs import PriceTrackingJob, RefreshResult, make_runtime_adapters
from .providers import price_provider
from .config import get_settings, validate_runtime_settings

logger = logging.getLogger("pick.price_tracking")


def run_price_tracking_once(session_factory: Callable = SessionLocal, provider=price_provider) -> RefreshResult:
    db = session_factory()
    try:
        locks, cache = make_runtime_adapters()
        return PriceTrackingJob(db, provider, lock_provider=locks, cache_provider=cache).run()
    finally:
        db.close()


def run_price_tracking_scheduler(interval_seconds: int | None = None, run_once: Callable = run_price_tracking_once, stop_event=None) -> None:
    settings = get_settings()
    validate_runtime_settings(settings)
    interval = max(1, interval_seconds or settings.price_tracking_interval_seconds)
    while stop_event is None or not stop_event.is_set():
        try:
            result = run_once()
            logger.info("price tracking checked=%s updated=%s triggered=%s errors=%s", result.checked, result.updated, result.triggered, len(result.errors))
        except Exception:
            logger.exception("price tracking cycle failed")
        if stop_event is None:
            time.sleep(interval)
        else:
            stop_event.wait(interval)


def main() -> None:
    logging.basicConfig(level=logging.INFO)
    stop = __import__("threading").Event()
    signal.signal(signal.SIGTERM, lambda *_: stop.set())
    signal.signal(signal.SIGINT, lambda *_: stop.set())
    run_price_tracking_scheduler(stop_event=stop)


if __name__ == "__main__":
    main()
