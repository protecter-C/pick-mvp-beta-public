from fastapi.testclient import TestClient

from app.main import app


ORGANIC = {"User-Agent": "Mozilla/5.0 PICK Beta Browser"}


def test_organic_cohorts_and_error_segmentation_exclude_test_and_admin_traffic():
    with TestClient(app) as client:
        registered = client.post("/auth/register", headers=ORGANIC, json={"email": "organic-monitoring@example.com", "password": "secure-pass", "name": "Organic monitor"})
        headers = {**ORGANIC, "Authorization": f"Bearer {registered.json()['access_token']}"}
        decision = client.post("/decisions/analyze", headers=headers, json={"query": "organic monitoring headphones", "budget_cents": 20000, "urgency": 4, "fit": 8}).json()
        assert client.get(f"/decisions/{decision['id']}", headers=headers).status_code == 200
        assert client.post("/price-watches", headers=headers, json={"product_id": decision["product"]["id"], "target_price_cents": 10000}).status_code == 201
        assert client.get("/dashboard", headers=headers).status_code == 200
        assert client.get("/unknown-route", headers=ORGANIC).status_code == 404
        assert client.get("/notifications").status_code == 401
        assert client.get("/admin/beta-dashboard").status_code == 403

        beta = client.get("/admin/beta-dashboard", headers={"X-Admin-Key": "test-admin"})
        assert beta.status_code == 200
        body = beta.json()
        assert body["cohort"]["organic_users"] >= 1
        assert body["cohort"]["activated_users"] >= 1
        assert body["cohort"]["engaged_users"] >= 1
        assert body["traffic"]["by_source"]["organic"] >= 1
        assert body["traffic"]["by_source"]["test"] >= 1
        assert body["errors"]["organic_total"] >= 1
        assert body["errors"]["by_route"]["unmatched"] >= 1
        assert body["errors"]["by_source"]["admin"] >= 1
