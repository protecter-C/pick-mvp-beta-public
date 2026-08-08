from dataclasses import dataclass, field
from datetime import datetime, timezone
import json
import threading
import time
from typing import Protocol
from uuid import uuid4

from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert as postgres_insert
from sqlalchemy.dialects.sqlite import insert as sqlite_insert
from sqlalchemy.orm import Session

from . import models, services
from .config import get_settings
from .providers import PriceProvider, ProviderError


class LockProvider(Protocol):
    def acquire(self, key: str, timeout_seconds: float) -> bool: ...
    def release(self, key: str) -> None: ...


class CacheProvider(Protocol):
    def get(self, key: str): ...
    def set(self, key: str, value, ttl_seconds: int) -> None: ...


class InMemoryLockProvider:
    def __init__(self):
        self._locks: dict[str, threading.Lock] = {}
        self._guard = threading.Lock()

    def acquire(self, key: str, timeout_seconds: float = 0) -> bool:
        with self._guard:
            lock = self._locks.setdefault(key, threading.Lock())
        return lock.acquire(timeout=max(0, timeout_seconds))

    def release(self, key: str) -> None:
        with self._guard:
            lock = self._locks.get(key)
        if lock and lock.locked():
            lock.release()


class InMemoryCacheProvider:
    def __init__(self):
        self._values: dict[str, tuple[float, object]] = {}
        self._lock = threading.Lock()

    def get(self, key: str):
        with self._lock:
            item = self._values.get(key)
            if item is None:
                return None
            expires, value = item
            if expires <= time.monotonic():
                self._values.pop(key, None)
                return None
            return value

    def set(self, key: str, value, ttl_seconds: int) -> None:
        with self._lock:
            self._values[key] = (time.monotonic() + max(1, ttl_seconds), value)


class RedisLockProvider:
    """Redis SET NX lock; import redis only when this adapter is selected."""

    def __init__(self, client):
        self.client = client
        self._tokens: dict[str, str] = {}

    def acquire(self, key: str, timeout_seconds: float = 30) -> bool:
        token = uuid4().hex
        acquired = bool(self.client.set(key, token, nx=True, ex=max(1, round(timeout_seconds))))
        if acquired:
            self._tokens[key] = token
        return acquired

    def release(self, key: str) -> None:
        token = self._tokens.pop(key, None)
        if token:
            self.client.eval("if redis.call('get', KEYS[1]) == ARGV[1] then return redis.call('del', KEYS[1]) else return 0 end", 1, key, token)


class RedisCacheProvider:
    def __init__(self, client):
        self.client = client

    def get(self, key: str):
        value = self.client.get(key)
        return json.loads(value) if value else None

    def set(self, key: str, value, ttl_seconds: int) -> None:
        self.client.setex(key, max(1, ttl_seconds), json.dumps(value))


def make_runtime_adapters(redis_url: str | None = None) -> tuple[LockProvider, CacheProvider]:
    """Select Redis when available; never make Redis a requirement for local/test runs."""
    try:
        import redis

        client = redis.Redis.from_url(redis_url or get_settings().redis_url, decode_responses=True)
        client.ping()
        return RedisLockProvider(client), RedisCacheProvider(client)
    except Exception:
        return InMemoryLockProvider(), InMemoryCacheProvider()


def meaningful_price_observation(previous_cents: int | None, current_cents: int, relative_threshold: float = 0.01) -> bool:
    if previous_cents is None:
        return True
    return abs(current_cents - previous_cents) >= max(1, round(abs(previous_cents) * relative_threshold))


@dataclass
class RefreshResult:
    checked: int = 0
    updated: int = 0
    triggered: int = 0
    skipped_locked: int = 0
    errors: list[str] = field(default_factory=list)


class PriceTrackingJob:
    def __init__(self, db: Session, price_provider: PriceProvider, lock_provider: LockProvider | None = None, cache_provider: CacheProvider | None = None, attempts: int = 3, backoff_seconds: float = 0.1, cache_ttl_seconds: int = 30):
        self.db = db
        self.price_provider = price_provider
        self.locks = lock_provider or InMemoryLockProvider()
        self.cache = cache_provider or InMemoryCacheProvider()
        self.attempts = max(1, attempts)
        self.backoff_seconds = max(0, backoff_seconds)
        self.cache_ttl_seconds = max(1, cache_ttl_seconds)

    def _price_with_retry(self, external_id: str, fallback_cents: int) -> int:
        last_error: Exception | None = None
        for attempt in range(self.attempts):
            try:
                return self.price_provider.current_price(external_id, fallback_cents)
            except Exception as error:
                last_error = error
                if attempt + 1 < self.attempts:
                    time.sleep(self.backoff_seconds * (2**attempt))
        raise ProviderError(f"price refresh failed for {external_id}: {last_error}") from last_error

    def _event_exists(self, dedupe_key: str) -> bool:
        return self.db.scalar(select(models.PriceTrackingEvent.id).where(models.PriceTrackingEvent.dedupe_key == dedupe_key)) is not None

    def _create_event(self, watch: models.PriceWatch, product: models.Product, kind: str, threshold_cents: int, observed_cents: int, decision_id: int | None = None) -> bool:
        dedupe_key = f"{kind}:{watch.id}:{decision_id or 0}:{threshold_cents}"
        values = {"user_id": watch.user_id, "product_id": product.id, "watch_id": watch.id, "decision_id": decision_id, "kind": kind, "threshold_cents": threshold_cents, "observed_price_cents": observed_cents, "dedupe_key": dedupe_key}
        dialect = self.db.bind.dialect.name if self.db.bind is not None else ""
        if dialect == "postgresql":
            inserted = self.db.execute(postgres_insert(models.PriceTrackingEvent).values(**values).on_conflict_do_nothing(index_elements=["dedupe_key"]))
            if inserted.rowcount != 1:
                return False
        elif dialect == "sqlite":
            inserted = self.db.execute(sqlite_insert(models.PriceTrackingEvent).values(**values).on_conflict_do_nothing(index_elements=["dedupe_key"]))
            if inserted.rowcount != 1:
                return False
        else:
            if self._event_exists(dedupe_key):
                return False
            self.db.add(models.PriceTrackingEvent(**values))
        title = "Target price reached" if kind == "target_price" else "BUY price signal"
        services.notify(self.db, watch.user_id, "price_alert", title, f"{product.name} is now {observed_cents / 100:.2f} {product.currency}.")
        return True

    def _refresh_watch(self, watch: models.PriceWatch, result: RefreshResult) -> None:
        product = self.db.get(models.Product, watch.product_id)
        if product is None:
            return
        lock_key = f"pick:price:{product.external_id}"
        if not self.locks.acquire(lock_key, 1):
            result.skipped_locked += 1
            return
        try:
            result.checked += 1
            cache_key = f"pick:price:{product.external_id}"
            current = self.cache.get(cache_key)
            if current is None:
                current = self._price_with_retry(product.external_id, product.current_price_cents)
                self.cache.set(cache_key, current, self.cache_ttl_seconds)
            current = int(current)
            previous_point = self.db.scalar(select(models.PricePoint).where(models.PricePoint.product_id == product.id).order_by(models.PricePoint.captured_at.desc(), models.PricePoint.id.desc()).limit(1))
            previous = previous_point.price_cents if previous_point else product.current_price_cents
            product.current_price_cents = current
            if meaningful_price_observation(previous, current):
                self.db.add(models.PricePoint(product_id=product.id, price_cents=current, captured_at=datetime.now(timezone.utc)))
                result.updated += 1
            if current <= watch.target_price_cents and not self._event_exists(f"target_price:{watch.id}:0:{watch.target_price_cents}"):
                if self._create_event(watch, product, "target_price", watch.target_price_cents, current):
                    result.triggered += 1
                watch.active = False
            decisions = self.db.scalars(select(models.Decision).where(models.Decision.user_id == watch.user_id, models.Decision.product_id == product.id, models.Decision.verdict == models.Verdict.BUY.value)).all()
            for decision in decisions:
                crossed = current <= decision.budget_cents and (previous is None or previous > decision.budget_cents)
                if crossed and self._create_event(watch, product, "buy_threshold", decision.budget_cents, current, decision.id):
                    result.triggered += 1
            self.db.commit()
        finally:
            self.locks.release(lock_key)

    def run(self, user_id: int | None = None) -> RefreshResult:
        result = RefreshResult()
        query = select(models.PriceWatch).where(models.PriceWatch.active.is_(True))
        if user_id is not None:
            query = query.where(models.PriceWatch.user_id == user_id)
        watches = self.db.scalars(query.order_by(models.PriceWatch.id)).all()
        for watch in watches:
            try:
                self._refresh_watch(watch, result)
            except Exception as error:
                self.db.rollback()
                result.errors.append(str(error))
        return result
