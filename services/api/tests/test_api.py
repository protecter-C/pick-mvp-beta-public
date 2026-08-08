from datetime import datetime, timedelta, timezone
from fastapi.testclient import TestClient
from app.main import app


def auth_headers(client: TestClient):
    response = client.post("/auth/register", json={"email": "buyer@example.com", "password": "secure-pass", "name": "Buyer"})
    assert response.status_code == 201
    return {"Authorization": f"Bearer {response.json()['access_token']}"}


def test_complete_decision_protection_reward_flow():
    with TestClient(app) as client:
        headers = auth_headers(client)
        profile = client.get("/profile", headers=headers)
        assert profile.status_code == 200

        decision_response = client.post("/decisions/analyze", headers=headers, json={"query": "headphones", "budget_cents": 18000, "urgency": 8, "fit": 9})
        assert decision_response.status_code == 201, decision_response.text
        decision = decision_response.json()
        assert decision["verdict"] == "BUY"
        assert decision["alternatives"]

        watch = client.post("/price-watches", headers=headers, json={"product_id": decision["product"]["id"], "target_price_cents": 20000})
        assert watch.status_code == 201
        refresh = client.post("/price-watches/refresh", headers=headers)
        assert refresh.json()["triggered"] == 1
        history = client.get(f"/products/{decision['product']['id']}/prices", headers=headers)
        assert history.status_code == 200
        assert len(history.json()) >= 2
        assert client.get("/notifications", headers=headers).json()

        now = datetime.now(timezone.utc)
        purchase_response = client.post("/purchases", headers=headers, json={"product_id": decision["product"]["id"], "decision_id": decision["id"], "price_paid_cents": 12000, "return_deadline": (now + timedelta(days=30)).isoformat(), "warranty_deadline": (now + timedelta(days=365)).isoformat()})
        assert purchase_response.status_code == 201
        purchase_id = purchase_response.json()["id"]
        checkin = client.patch(f"/purchases/{purchase_id}", headers=headers, json={"satisfaction": 9})
        assert checkin.status_code == 200

        dashboard = client.get("/dashboard", headers=headers).json()
        assert dashboard["choice_score"] is not None
        assert dashboard["savings_cents"] == 4900
        assert dashboard["purchase_count"] == 1
        rewards = client.get("/rewards", headers=headers).json()
        assert rewards["balance"] == 37


def test_pass_rewards_more_and_records_prevented_spend():
    with TestClient(app) as client:
        login = client.post("/auth/login", json={"email": "buyer@example.com", "password": "secure-pass"})
        headers = {"Authorization": f"Bearer {login.json()['access_token']}"}
        response = client.post("/decisions/analyze", headers=headers, json={"query": "watch", "budget_cents": 1000, "urgency": 3, "fit": 4})
        assert response.status_code == 201
        assert response.json()["verdict"] == "PASS"
        assert response.json()["prevented_spend_cents"] > 0
        assert client.get("/dashboard", headers=headers).json()["prevented_spend_cents"] > 0


def test_authentication_rejects_bad_password():
    with TestClient(app) as client:
        response = client.post("/auth/login", json={"email": "buyer@example.com", "password": "wrong"})
        assert response.status_code == 401
