from app.providers import FallbackProductProvider, MockProductProvider, ProviderError, SerpApiShoppingProvider, normalize_url, price_to_cents


SHOPPING_RESPONSE = {
    "shopping_results": [
        {
            "product_id": "abc-123",
            "title": "  Noise Cancelling Headphones  ",
            "source": "  Best   Buy ",
            "price": "$1,299.00",
            "extracted_price": 1299,
            "old_price": "$1,599.00",
            "extracted_old_price": 1599,
            "rating": 4.5,
            "product_link": "HTTPS://Shop.Example/item/abc/?utm_source=google&color=black#reviews",
            "thumbnail": "https://cdn.example/item.jpg",
        },
        {"product_id": "other", "title": "Alternative", "source": "Store", "extracted_price": 99.0, "product_link": "https://shop.example/other"},
    ]
}


def test_serpapi_normalizes_product_seller_price_url_and_caches():
    calls = []
    provider = SerpApiShoppingProvider(api_key="test-key", cache_ttl=60, fetch_json=lambda params: calls.append(params) or SHOPPING_RESPONSE)
    product = provider.resolve("headphones")
    again = provider.resolve(" HEADPHONES ")
    assert len(calls) == 1
    assert product.external_id == "abc-123"
    assert product.url == "https://shop.example/item/abc?color=black"
    assert product.merchant == "Best Buy"
    assert product.current_price_cents == 129900
    assert product.typical_price_cents == 159900
    assert product.rating == 90
    assert product.observed_at is not None
    assert again.external_id == product.external_id
    assert again.current_price_cents == product.current_price_cents


def test_serpapi_retries_transient_failure_and_maps_price():
    calls = 0

    def flaky(_params):
        nonlocal calls
        calls += 1
        if calls == 1:
            raise TimeoutError("temporary")
        return SHOPPING_RESPONSE

    provider = SerpApiShoppingProvider(api_key="test-key", retries=1, fetch_json=flaky)
    assert provider.current_price("abc-123", 100) == 129900
    assert calls == 2


def test_korean_query_uses_korean_shopping_locale_and_won_minor_units():
    calls = []
    response = {"shopping_results": [{"product_id": "kr-1", "title": "무선 헤드폰", "source": "  판매   자 ", "price": "₩129,000", "extracted_price": 129000, "product_link": "https://shop.kr/p/1"}]}
    provider = SerpApiShoppingProvider(api_key="test-key", fetch_json=lambda params: calls.append(params) or response)
    product = provider.resolve("무선 헤드폰")
    assert calls[0]["hl"] == "ko"
    assert calls[0]["gl"] == "kr"
    assert calls[0]["location"] == "Seoul, South Korea"
    assert product.currency == "KRW"
    assert product.current_price_cents == 129000
    assert product.merchant == "판매 자"


def test_sponsored_missing_and_duplicate_results_are_excluded_without_changing_identity():
    response = {"shopping_results": [
        {"product_id": "sponsored", "title": "Paid listing", "source": "Ads", "extracted_price": 1, "tag": "Sponsored", "product_link": "https://ads.example/p"},
        {"product_id": "same", "title": "Canonical item", "source": "Seller A", "extracted_price": 10, "product_link": "https://shop.example/item"},
        {"product_id": "same", "title": "Canonical item duplicate", "source": "Seller B", "extracted_price": 11, "product_link": "https://other.example/item"},
        {"product_id": "missing-price", "title": "No price", "source": "Seller", "product_link": "https://shop.example/no-price"},
    ]}
    provider = SerpApiShoppingProvider(api_key="test-key", fetch_json=lambda _params: response)
    product = provider.resolve("canonical")
    alternatives = provider.alternatives(product)
    assert product.external_id == "same"
    assert product.current_price_cents == 1000
    assert all(item.external_id != "same" for item in alternatives)
    assert all(item.external_id != "sponsored" for item in alternatives)


def test_price_change_keeps_stable_product_identity():
    responses = iter([
        {"shopping_results": [{"product_id": "stable", "title": "Item", "source": "Store", "extracted_price": 10, "product_link": "https://shop.example/item"}]},
        {"shopping_results": [{"product_id": "stable", "title": "Item", "source": "Store", "extracted_price": 8, "product_link": "https://shop.example/item"}]},
    ])
    provider = SerpApiShoppingProvider(api_key="test-key", cache_ttl=0, fetch_json=lambda _params: next(responses))
    first = provider.resolve("item")
    second = provider.resolve("item")
    assert first.external_id == second.external_id == "stable"
    assert first.current_price_cents == 1000
    assert second.current_price_cents == 800


def test_missing_real_provider_uses_mock_fallback():
    class Broken:
        def resolve(self, query):
            raise ProviderError("offline")

        def alternatives(self, product):
            raise ProviderError("offline")

    product = FallbackProductProvider(Broken(), MockProductProvider()).resolve("headphones")
    assert product.external_id == "headphones-1"


def test_url_and_localized_price_normalization_removes_tracking():
    assert normalize_url("https://shop.example/p/?utm_source=x&gclid=y&sku=1#details") == "https://shop.example/p?sku=1"
    assert price_to_cents("1.299,99 €", "EUR") == 129999
    assert price_to_cents("$1,299.99", "USD") == 129999
    assert price_to_cents("₩129,000", "KRW") == 129000
