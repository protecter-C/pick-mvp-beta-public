from datetime import datetime, timezone
from enum import Enum
from sqlalchemy import Boolean, DateTime, ForeignKey, Integer, JSON, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship
from .database import Base


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


class Verdict(str, Enum):
    BUY = "BUY"
    WAIT = "WAIT"
    PASS = "PASS"


class User(Base):
    __tablename__ = "users"
    id: Mapped[int] = mapped_column(primary_key=True)
    email: Mapped[str] = mapped_column(String(320), unique=True, index=True)
    password_hash: Mapped[str] = mapped_column(String(256))
    name: Mapped[str] = mapped_column(String(120))
    referral_code: Mapped[str] = mapped_column(String(20), unique=True, index=True)
    preferences: Mapped[dict] = mapped_column(JSON, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class Product(Base):
    __tablename__ = "products"
    id: Mapped[int] = mapped_column(primary_key=True)
    external_id: Mapped[str] = mapped_column(String(100), unique=True, index=True)
    url: Mapped[str] = mapped_column(Text)
    name: Mapped[str] = mapped_column(String(240))
    category: Mapped[str] = mapped_column(String(80), index=True)
    merchant: Mapped[str] = mapped_column(String(120))
    image_url: Mapped[str | None] = mapped_column(Text, nullable=True)
    current_price_cents: Mapped[int] = mapped_column(Integer)
    typical_price_cents: Mapped[int] = mapped_column(Integer)
    currency: Mapped[str] = mapped_column(String(3), default="USD")
    rating: Mapped[int] = mapped_column(Integer, default=80)


class Decision(Base):
    __tablename__ = "decisions"
    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), index=True)
    product_id: Mapped[int] = mapped_column(ForeignKey("products.id"), index=True)
    verdict: Mapped[str] = mapped_column(String(4), index=True)
    score: Mapped[int] = mapped_column(Integer)
    budget_cents: Mapped[int] = mapped_column(Integer)
    urgency: Mapped[int] = mapped_column(Integer)
    fit: Mapped[int] = mapped_column(Integer)
    evidence: Mapped[list] = mapped_column(JSON)
    explanation: Mapped[str] = mapped_column(Text)
    prevented_spend_cents: Mapped[int] = mapped_column(Integer, default=0)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    product: Mapped[Product] = relationship()


class PricePoint(Base):
    __tablename__ = "price_points"
    id: Mapped[int] = mapped_column(primary_key=True)
    product_id: Mapped[int] = mapped_column(ForeignKey("products.id"), index=True)
    price_cents: Mapped[int] = mapped_column(Integer)
    captured_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class PriceWatch(Base):
    __tablename__ = "price_watches"
    __table_args__ = (UniqueConstraint("user_id", "product_id"),)
    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), index=True)
    product_id: Mapped[int] = mapped_column(ForeignKey("products.id"), index=True)
    target_price_cents: Mapped[int] = mapped_column(Integer)
    active: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class PriceTrackingEvent(Base):
    __tablename__ = "price_tracking_events"
    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), index=True)
    product_id: Mapped[int] = mapped_column(ForeignKey("products.id"), index=True)
    watch_id: Mapped[int] = mapped_column(ForeignKey("price_watches.id"), index=True)
    decision_id: Mapped[int | None] = mapped_column(ForeignKey("decisions.id"), nullable=True)
    kind: Mapped[str] = mapped_column(String(40), index=True)
    threshold_cents: Mapped[int] = mapped_column(Integer)
    observed_price_cents: Mapped[int] = mapped_column(Integer)
    dedupe_key: Mapped[str] = mapped_column(String(240), unique=True, index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class Purchase(Base):
    __tablename__ = "purchases"
    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), index=True)
    product_id: Mapped[int] = mapped_column(ForeignKey("products.id"), index=True)
    decision_id: Mapped[int | None] = mapped_column(ForeignKey("decisions.id"), nullable=True)
    price_paid_cents: Mapped[int] = mapped_column(Integer)
    purchased_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    return_deadline: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    warranty_deadline: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    satisfaction: Mapped[int | None] = mapped_column(Integer, nullable=True)
    returned: Mapped[bool] = mapped_column(Boolean, default=False)
    product: Mapped[Product] = relationship()


class PointsEntry(Base):
    __tablename__ = "points_entries"
    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), index=True)
    amount: Mapped[int] = mapped_column(Integer)
    reason: Mapped[str] = mapped_column(String(80))
    reference_type: Mapped[str] = mapped_column(String(40))
    reference_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    idempotency_key: Mapped[str | None] = mapped_column(String(240), unique=True, nullable=True, index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class AffiliateClick(Base):
    __tablename__ = "affiliate_clicks"
    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), index=True)
    product_id: Mapped[int] = mapped_column(ForeignKey("products.id"), index=True)
    provider: Mapped[str] = mapped_column(String(40), index=True)
    click_token: Mapped[str] = mapped_column(String(96), unique=True, index=True)
    destination_url: Mapped[str] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))


class AffiliateConversion(Base):
    __tablename__ = "affiliate_conversions"
    __table_args__ = (UniqueConstraint("provider", "external_conversion_id"),)
    id: Mapped[int] = mapped_column(primary_key=True)
    click_id: Mapped[int] = mapped_column(ForeignKey("affiliate_clicks.id"), index=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), index=True)
    product_id: Mapped[int] = mapped_column(ForeignKey("products.id"), index=True)
    provider: Mapped[str] = mapped_column(String(40), index=True)
    external_conversion_id: Mapped[str] = mapped_column(String(160), index=True)
    external_order_id: Mapped[str | None] = mapped_column(String(160), nullable=True)
    status: Mapped[str] = mapped_column(String(20), index=True)
    gross_order_value_cents: Mapped[int] = mapped_column(Integer)
    commission_cents: Mapped[int] = mapped_column(Integer)
    reward_points: Mapped[int] = mapped_column(Integer, default=0)
    currency: Mapped[str] = mapped_column(String(3), default="USD")
    occurred_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    verified_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    rewarded_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    reversed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, onupdate=utcnow)


class AnalyticsEvent(Base):
    __tablename__ = "analytics_events"
    id: Mapped[int] = mapped_column(primary_key=True)
    event_id: Mapped[str] = mapped_column(String(160), unique=True, index=True)
    event_name: Mapped[str] = mapped_column(String(40), index=True)
    user_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"), nullable=True, index=True)
    product_id: Mapped[int | None] = mapped_column(ForeignKey("products.id"), nullable=True, index=True)
    decision_id: Mapped[int | None] = mapped_column(ForeignKey("decisions.id"), nullable=True)
    purchase_id: Mapped[int | None] = mapped_column(ForeignKey("purchases.id"), nullable=True)
    conversion_id: Mapped[int | None] = mapped_column(ForeignKey("affiliate_conversions.id"), nullable=True)
    value_cents: Mapped[int | None] = mapped_column(Integer, nullable=True)
    points: Mapped[int | None] = mapped_column(Integer, nullable=True)
    properties: Mapped[dict] = mapped_column(JSON, default=dict)
    occurred_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class BetaInvite(Base):
    __tablename__ = "beta_invites"
    id: Mapped[int] = mapped_column(primary_key=True)
    email: Mapped[str] = mapped_column(String(320), unique=True, index=True)
    invited_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    accepted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class BetaFeedback(Base):
    __tablename__ = "beta_feedback"
    __table_args__ = (UniqueConstraint("user_id", "decision_id"),)
    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), index=True)
    decision_id: Mapped[int] = mapped_column(ForeignKey("decisions.id"), index=True)
    category: Mapped[str] = mapped_column(String(40), index=True)
    rating: Mapped[int | None] = mapped_column(Integer, nullable=True)
    message: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, onupdate=utcnow)


class Referral(Base):
    __tablename__ = "referrals"
    id: Mapped[int] = mapped_column(primary_key=True)
    referrer_id: Mapped[int] = mapped_column(ForeignKey("users.id"), index=True)
    referred_user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), unique=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class Notification(Base):
    __tablename__ = "notifications"
    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), index=True)
    kind: Mapped[str] = mapped_column(String(40), index=True)
    title: Mapped[str] = mapped_column(String(160))
    body: Mapped[str] = mapped_column(Text)
    read: Mapped[bool] = mapped_column(Boolean, default=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
