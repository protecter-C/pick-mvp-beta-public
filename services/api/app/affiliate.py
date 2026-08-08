from datetime import datetime, timedelta, timezone
import hashlib
import hmac
import secrets
from urllib.parse import parse_qsl, urlencode, urlparse, urlunparse

from fastapi import HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

from . import models, schemas, services
from .config import get_settings
from .providers import affiliate_provider, normalize_url


def utc(value: datetime) -> datetime:
    return value.astimezone(timezone.utc) if value.tzinfo else value.replace(tzinfo=timezone.utc)


def expired(value: datetime) -> bool:
    return utc(value) < datetime.now(timezone.utc)


def attach_click_token(destination_url: str, token: str) -> str:
    parsed = urlparse(normalize_url(destination_url))
    query = parse_qsl(parsed.query, keep_blank_values=True)
    query.append(("pick_click_token", token))
    return urlunparse((parsed.scheme, parsed.netloc, parsed.path, parsed.params, urlencode(query), parsed.fragment))


def create_click(db: Session, user_id: int, data: schemas.AffiliateClickIn) -> models.AffiliateClick:
    product = db.get(models.Product, data.product_id)
    if product is None:
        raise HTTPException(status_code=404, detail="Product not found")
    provider = data.provider.strip().lower()
    token = secrets.token_urlsafe(32)
    now = datetime.now(timezone.utc)
    click = models.AffiliateClick(user_id=user_id, product_id=product.id, provider=provider, click_token=token, destination_url=attach_click_token(affiliate_provider.outbound_url(data.destination_url), token), created_at=now, expires_at=now + timedelta(days=get_settings().affiliate_click_ttl_days))
    db.add(click)
    db.commit()
    return click


def verify_webhook_signature(body: bytes, signature: str | None) -> bool:
    if not signature:
        return False
    supplied = signature.removeprefix("sha256=").strip()
    expected = hmac.new(get_settings().affiliate_webhook_secret.encode(), body, hashlib.sha256).hexdigest()
    return hmac.compare_digest(expected, supplied)


def _reward_points(commission_cents: int) -> int:
    settings = get_settings()
    return min(settings.affiliate_max_reward_points, max(0, commission_cents * settings.affiliate_reward_bps // 10000))


def process_conversion(db: Session, data: schemas.AffiliateConversionIn, provider: str | None = None, user_id: int | None = None) -> models.AffiliateConversion:
    click = db.scalar(select(models.AffiliateClick).where(models.AffiliateClick.click_token == data.click_token))
    if click is None:
        raise HTTPException(status_code=400, detail="Unknown or expired affiliate click")
    if user_id is not None and click.user_id != user_id:
        raise HTTPException(status_code=403, detail="Affiliate click does not belong to this user")
    provider_name = (provider or click.provider).strip().lower()
    existing = db.scalar(select(models.AffiliateConversion).where(models.AffiliateConversion.provider == provider_name, models.AffiliateConversion.external_conversion_id == data.external_conversion_id))
    if expired(click.expires_at) and existing is None:
        raise HTTPException(status_code=400, detail="Unknown or expired affiliate click")
    if existing is not None:
        if existing.click_id != click.id:
            raise HTTPException(status_code=409, detail="Conversion already attributed")
        incoming_status = data.status
        if existing.status == "refunded" or (existing.status == "verified" and incoming_status == "pending"):
            incoming_status = existing.status
        existing.external_order_id = data.external_order_id or existing.external_order_id
        existing.gross_order_value_cents = data.gross_order_value_cents
        existing.commission_cents = data.commission_cents
        existing.currency = data.currency.upper()
        existing.occurred_at = utc(data.occurred_at)
        existing.status = incoming_status
        conversion = existing
    else:
        conversion = models.AffiliateConversion(click_id=click.id, user_id=click.user_id, product_id=click.product_id, provider=provider_name, external_conversion_id=data.external_conversion_id, external_order_id=data.external_order_id, status=data.status, gross_order_value_cents=data.gross_order_value_cents, commission_cents=data.commission_cents, currency=data.currency.upper(), occurred_at=utc(data.occurred_at))
        db.add(conversion)
        db.flush()

    if conversion.status == "verified" and conversion.verified_at is None:
        conversion.verified_at = datetime.now(timezone.utc)
        conversion.reward_points = _reward_points(conversion.commission_cents)
        if conversion.reward_points and conversion.rewarded_at is None:
            services.add_points(db, conversion.user_id, conversion.reward_points, "Verified affiliate purchase reward", "affiliate_conversion", conversion.id, f"affiliate:{provider_name}:{conversion.external_conversion_id}:reward")
            conversion.rewarded_at = datetime.now(timezone.utc)
    if conversion.status == "refunded" and conversion.rewarded_at is not None and conversion.reversed_at is None:
        if conversion.reward_points:
            services.add_points(db, conversion.user_id, -conversion.reward_points, "Reversed affiliate purchase reward", "affiliate_conversion", conversion.id, f"affiliate:{provider_name}:{conversion.external_conversion_id}:reversal")
        conversion.reversed_at = datetime.now(timezone.utc)
    db.commit()
    return conversion
