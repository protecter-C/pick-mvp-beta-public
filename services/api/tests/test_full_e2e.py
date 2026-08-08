from fastapi.testclient import TestClient
from app import main as main_module
from app.main import app


class PriceTransitionProvider:
    def __init__(self):
        self.values = iter((19000, 12000))

    def current_price(self, external_id, fallback_cents):
        return next(self.values)


def test_full_purchase_protection_attribution_e2e(monkeypatch):
    monkeypatch.setattr(main_module, "price_provider", PriceTransitionProvider())
    with TestClient(app) as client:
        auth = client.post("/auth/register", json={"email": "full-e2e@example.com", "password": "secure-pass", "name": "Full E2E"})
        headers = {"Authorization": f"Bearer {auth.json()['access_token']}"}
        decision = client.post("/decisions/analyze", headers=headers, json={"query": "headphones", "budget_cents": 18000, "urgency": 8, "fit": 9}).json()
        assert decision["verdict"] == "BUY"
        product = decision["product"]
        watch = client.post("/price-watches", headers=headers, json={"product_id": product["id"], "target_price_cents": 12500})
        assert watch.status_code == 201
        assert client.post("/price-watches/refresh", headers=headers).json()["triggered"] == 0
        refresh = client.post("/price-watches/refresh", headers=headers).json()
        assert refresh["triggered"] == 2

        click = client.post("/affiliate/click", headers=headers, json={"product_id": product["id"], "provider": "mock", "destination_url": product["url"]}).json()
        conversion = client.post("/affiliate/conversions/import", headers=headers, json={"click_token": click["click_token"], "external_conversion_id": "full-e2e-conversion", "status": "verified", "gross_order_value_cents": 12000, "commission_cents": 500, "currency": "USD", "occurred_at": "2026-08-08T00:00:00Z"})
        assert conversion.status_code == 201
        purchase = client.post("/purchases", headers=headers, json={"product_id": product["id"], "decision_id": decision["id"], "price_paid_cents": 12000}).json()
        assert client.patch(f"/purchases/{purchase['id']}", headers=headers, json={"satisfaction": 9}).status_code == 200
        dashboard = client.get("/dashboard", headers=headers).json()
        assert dashboard["choice_score"] is not None
        assert dashboard["points_balance"] == 87
        assert dashboard["purchase_count"] == 1
