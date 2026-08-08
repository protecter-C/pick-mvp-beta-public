from datetime import datetime
from typing import Literal
from pydantic import BaseModel, ConfigDict, EmailStr, Field


class RegisterIn(BaseModel):
    email: EmailStr
    password: str = Field(min_length=8, max_length=128)
    name: str = Field(min_length=1, max_length=120)
    referral_code: str | None = None


class LoginIn(BaseModel):
    email: EmailStr
    password: str


class TokenOut(BaseModel):
    access_token: str
    token_type: str = "bearer"


class ProfileUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=120)
    preferences: dict | None = None


class UserOut(BaseModel):
    id: int
    email: EmailStr
    name: str
    referral_code: str
    preferences: dict
    model_config = ConfigDict(from_attributes=True)


class ProductOut(BaseModel):
    id: int
    external_id: str
    url: str
    name: str
    category: str
    merchant: str
    current_price_cents: int
    typical_price_cents: int
    currency: str
    rating: int
    image_url: str | None
    model_config = ConfigDict(from_attributes=True)


class AnalyzeIn(BaseModel):
    query: str = Field(min_length=2, max_length=2000)
    budget_cents: int = Field(gt=0)
    urgency: int = Field(ge=1, le=10)
    fit: int = Field(ge=1, le=10)


class DecisionOut(BaseModel):
    id: int
    product: ProductOut
    verdict: str
    score: int
    budget_cents: int
    urgency: int
    fit: int
    evidence: list[str]
    explanation: str
    prevented_spend_cents: int
    created_at: datetime
    alternatives: list[ProductOut] = []
    model_config = ConfigDict(from_attributes=True)


class WatchIn(BaseModel):
    product_id: int
    target_price_cents: int = Field(gt=0)


class PurchaseIn(BaseModel):
    product_id: int
    decision_id: int | None = None
    price_paid_cents: int = Field(gt=0)
    purchased_at: datetime | None = None
    return_deadline: datetime | None = None
    warranty_deadline: datetime | None = None


class PurchaseUpdate(BaseModel):
    satisfaction: int | None = Field(default=None, ge=1, le=10)
    returned: bool | None = None


class RedeemIn(BaseModel):
    points: int = Field(ge=100)
    reward: str = Field(min_length=1, max_length=80)


class AffiliateClickIn(BaseModel):
    product_id: int
    provider: str = Field(default="mock", min_length=1, max_length=40)
    destination_url: str = Field(min_length=1, max_length=2000)


class AffiliateClickOut(BaseModel):
    click_token: str
    provider: str
    product_id: int
    outbound_url: str
    expires_at: datetime


class AffiliateConversionIn(BaseModel):
    click_token: str = Field(min_length=16, max_length=96)
    external_conversion_id: str = Field(min_length=1, max_length=160)
    external_order_id: str | None = Field(default=None, max_length=160)
    status: Literal["pending", "verified", "rejected", "refunded"]
    gross_order_value_cents: int = Field(ge=0)
    commission_cents: int = Field(ge=0)
    currency: str = Field(default="USD", min_length=3, max_length=3)
    occurred_at: datetime


class AffiliateConversionOut(BaseModel):
    id: int
    click_id: int
    provider: str
    external_conversion_id: str
    external_order_id: str | None
    status: str
    gross_order_value_cents: int
    commission_cents: int
    reward_points: int
    currency: str
    occurred_at: datetime
    verified_at: datetime | None
    rewarded_at: datetime | None
    reversed_at: datetime | None
    created_at: datetime
    updated_at: datetime
    model_config = ConfigDict(from_attributes=True)
