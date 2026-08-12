from datetime import datetime, timedelta, timezone
from contextvars import ContextVar
from uuid import uuid4
from sqlalchemy import distinct, func, select
from sqlalchemy.orm import Session
from . import models

EVENT_NAMES = frozenset({"product_check", "first_check", "verdict", "evidence_view", "track", "price_track", "buy_action", "wait_action", "pass_action", "merchant_click", "conversion", "reward", "satisfaction", "realized_savings", "realized_savings_reversal", "choice_score_change", "repeat_check", "feedback", "error"})
TRAFFIC_SOURCES = frozenset({"organic", "admin", "health", "deployment", "bot", "test", "unclassified", "system"})
_traffic_context: ContextVar[dict] = ContextVar("pick_traffic_context", default={"source": "system", "route": "system"})


def set_traffic_context(source: str, route: str):
    """Request metadata is classified transiently; no IP or raw user agent is stored."""
    return _traffic_context.set({"source": source if source in TRAFFIC_SOURCES else "unclassified", "route": route[:80]})


def reset_traffic_context(token) -> None:
    _traffic_context.reset(token)

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
    context = _traffic_context.get()
    event_properties = _safe_properties(properties)
    event_properties.setdefault("traffic_source", context["source"])
    event_properties.setdefault("route", context["route"])
    event = models.AnalyticsEvent(event_id=event_id, event_name=event_name, user_id=user_id, product_id=product_id, decision_id=decision_id, purchase_id=purchase_id, conversion_id=conversion_id, value_cents=value_cents, points=points, properties=event_properties, occurred_at=occurred_at or datetime.now(timezone.utc))
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
    event_rows = db.execute(select(models.AnalyticsEvent.user_id, models.AnalyticsEvent.event_name, models.AnalyticsEvent.occurred_at, models.AnalyticsEvent.properties).where(models.AnalyticsEvent.occurred_at >= since)).all()
    def utc(value: datetime) -> datetime:
        return value if value.tzinfo else value.replace(tzinfo=timezone.utc)
    def source(properties: dict | None) -> str:
        value = (properties or {}).get("traffic_source", "unclassified")
        return value if value in TRAFFIC_SOURCES else "unclassified"
    organic_rows = [row for row in event_rows if source(row.properties) == "organic" and row.user_id is not None]
    organic_users = {row.user_id for row in organic_rows}
    activated_users = {row.user_id for row in organic_rows if row.event_name == "verdict"}
    engaged_events = {"evidence_view", "price_track", "merchant_click"}
    engaged_users = {row.user_id for row in organic_rows if row.event_name in engaged_events}
    checks_by_user: dict[int, set] = {}
    for row in organic_rows:
        if row.event_name == "product_check":
            checks_by_user.setdefault(row.user_id, set()).add(row.occurred_at.date())
    returning_users = {user_id for user_id, check_dates in checks_by_user.items() if len(check_dates) > 1}
    active_since = now - timedelta(days=7)
    cohort_cutoff = now - timedelta(days=14)
    activation_dates: dict[int, datetime] = {}
    for row in organic_rows:
        if row.event_name == "verdict" and (row.user_id not in activation_dates or row.occurred_at < activation_dates[row.user_id]):
            activation_dates[row.user_id] = utc(row.occurred_at)
    eligible_users = {user_id for user_id, activated_at in activation_dates.items() if activated_at < cohort_cutoff}
    retained_users = {row.user_id for row in organic_rows if row.user_id in eligible_users and utc(row.occurred_at) >= active_since and row.event_name != "error"}
    source_counts: dict[str, int] = {}
    for row in event_rows:
        value = source(row.properties)
        source_counts[value] = source_counts.get(value, 0) + 1
    # PostgreSQL's JSON type has no equality operator, so aggregate the small
    # operational error stream in Python rather than grouping on raw JSON.
    error_rows = [row for row in event_rows if row.event_name == "error"]
    errors: dict[str, int] = {}
    errors_by_source: dict[str, int] = {}
    errors_by_route: dict[str, int] = {}
    organic_errors = 0
    for row in error_rows:
        properties = row.properties or {}
        status = str(properties.get("status_code", "unknown"))
        traffic_source = source(properties)
        route = str(properties.get("route", "unclassified"))
        errors[status] = errors.get(status, 0) + 1
        errors_by_source[traffic_source] = errors_by_source.get(traffic_source, 0) + 1
        errors_by_route[route] = errors_by_route.get(route, 0) + 1
        organic_errors += traffic_source == "organic"
    feedback_rows = db.execute(select(models.BetaFeedback.category, func.count(models.BetaFeedback.id)).where(models.BetaFeedback.created_at >= since).group_by(models.BetaFeedback.category)).all()
    invitations = {
        "invited": int(db.scalar(select(func.count(models.BetaInvite.id))) or 0),
        "accepted": int(db.scalar(select(func.count(models.BetaInvite.id)).where(models.BetaInvite.accepted_at.is_not(None))) or 0),
    }
    return {
        "window_days": days,
        "events": aggregate_metrics(db, days),
        "traffic": {"organic_events": source_counts.get("organic", 0), "excluded_events": sum(count for key, count in source_counts.items() if key != "organic"), "by_source": source_counts},
        "cohort": {"organic_users": len(organic_users), "activated_users": len(activated_users), "engaged_users": len(engaged_users), "returning_users": len(returning_users)},
        "retention": {"eligible_14d": len(eligible_users), "retained_7d": len(retained_users), "rate_percent": round(len(retained_users) * 100 / len(eligible_users)) if eligible_users else None},
        "errors": {"total": sum(errors.values()), "organic_total": organic_errors, "excluded_total": sum(errors.values()) - organic_errors, "by_status": errors, "by_source": errors_by_source, "by_route": errors_by_route},
        "feedback": {"total": sum(int(count) for _, count in feedback_rows), "by_category": {category: int(count) for category, count in feedback_rows}},
        "invitations": invitations,
    }
