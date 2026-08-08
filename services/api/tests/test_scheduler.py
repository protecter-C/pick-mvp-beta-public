import threading
import pytest
from app.config import Settings, validate_runtime_settings
from app.jobs import RefreshResult
from app.scheduler import run_price_tracking_scheduler


def test_production_startup_rejects_clean_default_secrets():
    with pytest.raises(RuntimeError, match="AUTH_SECRET"):
        validate_runtime_settings(Settings.model_construct(environment="production", database_url="postgresql+psycopg://pick:pick@db:5432/pick", auth_secret="local-development-secret", affiliate_webhook_secret="local-affiliate-secret"))


def test_production_startup_accepts_explicit_database_and_secrets():
    validate_runtime_settings(Settings.model_construct(environment="production", database_url="postgresql+psycopg://pick:pick@db:5432/pick", auth_secret="strong-secret", affiliate_webhook_secret="strong-webhook-secret", admin_api_key="strong-admin-key"))


def test_scheduler_runs_cycle_and_honors_stop_event():
    stop = threading.Event()
    calls = []

    def cycle():
        calls.append(True)
        stop.set()
        return RefreshResult(checked=2)

    run_price_tracking_scheduler(interval_seconds=1, run_once=cycle, stop_event=stop)
    assert len(calls) == 1
