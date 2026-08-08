from fastapi.testclient import TestClient
from app.main import app

def test_closed_beta_analytics_and_admin_metrics():
    with TestClient(app) as client:
        email = "analytics@example.com"
        registered = client.post("/auth/register", json={"email": email, "password": "secret123", "name": "Analytics"})
        token = registered.json()["access_token"]
        headers = {"Authorization": f"Bearer {token}"}
        decision = client.post("/decisions/analyze", headers=headers, json={"query": "https://example.com/analytics-phone", "budget_cents": 150000, "urgency": 2, "fit": 8})
        assert decision.status_code == 201
        decision_id = decision.json()["id"]
        product_id = decision.json()["product"]["id"]
        assert client.get(f"/decisions/{decision_id}", headers=headers).status_code == 200
        assert client.post("/price-watches", headers=headers, json={"product_id": product_id, "target_price_cents": 90000}).status_code == 201
        assert client.get("/dashboard", headers=headers).status_code == 200
        metrics = client.get("/admin/metrics", headers={"X-Admin-Key": "test-admin"})
        assert metrics.status_code == 200
        names = {item["event_name"] for item in metrics.json()["events"]}
        assert {"product_check", "verdict", "evidence_view", "track", "repeat_check", "reward"} <= names
        assert any(name in names for name in {"buy_action", "wait_action", "pass_action"})
        assert client.get("/admin/metrics", headers={"X-Admin-Key": "wrong"}).status_code == 403
        assert client.get("/missing", headers=headers).status_code == 404
        assert "error" in {item["event_name"] for item in client.get("/admin/metrics", headers={"X-Admin-Key": "test-admin"}).json()["events"]}
