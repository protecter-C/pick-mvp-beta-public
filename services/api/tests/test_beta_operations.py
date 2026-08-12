from datetime import datetime, timezone

from fastapi.testclient import TestClient

from app import main as main_module, models
from app.config import Settings
from app.database import SessionLocal


def test_beta_feedback_events_admin_dashboard_and_invites():
    with TestClient(main_module.app) as client:
        admin = {"X-Admin-Key": "test-admin"}
        assert client.post("/admin/beta-invites", headers=admin, json={"email": "invited@example.com"}).status_code == 201
        assert client.get("/admin/beta-invites", headers=admin).json()["invited"] >= 1

        registered = client.post("/auth/register", json={"email": "beta-ops@example.com", "password": "secure-pass", "name": "Beta ops"})
        headers = {"Authorization": f"Bearer {registered.json()['access_token']}"}
        decision = client.post("/decisions/analyze", headers=headers, json={"query": "beta operations headphones", "budget_cents": 20000, "urgency": 4, "fit": 8}).json()
        product_id, decision_id = decision["product"]["id"], decision["id"]
        assert client.get(f"/decisions/{decision_id}", headers=headers).status_code == 200
        assert client.post("/price-watches", headers=headers, json={"product_id": product_id, "target_price_cents": 10000}).status_code == 201
        purchase = client.post("/purchases", headers=headers, json={"product_id": product_id, "decision_id": decision_id, "price_paid_cents": 9000}).json()
        assert client.patch(f"/purchases/{purchase['id']}", headers=headers, json={"satisfaction": 8}).status_code == 200
        feedback = client.post("/beta-feedback", headers=headers, json={"decision_id": decision_id, "category": "accuracy", "rating": 4, "message": "Useful and concise"})
        assert feedback.status_code == 201
        assert client.get("/dashboard", headers=headers).status_code == 200

        dashboard = client.get("/admin/beta-dashboard", headers=admin)
        assert dashboard.status_code == 200
        body = dashboard.json()
        names = {item["event_name"] for item in body["events"]["events"]}
        assert {"first_check", "verdict", "evidence_view", "price_track", "satisfaction", "realized_savings", "choice_score_change", "repeat_check", "feedback"} <= names
        assert body["feedback"]["by_category"]["accuracy"] >= 1
        assert "retention" in body and "errors" in body and "cohort" in body
        assert client.get("/admin/beta-dashboard").status_code == 403


def test_production_registration_requires_invite_or_allowlist(monkeypatch):
    production = Settings.model_construct(
        environment="production",
        beta_invite_required=True,
        beta_allowlist_emails="allowlisted@example.com",
        database_url="postgresql+psycopg://pick:pick@db:5432/pick",
        auth_secret="strong-secret",
        affiliate_webhook_secret="strong-webhook-secret",
        admin_api_key="strong-admin-key",
        serpapi_key="key",
    )
    monkeypatch.setattr(main_module, "get_settings", lambda: production)
    with TestClient(main_module.app) as client:
        rejected = client.post("/auth/register", json={"email": "uninvited@example.com", "password": "secure-pass", "name": "Uninvited"})
        assert rejected.status_code == 403
        allowed = client.post("/auth/register", json={"email": "allowlisted@example.com", "password": "secure-pass", "name": "Allowlisted"})
        assert allowed.status_code == 201

        db = SessionLocal()
        try:
            db.add(models.BetaInvite(email="invited-production@example.com", invited_at=datetime.now(timezone.utc)))
            db.commit()
        finally:
            db.close()
        invited = client.post("/auth/register", json={"email": "invited-production@example.com", "password": "secure-pass", "name": "Invited"})
        assert invited.status_code == 201
