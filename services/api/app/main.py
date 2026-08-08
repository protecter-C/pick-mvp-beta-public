from contextlib import asynccontextmanager
from datetime import datetime, timezone
import json
import logging
from fastapi import Depends, FastAPI, HTTPException, Query, Request, Header
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy import func, select
from sqlalchemy.orm import Session
from . import affiliate, analytics, models, schemas, services
from .config import get_settings, validate_runtime_settings
from .database import Base, SessionLocal, engine, get_db
from .jobs import PriceTrackingJob
from .providers import price_provider, product_provider
from .scoring import ScoreInput, choice_score, score_decision
from .security import create_token, current_user, hash_password, verify_password

logger = logging.getLogger("pick.api")


@asynccontextmanager
async def lifespan(_: FastAPI):
    settings = get_settings()
    validate_runtime_settings(settings)
    if settings.auto_create_schema:
        Base.metadata.create_all(bind=engine)
    yield


app = FastAPI(title="PICK API", version="0.1.0", lifespan=lifespan)
app.add_middleware(CORSMiddleware, allow_origins=["http://localhost:3000"], allow_credentials=True, allow_methods=["*"], allow_headers=["*"])

def require_admin(x_admin_key: str | None = Header(default=None, alias="X-Admin-Key")):
    import secrets
    if not x_admin_key or not secrets.compare_digest(x_admin_key, get_settings().admin_api_key):
        raise HTTPException(status_code=403, detail="Admin access required")

@app.middleware("http")
async def analytics_errors(request: Request, call_next):
    route_path = getattr(request.scope.get("route"), "path", request.url.path)
    try:
        response = await call_next(request)
    except Exception:
        response = None
        logger.exception("api_request_error", extra={"event": "api_request_error", "method": request.method, "path": route_path, "status_code": 500})
        try:
            db = SessionLocal()
            analytics.record_event(db, "error", properties={"status_code": 500, "method": request.method, "path": route_path})
            db.commit(); db.close()
        except Exception:
            pass
        raise
    if response.status_code >= 400:
        logger.warning("api_request_failed", extra={"event": "api_request_failed", "method": request.method, "path": route_path, "status_code": response.status_code})
        try:
            db = SessionLocal()
            analytics.record_event(db, "error", properties={"status_code": response.status_code, "method": request.method, "path": route_path})
            db.commit(); db.close()
        except Exception:
            pass
    return response


@app.get("/health")
def health():
    return {"status": "ok"}

@app.get("/ready")
def readiness(db: Session = Depends(get_db)):
    try:
        db.execute(select(1))
    except Exception as error:
        logger.error("readiness_failed", extra={"event": "readiness_failed", "status_code": 503, "error_type": type(error).__name__})
        raise HTTPException(status_code=503, detail="database unavailable") from error
    return {"status": "ready", "database": "ok"}


@app.post("/auth/register", response_model=schemas.TokenOut, status_code=201)
def register(data: schemas.RegisterIn, db: Session = Depends(get_db)):
    email = data.email.lower()
    if db.scalar(select(models.User.id).where(models.User.email == email)):
        raise HTTPException(status_code=409, detail="Email already registered")
    user = models.User(email=email, password_hash=hash_password(data.password), name=data.name, referral_code=services.unique_referral_code(db), preferences={})
    db.add(user)
    db.flush()
    services.add_points(db, user.id, 20, "Welcome to PICK", "signup", user.id)
    if data.referral_code:
        referrer = db.scalar(select(models.User).where(models.User.referral_code == data.referral_code.upper()))
        if referrer:
            db.add(models.Referral(referrer_id=referrer.id, referred_user_id=user.id))
            services.add_points(db, referrer.id, 50, "Successful referral", "referral", user.id)
            services.add_points(db, user.id, 25, "Referral welcome bonus", "referral", referrer.id)
    db.commit()
    return schemas.TokenOut(access_token=create_token(user.id))


@app.post("/auth/login", response_model=schemas.TokenOut)
def login(data: schemas.LoginIn, db: Session = Depends(get_db)):
    user = db.scalar(select(models.User).where(models.User.email == data.email.lower()))
    if user is None or not verify_password(data.password, user.password_hash):
        raise HTTPException(status_code=401, detail="Invalid email or password")
    return schemas.TokenOut(access_token=create_token(user.id))


@app.get("/profile", response_model=schemas.UserOut)
def profile(user: models.User = Depends(current_user)):
    return user


@app.post("/affiliate/click", response_model=schemas.AffiliateClickOut, status_code=201)
def create_affiliate_click(data: schemas.AffiliateClickIn, db: Session = Depends(get_db), user: models.User = Depends(current_user)):
    click = affiliate.create_click(db, user.id, data)
    analytics.record_event(db, "merchant_click", user_id=user.id, product_id=click.product_id, properties={"provider": click.provider})
    db.commit()
    return schemas.AffiliateClickOut(click_token=click.click_token, provider=click.provider, product_id=click.product_id, outbound_url=click.destination_url, expires_at=click.expires_at)


@app.get("/affiliate/click/{click_token}", response_model=schemas.AffiliateClickOut)
def resolve_affiliate_click(click_token: str, db: Session = Depends(get_db)):
    click = db.scalar(select(models.AffiliateClick).where(models.AffiliateClick.click_token == click_token))
    if click is None or affiliate.expired(click.expires_at):
        raise HTTPException(status_code=404, detail="Affiliate click not found")
    return schemas.AffiliateClickOut(click_token=click.click_token, provider=click.provider, product_id=click.product_id, outbound_url=click.destination_url, expires_at=click.expires_at)


def conversion_out(conversion: models.AffiliateConversion) -> schemas.AffiliateConversionOut:
    return schemas.AffiliateConversionOut.model_validate(conversion)


@app.post("/affiliate/conversions/import", response_model=schemas.AffiliateConversionOut, status_code=201)
def import_affiliate_conversion(data: schemas.AffiliateConversionIn, db: Session = Depends(get_db), user: models.User = Depends(current_user)):
    conversion = affiliate.process_conversion(db, data, user_id=user.id)
    analytics.record_event(db, "conversion", event_id=f"conversion:{conversion.provider}:{conversion.external_conversion_id}:{conversion.status}", user_id=conversion.user_id, product_id=conversion.product_id, conversion_id=conversion.id, value_cents=conversion.gross_order_value_cents, properties={"provider": conversion.provider, "status": conversion.status})
    db.commit()
    return conversion_out(conversion)


@app.post("/affiliate/webhook/{provider}", response_model=schemas.AffiliateConversionOut)
async def affiliate_webhook(provider: str, request: Request, db: Session = Depends(get_db)):
    body = await request.body()
    if not affiliate.verify_webhook_signature(body, request.headers.get("X-Affiliate-Signature")):
        raise HTTPException(status_code=401, detail="Invalid affiliate webhook signature")
    try:
        data = schemas.AffiliateConversionIn.model_validate(json.loads(body))
    except (ValueError, TypeError, json.JSONDecodeError) as error:
        raise HTTPException(status_code=400, detail="Invalid affiliate webhook payload") from error
    conversion = affiliate.process_conversion(db, data, provider=provider)
    analytics.record_event(db, "conversion", event_id=f"conversion:{conversion.provider}:{conversion.external_conversion_id}:{conversion.status}", user_id=conversion.user_id, product_id=conversion.product_id, conversion_id=conversion.id, value_cents=conversion.gross_order_value_cents, properties={"provider": conversion.provider, "status": conversion.status})
    db.commit()
    return conversion_out(conversion)


@app.get("/affiliate/conversions", response_model=list[schemas.AffiliateConversionOut])
def affiliate_conversions(db: Session = Depends(get_db), user: models.User = Depends(current_user)):
    items = db.scalars(select(models.AffiliateConversion).where(models.AffiliateConversion.user_id == user.id).order_by(models.AffiliateConversion.created_at.desc())).all()
    return [conversion_out(item) for item in items]


@app.patch("/profile", response_model=schemas.UserOut)
def update_profile(data: schemas.ProfileUpdate, user: models.User = Depends(current_user), db: Session = Depends(get_db)):
    if data.name is not None:
        user.name = data.name
    if data.preferences is not None:
        user.preferences = data.preferences
    db.commit()
    return user


def product_out(product: models.Product) -> schemas.ProductOut:
    return schemas.ProductOut.model_validate(product)


def decision_out(db: Session, decision: models.Decision, include_alternatives: bool = False) -> schemas.DecisionOut:
    alternatives = []
    if include_alternatives:
        data = product_provider.resolve(decision.product.external_id)
        alternatives = [product_out(services.serialize_product_data(db, item)) for item in product_provider.alternatives(data)]
    result = schemas.DecisionOut.model_validate(decision)
    result.alternatives = alternatives
    return result


@app.get("/products/search", response_model=list[schemas.ProductOut])
def search_products(q: str = Query(min_length=2), db: Session = Depends(get_db), user: models.User = Depends(current_user)):
    primary = product_provider.resolve(q)
    products = [primary, *product_provider.alternatives(primary)]
    result = [product_out(services.get_or_create_product(db, item)) for item in products]
    db.commit()
    return result


@app.post("/decisions/analyze", response_model=schemas.DecisionOut, status_code=201)
def analyze(data: schemas.AnalyzeIn, db: Session = Depends(get_db), user: models.User = Depends(current_user)):
    product = services.get_or_create_product(db, product_provider.resolve(data.query))
    analytics.record_event(db, "product_check", user_id=user.id, product_id=product.id, properties={"source": "analyze"})
    scored = score_decision(ScoreInput(product.current_price_cents, product.typical_price_cents, data.budget_cents, data.fit, data.urgency, product.rating))
    prevented = product.current_price_cents if scored.verdict == models.Verdict.PASS else 0
    explanation = f"{scored.verdict.value}: deterministic score {scored.score}/100 based on value, budget, fit, timing, and quality."
    decision = models.Decision(user_id=user.id, product_id=product.id, verdict=scored.verdict.value, score=scored.score, budget_cents=data.budget_cents, urgency=data.urgency, fit=data.fit, evidence=scored.evidence, explanation=explanation, prevented_spend_cents=prevented)
    db.add(decision)
    db.flush()
    analytics.record_event(db, "verdict", user_id=user.id, product_id=product.id, decision_id=decision.id, properties={"verdict": scored.verdict.value, "score": scored.score})
    analytics.record_event(db, {models.Verdict.BUY: "buy_action", models.Verdict.WAIT: "wait_action", models.Verdict.PASS: "pass_action"}[scored.verdict], user_id=user.id, product_id=product.id, decision_id=decision.id)
    reward = {models.Verdict.PASS: 10, models.Verdict.WAIT: 7, models.Verdict.BUY: 2}[scored.verdict]
    services.add_points(db, user.id, reward, f"Thoughtful {scored.verdict.value} decision", "decision", decision.id)
    db.commit()
    return decision_out(db, decision, True)

@app.get("/decisions/{decision_id}", response_model=schemas.DecisionOut)
def decision_detail(decision_id: int, db: Session = Depends(get_db), user: models.User = Depends(current_user)):
    decision = services.owned(db, models.Decision, decision_id, user.id)
    analytics.record_event(db, "evidence_view", user_id=user.id, product_id=decision.product_id, decision_id=decision.id)
    db.commit()
    return decision_out(db, decision, True)


@app.get("/decisions", response_model=list[schemas.DecisionOut])
def decisions(db: Session = Depends(get_db), user: models.User = Depends(current_user)):
    items = db.scalars(select(models.Decision).where(models.Decision.user_id == user.id).order_by(models.Decision.created_at.desc())).all()
    return [decision_out(db, item) for item in items]


@app.post("/price-watches", status_code=201)
def create_watch(data: schemas.WatchIn, db: Session = Depends(get_db), user: models.User = Depends(current_user)):
    if db.get(models.Product, data.product_id) is None:
        raise HTTPException(status_code=404, detail="Product not found")
    watch = db.scalar(select(models.PriceWatch).where(models.PriceWatch.user_id == user.id, models.PriceWatch.product_id == data.product_id))
    if watch:
        watch.target_price_cents, watch.active = data.target_price_cents, True
    else:
        watch = models.PriceWatch(user_id=user.id, product_id=data.product_id, target_price_cents=data.target_price_cents)
        db.add(watch)
    analytics.record_event(db, "track", user_id=user.id, product_id=data.product_id, properties={"target_price_cents": data.target_price_cents})
    db.commit()
    return {"id": watch.id, "product_id": watch.product_id, "target_price_cents": watch.target_price_cents, "active": watch.active}


@app.get("/price-watches")
def price_watches(db: Session = Depends(get_db), user: models.User = Depends(current_user)):
    watches = db.scalars(select(models.PriceWatch).where(models.PriceWatch.user_id == user.id)).all()
    return [{"id": w.id, "product_id": w.product_id, "target_price_cents": w.target_price_cents, "active": w.active} for w in watches]


@app.post("/price-watches/refresh")
def refresh_prices(db: Session = Depends(get_db), user: models.User = Depends(current_user)):
    result = PriceTrackingJob(db, price_provider).run(user.id)
    return {"checked": result.checked, "triggered": result.triggered, "updated": result.updated, "skipped_locked": result.skipped_locked, "errors": result.errors}


@app.get("/products/{product_id}/prices")
def price_history(product_id: int, db: Session = Depends(get_db), user: models.User = Depends(current_user)):
    points = db.scalars(select(models.PricePoint).where(models.PricePoint.product_id == product_id).order_by(models.PricePoint.captured_at)).all()
    return [{"price_cents": p.price_cents, "captured_at": p.captured_at} for p in points]


@app.post("/purchases", status_code=201)
def create_purchase(data: schemas.PurchaseIn, db: Session = Depends(get_db), user: models.User = Depends(current_user)):
    product = db.get(models.Product, data.product_id)
    if product is None:
        raise HTTPException(status_code=404, detail="Product not found")
    if data.decision_id is not None:
        services.owned(db, models.Decision, data.decision_id, user.id)
    purchase = models.Purchase(user_id=user.id, product_id=data.product_id, decision_id=data.decision_id, price_paid_cents=data.price_paid_cents, purchased_at=data.purchased_at or datetime.now(timezone.utc), return_deadline=data.return_deadline, warranty_deadline=data.warranty_deadline)
    db.add(purchase)
    db.flush()
    services.notify(db, user.id, "purchase", "Purchase protected", "Return and warranty dates are now tracked.")
    db.commit()
    return {"id": purchase.id, "product_id": purchase.product_id, "price_paid_cents": purchase.price_paid_cents, "satisfaction": purchase.satisfaction, "returned": purchase.returned}


@app.patch("/purchases/{purchase_id}")
def update_purchase(purchase_id: int, data: schemas.PurchaseUpdate, db: Session = Depends(get_db), user: models.User = Depends(current_user)):
    purchase = services.owned(db, models.Purchase, purchase_id, user.id)
    first_checkin = purchase.satisfaction is None and data.satisfaction is not None
    if data.satisfaction is not None:
        purchase.satisfaction = data.satisfaction
    if data.returned is not None:
        purchase.returned = data.returned
    if first_checkin:
        services.add_points(db, user.id, 15, "Post-purchase check-in", "purchase", purchase.id)
        analytics.record_event(db, "satisfaction", user_id=user.id, product_id=purchase.product_id, purchase_id=purchase.id, properties={"satisfaction": purchase.satisfaction})
    db.commit()
    return {"id": purchase.id, "satisfaction": purchase.satisfaction, "returned": purchase.returned}


@app.get("/purchases")
def purchases(db: Session = Depends(get_db), user: models.User = Depends(current_user)):
    items = db.scalars(select(models.Purchase).where(models.Purchase.user_id == user.id).order_by(models.Purchase.purchased_at.desc())).all()
    now = datetime.now(timezone.utc)
    return [{"id": p.id, "product": product_out(p.product), "price_paid_cents": p.price_paid_cents, "purchased_at": p.purchased_at, "return_deadline": p.return_deadline, "warranty_deadline": p.warranty_deadline, "return_open": bool(p.return_deadline and p.return_deadline.replace(tzinfo=timezone.utc) >= now), "satisfaction": p.satisfaction, "returned": p.returned} for p in items]


@app.get("/rewards")
def rewards(db: Session = Depends(get_db), user: models.User = Depends(current_user)):
    entries = db.scalars(select(models.PointsEntry).where(models.PointsEntry.user_id == user.id).order_by(models.PointsEntry.created_at.desc())).all()
    return {"balance": services.points_balance(db, user.id), "ledger": [{"id": e.id, "amount": e.amount, "reason": e.reason, "created_at": e.created_at} for e in entries], "catalog": [{"name": "Partner reward", "points": 100}, {"name": "Donation", "points": 250}]}


@app.post("/rewards/redeem")
def redeem(data: schemas.RedeemIn, db: Session = Depends(get_db), user: models.User = Depends(current_user)):
    if services.points_balance(db, user.id) < data.points:
        raise HTTPException(status_code=400, detail="Insufficient points")
    services.add_points(db, user.id, -data.points, f"Redeemed: {data.reward}", "redemption")
    db.commit()
    return {"balance": services.points_balance(db, user.id)}


@app.get("/notifications")
def notifications(db: Session = Depends(get_db), user: models.User = Depends(current_user)):
    items = db.scalars(select(models.Notification).where(models.Notification.user_id == user.id).order_by(models.Notification.created_at.desc())).all()
    return [{"id": n.id, "kind": n.kind, "title": n.title, "body": n.body, "read": n.read, "created_at": n.created_at} for n in items]


@app.post("/notifications/{notification_id}/read")
def read_notification(notification_id: int, db: Session = Depends(get_db), user: models.User = Depends(current_user)):
    item = services.owned(db, models.Notification, notification_id, user.id)
    item.read = True
    db.commit()
    return {"id": item.id, "read": True}


@app.get("/dashboard")
def dashboard(db: Session = Depends(get_db), user: models.User = Depends(current_user)):
    decisions = db.scalars(select(models.Decision).where(models.Decision.user_id == user.id)).all()
    purchases = db.scalars(select(models.Purchase).where(models.Purchase.user_id == user.id)).all()
    prevented = sum(d.prevented_spend_cents for d in decisions)
    savings = sum(max(0, p.product.typical_price_cents - p.price_paid_cents) for p in purchases if not p.returned)
    choice_scores = []
    for purchase in purchases:
        decision = db.get(models.Decision, purchase.decision_id) if purchase.decision_id else None
        if decision and not purchase.returned and purchase.product.current_price_cents > 0 and purchase.product.typical_price_cents > 0:
            discount = (purchase.product.typical_price_cents - purchase.price_paid_cents) / max(purchase.product.typical_price_cents, 1)
            value = max(0, min(100, round(60 + discount * 160)))
            timing = max(0, min(100, round(decision.urgency * 10 + discount * 100)))
            choice_scores.append(choice_score(value, decision.fit * 10, timing, purchase.satisfaction))
    result = {"choice_score": round(sum(choice_scores) / len(choice_scores)) if choice_scores else None, "savings_cents": savings, "prevented_spend_cents": prevented, "points_balance": services.points_balance(db, user.id), "decision_count": len(decisions), "purchase_count": len(purchases), "verdicts": {v.value: sum(d.verdict == v.value for d in decisions) for v in models.Verdict}}
    analytics.record_event(db, "repeat_check", user_id=user.id, properties={"purchase_count": len(purchases), "decision_count": len(decisions)})
    db.commit()
    return result

@app.get("/admin/metrics")
def admin_metrics(days: int = Query(default=30, ge=1, le=365), _: None = Depends(require_admin), db: Session = Depends(get_db)):
    return analytics.aggregate_metrics(db, days)

@app.get("/admin/metrics/export")
def export_admin_metrics(days: int = Query(default=30, ge=1, le=365), _: None = Depends(require_admin), db: Session = Depends(get_db)):
    return {"format": "json", "retention_days": get_settings().analytics_retention_days, "metrics": analytics.aggregate_metrics(db, days)}
