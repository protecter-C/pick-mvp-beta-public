from datetime import datetime, timedelta, timezone
from uuid import uuid4
from sqlalchemy import distinct, func, select
from sqlalchemy.orm import Session
from . import models

EVENT_NAMES = frozenset({"product_check", "first_check", "verdict", "evidence_view", "track", "price_track", "buy_action", "wait_action", "pass_action", "merchant_click", "conversion", "reward", "satisfaction", "realized_savings", "realized_savings_reversal", "choice_score_change", "repeat_check", "feedback", "error"})

def _safe_properties(properties: dict | None) -> dict:
    if not properties:
        return {}
    safe = {}
    for key, value in properties.items():
        if not isinstance(key, str) or len(key) > 40 or not isinstance(value, (str, int, float, bool)):
            continue
        safe[key] = value[:120] if isinstance(value, str) else value
    return safe

def record_event(db: Session, event_name: str, *, event_id: str | None = None, user_id: int | None = None, product_id: int | None = None, decision_id: int | None = None, purchase_id: int | None = None, conversion_id: int | None = None, value_cents: int | None = None, points: int | None = None, properties: dict | None = None, occurred_at: datetime | None = None) -> models.AnalyticsEvent:
    if event_name not in EVENT_NAMES:
        raise ValueError(f"unsupported analytics event: {event_name}")
    event_id = event_id or str(uuid4())
    existing = db.scalar(select(models.AnalyticsEvent).where(models.AnalyticsEvent.event_id == event_id))
    if existing is not None:
        return existing
    event = models.AnalyticsEvent(event_id=event_id, event_name=event_name, user_id=user_id, product_id=product_id, decision_id=decision_id, purchase_id=purchase_id, conversion_id=conversion_id, value_cents=value_cents, points=points, properties=_safe_properties(properties), occurred_at=occurred_at or datetime.now(timezone.utc))
    db.add(event)
    db.flush()
    return event

def aggregate_metrics(db: Session, days: int = 30) -> dict:
    days = max(1, min(days, 365))
    since = datetime.now(timezone.utc) - timedelta(days=days)
    rows = db.execute(select(models.AnalyticsEvent.event_name, func.count(models.AnalyticsEvent.id), func.count(distinct(models.AnalyticsEvent.user_id)), func.coalesce(func.sum(models.AnalyticsEvent.value_cents), 0), func.coalesce(func.sum(models.AnalyticsEvent.points), 0)).where(models.AnalyticsEvent.occurred_at >= since).group_by(models.AnalyticsEvent.event_name)).all()
    events = [{"event_name": name, "count": int(count), "unique_users": int(users), "value_cents": int(value or 0), "points": int(points or 0)} for name, count, users, value, points in rows]
    return {"window_days": days, "total_events": sum(item["count"] for item in events), "events": sorted(events, key=lambda item: item["event_name"])}


def beta_dashboard(db: Session, days: int = 30) -> dict:
    """Aggregate operational signals only; never expose beta-user identities."""
    days = max(1, min(days, 365))
    now = datetime.now(timezone.utc)
    since = now - timedelta(days=days)
    active_since = now - timedelta(days=7)
    cohort_cutoff = now - timedelta(days=14)
    active_user_ids = select(distinct(models.AnalyticsEvent.user_id)).where(
        models.AnalyticsEvent.user_id.is_not(None),
        models.AnalyticsEvent.occurred_at >= active_since,
        models.AnalyticsEvent.event_name != "error",
    )
    eligible = int(db.scalar(select(func.count(models.User.id)).where(models.User.created_at < cohort_cutoff)) or 0)
    retained = int(db.scalar(select(func.count(models.User.id)).where(models.User.created_at < cohort_cutoff, models.User.id.in_(active_user_ids))) or 0)
    new_users = int(db.scalar(select(func.count(models.User.id)).where(models.User.created_at >= since)) or 0)
    active_users = int(db.scalar(select(func.count(distinct(models.AnalyticsEvent.user_id))).where(models.AnalyticsEvent.occurred_at >= since, models.AnalyticsEvent.user_id.is_not(None), models.AnalyticsEvent.event_name != "error")) or 0)
    error_rows = db.execute(select(models.AnalyticsEvent.properties, func.count(models.AnalyticsEvent.id)).where(models.AnalyticsEvent.event_name == "error", models.AnalyticsEvent.occurred_at >= since).group_by(models.AnalyticsEvent.properties)).all()
    errors: dict[str, int] = {}
    for properties, count in error_rows:
        status = str((properties or {}).get("status_code", "unknown"))
        errors[status] = errors.get(status, 0) + int(count)
    feedback_rows = db.execute(select(models.BetaFeedback.category, func.count(models.BetaFeedback.id)).where(models.BetaFeedback.created_at >= since).group_by(models.BetaFeedback.category)).all()
    invitations = {
        "invited": int(db.scalar(select(func.count(models.BetaInvite.id))) or 0),
        "accepted": int(db.scalar(select(func.count(models.BetaInvite.id)).where(models.BetaInvite.accepted_at.is_not(None))) or 0),
    }
    return {
        "window_days": days,
        "events": aggregate_metrics(db, days),
        "cohort": {"new_users": new_users, "active_users": active_users},
        "retention": {"eligible_14d": eligible, "retained_7d": retained, "rate_percent": round(retained * 100 / eligible) if eligible else None},
        "errors": {"total": sum(errors.values()), "by_status": errors},
        "feedback": {"total": sum(int(count) for _, count in feedback_rows), "by_category": {category: int(count) for category, count in feedback_rows}},
        "invitations": invitations,
    }
