from fastapi.testclient import TestClient

from app import affiliate, main as main_module
from app.config import Settings
from app.providers import (
    FallbackPriceProvider,
    FallbackProductProvider,
    MockAffiliateProvider,
    MockPriceProvider,
    MockProductProvider,
    PassthroughAffiliateProvider,
    ProviderError,
    SerpApiShoppingProvider,
    build_runtime_providers,
)


class BrokenLiveProvider:
    def resolve(self, _query):
        raise ProviderError("offline")

    def alternatives(self, _product):
        raise ProviderError("offline")

    def current_price(self, _external_id, _fallback_cents):
        raise ProviderError("offline")


def production_settings():
    return Settings.model_construct(
        environment="production",
        database_url="postgresql+psycopg://pick:pick@db:5432/pick",
        auth_secret="strong-secret",
        affiliate_webhook_secret="strong-webhook-secret",
        admin_api_key="strong-admin-key",
        serpapi_key=None,
    )


def test_runtime_provider_selection_uses_mocks_only_in_development_or_test():
    production = production_settings()
    product, price, affiliate_provider = build_runtime_providers(production)
    assert isinstance(product, SerpApiShoppingProvider)
    assert isinstance(price, SerpApiShoppingProvider)
    assert isinstance(affiliate_provider, PassthroughAffiliateProvider)
    assert not isinstance(affiliate_provider, MockAffiliateProvider)

    development = Settings.model_construct(environment="development", serpapi_key=None)
    product, price, affiliate_provider = build_runtime_providers(development)
    assert isinstance(product, FallbackProductProvider)
    assert isinstance(price, FallbackPriceProvider)
    assert isinstance(affiliate_provider, MockAffiliateProvider)


def test_production_fallback_wrappers_never_substitute_mock_data():
    product_provider = FallbackProductProvider(BrokenLiveProvider(), MockProductProvider(), allow_mock_fallback=False)
    price_provider = FallbackPriceProvider(BrokenLiveProvider(), MockPriceProvider(), allow_mock_fallback=False)

    try:
        product_provider.resolve("headphones")
        assert False, "production must not use a mock product"
    except ProviderError:
        pass
    try:
        price_provider.current_price("headphones", 100)
        assert False, "production must not use a mock price"
    except ProviderError:
        pass


def test_live_provider_failure_returns_unavailable_low_confidence(monkeypatch):
    monkeypatch.setattr(main_module, "product_provider", BrokenLiveProvider())
    with TestClient(main_module.app) as client:
        registered = client.post("/auth/register", json={"email": "provider-unavailable@example.com", "password": "secure-pass", "name": "Provider unavailable"})
        headers = {"Authorization": f"Bearer {registered.json()['access_token']}"}
        response = client.post("/decisions/analyze", headers=headers, json={"query": "Korean live provider", "budget_cents": 10000, "urgency": 4, "fit": 8})

    assert response.status_code == 503
    assert response.json()["status"] == "unavailable"
    assert response.json()["confidence"] == "low"


def test_production_keeps_direct_clicks_but_blocks_mock_conversion_and_rewards(monkeypatch):
    monkeypatch.setattr(affiliate, "get_settings", production_settings)
    with TestClient(main_module.app) as client:
        registered = client.post("/auth/register", json={"email": "production-affiliate@example.com", "password": "secure-pass", "name": "Production affiliate"})
        headers = {"Authorization": f"Bearer {registered.json()['access_token']}"}
        product = client.get("/products/search?q=headphones", headers=headers).json()[0]
        click = client.post("/affiliate/click", headers=headers, json={"product_id": product["id"], "provider": "mock", "destination_url": product["url"]})
        assert click.status_code == 201
        assert click.json()["provider"] == "direct"

        conversion = client.post("/affiliate/conversions/import", headers=headers, json={
            "click_token": click.json()["click_token"],
            "external_conversion_id": "production-mock-conversion",
            "status": "verified",
            "gross_order_value_cents": 10000,
            "commission_cents": 1000,
            "currency": "USD",
            "occurred_at": "2026-08-12T00:00:00Z",
        })
        assert conversion.status_code == 503
        rewards = client.get("/rewards", headers=headers).json()
        assert rewards["balance"] == 20
