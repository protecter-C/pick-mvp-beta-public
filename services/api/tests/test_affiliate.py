import hashlib
import hmac
import json
from fastapi.testclient import TestClient
from app.main import app


def test_affiliate_click_conversion_is_verified_and_idempotent():
    with TestClient(app) as client:
        registered = client.post("/auth/register", json={"email": "affiliate@example.com", "password": "secure-pass", "name": "Affiliate"})
        headers = {"Authorization": f"Bearer {registered.json()['access_token']}"}
        product = client.get("/products/search?q=headphones", headers=headers).json()[0]
        click = client.post("/affiliate/click", headers=headers, json={"product_id": product["id"], "provider": "mock", "destination_url": "https://shop.example/item?utm_source=pick"})
        assert click.status_code == 201
        click_data = click.json()
        assert "pick_click_token=" in click_data["outbound_url"]
        assert client.get(f"/affiliate/click/{click_data['click_token']}").status_code == 200

        payload = {"click_token": click_data["click_token"], "external_conversion_id": "conv-1", "external_order_id": "order-1", "status": "verified", "gross_order_value_cents": 12900, "commission_cents": 1000, "currency": "USD", "occurred_at": "2026-08-08T00:00:00Z"}
        first = client.post("/affiliate/conversions/import", headers=headers, json=payload)
        second = client.post("/affiliate/conversions/import", headers=headers, json=payload)
        assert first.status_code == second.status_code == 201
        assert first.json()["id"] == second.json()["id"]
        assert first.json()["reward_points"] == 100
        rewards = client.get("/rewards", headers=headers).json()
        assert rewards["balance"] == 120
        assert len([entry for entry in rewards["ledger"] if entry["reason"] == "Verified affiliate purchase reward"]) == 1


def test_signed_webhook_and_refund_reverse_reward_once():
    with TestClient(app) as client:
        registered = client.post("/auth/register", json={"email": "webhook@example.com", "password": "secure-pass", "name": "Webhook"})
        headers = {"Authorization": f"Bearer {registered.json()['access_token']}"}
        product = client.get("/products/search?q=watch", headers=headers).json()[0]
        click = client.post("/affiliate/click", headers=headers, json={"product_id": product["id"], "destination_url": "https://shop.example/watch", "provider": "mock"}).json()
        payload = {"click_token": click["click_token"], "external_conversion_id": "conv-webhook", "status": "verified", "gross_order_value_cents": 10000, "commission_cents": 500, "currency": "USD", "occurred_at": "2026-08-08T00:00:00Z"}
        body = json.dumps(payload, separators=(",", ":")).encode()
        signature = hmac.new(b"test-affiliate-secret", body, hashlib.sha256).hexdigest()
        webhook = client.post("/affiliate/webhook/mock", content=body, headers={"X-Affiliate-Signature": f"sha256={signature}", "Content-Type": "application/json"})
        assert webhook.status_code == 200
        assert client.post("/affiliate/webhook/mock", content=body, headers={"X-Affiliate-Signature": f"sha256={signature}", "Content-Type": "application/json"}).status_code == 200
        payload["status"] = "refunded"
        refund_body = json.dumps(payload, separators=(",", ":")).encode()
        refund_signature = hmac.new(b"test-affiliate-secret", refund_body, hashlib.sha256).hexdigest()
        refund = client.post("/affiliate/webhook/mock", content=refund_body, headers={"X-Affiliate-Signature": refund_signature, "Content-Type": "application/json"})
        assert refund.status_code == 200
        assert refund.json()["status"] == "refunded"
        assert client.get("/rewards", headers=headers).json()["balance"] == 20


def test_invalid_webhook_signature_is_rejected():
    with TestClient(app) as client:
        response = client.post("/affiliate/webhook/mock", content=b"{}", headers={"X-Affiliate-Signature": "bad", "Content-Type": "application/json"})
        assert response.status_code == 401
