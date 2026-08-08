from sqlalchemy import select
from sqlalchemy.orm import Session
from app.database import Base, make_engine
from app.jobs import InMemoryCacheProvider, InMemoryLockProvider, PriceTrackingJob
from app.models import Decision, PointsEntry, PricePoint, PriceTrackingEvent, PriceWatch, Product, User


def make_fixture(tmp_path, target=9500, budget=9000):
    engine = make_engine(f"sqlite:///{(tmp_path / 'jobs.db').as_posix()}")
    Base.metadata.create_all(engine)
    db = Session(engine)
    user = User(email="job@example.com", password_hash="hash", name="Job", referral_code="JOB", preferences={})
    product = Product(external_id="job-product", url="https://shop.example/item", name="Job Product", category="other", merchant="Seller", current_price_cents=10000, typical_price_cents=12000, rating=80)
    db.add_all([user, product]); db.flush()
    decision = Decision(user_id=user.id, product_id=product.id, verdict="BUY", score=80, budget_cents=budget, urgency=8, fit=8, evidence=[], explanation="test")
    watch = PriceWatch(user_id=user.id, product_id=product.id, target_price_cents=target)
    db.add_all([decision, watch, PricePoint(product_id=product.id, price_cents=10000)]); db.commit()
    return engine, db, user, product, watch, decision


class FixedProvider:
    def __init__(self, value):
        self.value, self.calls = value, 0

    def current_price(self, external_id, fallback_cents):
        self.calls += 1
        return self.value


def test_job_appends_meaningful_history_and_dedupes_target_event(tmp_path):
    engine, db, user, product, watch, _ = make_fixture(tmp_path)
    provider = FixedProvider(9400)
    job = PriceTrackingJob(db, provider, attempts=1, cache_provider=InMemoryCacheProvider())
    first = job.run(user.id)
    assert (first.checked, first.updated, first.triggered) == (1, 1, 1)
    assert db.scalar(select(PriceTrackingEvent.id)) is not None
    assert db.scalar(select(PricePoint.price_cents).order_by(PricePoint.id.desc())) == 9400
    assert db.scalar(select(PriceWatch.active).where(PriceWatch.id == watch.id)) is False
    watch.active = True
    db.commit()
    second = job.run(user.id)
    assert second.triggered == 0
    db.close(); engine.dispose()


def test_job_ignores_insignificant_price_change(tmp_path):
    engine, db, user, product, watch, decision = make_fixture(tmp_path, target=1, budget=1)
    provider = FixedProvider(9950)
    result = PriceTrackingJob(db, provider, attempts=1).run(user.id)
    assert result.updated == 0
    assert db.scalar(select(PricePoint.price_cents).order_by(PricePoint.id.desc())) == 10000
    db.close(); engine.dispose()


def test_job_detects_buy_threshold_and_retries(tmp_path):
    engine, db, user, product, watch, decision = make_fixture(tmp_path, target=1, budget=9500)

    class Flaky:
        calls = 0
        def current_price(self, external_id, fallback_cents):
            self.calls += 1
            if self.calls < 3:
                raise TimeoutError("temporary")
            return 9400

    provider = Flaky()
    result = PriceTrackingJob(db, provider, attempts=3, backoff_seconds=0).run(user.id)
    event = db.scalar(select(PriceTrackingEvent).where(PriceTrackingEvent.kind == "buy_threshold"))
    assert result.triggered == 1
    assert provider.calls == 3
    assert event.decision_id == decision.id
    assert db.scalar(select(PriceWatch.active).where(PriceWatch.id == watch.id)) is True
    db.close(); engine.dispose()


def test_job_skips_when_product_lock_is_held(tmp_path):
    engine, db, user, product, watch, _ = make_fixture(tmp_path)
    locks = InMemoryLockProvider()
    assert locks.acquire(f"pick:price:{product.external_id}", 0)
    result = PriceTrackingJob(db, FixedProvider(9000), lock_provider=locks, attempts=1).run(user.id)
    assert result.skipped_locked == 1
    locks.release(f"pick:price:{product.external_id}")
    db.close(); engine.dispose()
