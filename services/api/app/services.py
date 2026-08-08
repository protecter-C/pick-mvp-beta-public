import secrets
from datetime import datetime, timezone
from fastapi import HTTPException
from sqlalchemy import func, select
from sqlalchemy.dialects.postgresql import insert as postgres_insert
from sqlalchemy.dialects.sqlite import insert as sqlite_insert
from sqlalchemy.orm import Session
from . import models
from .analytics import record_event
from .providers import ProductData, normalize_seller, normalize_url, product_provider


def get_or_create_product(db: Session, data: ProductData) -> models.Product:
    product = db.scalar(select(models.Product).where(models.Product.external_id == data.external_id))
    if product is None:
        product = models.Product(
            external_id=data.external_id, url=normalize_url(data.url), name=data.name, category=data.category,
            merchant=normalize_seller(data.merchant), current_price_cents=data.current_price_cents,
            typical_price_cents=data.typical_price_cents, currency=data.currency,
            rating=data.rating, image_url=data.image_url,
        )
        db.add(product)
        db.flush()
    else:
        product.url = normalize_url(data.url)
        product.name = data.name
        product.category = data.category
        product.merchant = normalize_seller(data.merchant)
        product.current_price_cents = data.current_price_cents
        product.typical_price_cents = data.typical_price_cents
        product.currency = data.currency
        product.rating = data.rating
        product.image_url = data.image_url
    db.add(models.PricePoint(product_id=product.id, price_cents=data.current_price_cents, captured_at=data.observed_at))
    return product


def unique_referral_code(db: Session) -> str:
    while True:
        code = secrets.token_hex(4).upper()
        if db.scalar(select(models.User.id).where(models.User.referral_code == code)) is None:
            return code


def add_points(db: Session, user_id: int, amount: int, reason: str, reference_type: str, reference_id: int | None = None, idempotency_key: str | None = None):
    if idempotency_key:
        existing = db.scalar(select(models.PointsEntry).where(models.PointsEntry.idempotency_key == idempotency_key))
        if existing is not None:
            return existing
    values = {"user_id": user_id, "amount": amount, "reason": reason, "reference_type": reference_type, "reference_id": reference_id, "idempotency_key": idempotency_key}
    dialect = db.bind.dialect.name if db.bind is not None else ""
    if idempotency_key and dialect == "postgresql":
        result = db.execute(postgres_insert(models.PointsEntry).values(**values).on_conflict_do_nothing(index_elements=["idempotency_key"]))
        if result.rowcount == 0:
            return db.scalar(select(models.PointsEntry).where(models.PointsEntry.idempotency_key == idempotency_key))
        entry = db.scalar(select(models.PointsEntry).where(models.PointsEntry.idempotency_key == idempotency_key))
        record_event(db, "reward", event_id=f"points:{idempotency_key}", user_id=user_id, points=amount, properties={"reason": reason, "reference_type": reference_type})
        return entry
    if idempotency_key and dialect == "sqlite":
        result = db.execute(sqlite_insert(models.PointsEntry).values(**values).on_conflict_do_nothing(index_elements=["idempotency_key"]))
        if result.rowcount == 0:
            return db.scalar(select(models.PointsEntry).where(models.PointsEntry.idempotency_key == idempotency_key))
        entry = db.scalar(select(models.PointsEntry).where(models.PointsEntry.idempotency_key == idempotency_key))
        record_event(db, "reward", event_id=f"points:{idempotency_key}", user_id=user_id, points=amount, properties={"reason": reason, "reference_type": reference_type})
        return entry
    entry = models.PointsEntry(**values)
    db.add(entry)
    db.flush()
    record_event(db, "reward", event_id=f"points:{entry.id}", user_id=user_id, points=amount, properties={"reason": reason, "reference_type": reference_type})
    return entry


def points_balance(db: Session, user_id: int) -> int:
    return int(db.scalar(select(func.coalesce(func.sum(models.PointsEntry.amount), 0)).where(models.PointsEntry.user_id == user_id)) or 0)


def notify(db: Session, user_id: int, kind: str, title: str, body: str):
    notification = models.Notification(user_id=user_id, kind=kind, title=title, body=body)
    db.add(notification)
    return notification


def owned(db: Session, model, item_id: int, user_id: int):
    item = db.get(model, item_id)
    if item is None or item.user_id != user_id:
        raise HTTPException(status_code=404, detail="Not found")
    return item


def serialize_product_data(db: Session, data: ProductData) -> models.Product:
    return get_or_create_product(db, data)
