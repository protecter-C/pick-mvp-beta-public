from dataclasses import dataclass
from datetime import datetime, timezone
from hashlib import sha256
import json
import re
import threading
import time
from typing import Protocol
from urllib.parse import parse_qsl, urlencode, urlparse, urlunparse
from urllib.request import Request, urlopen

from .config import get_settings


@dataclass(frozen=True)
class ProductData:
    external_id: str
    url: str
    name: str
    category: str
    merchant: str
    current_price_cents: int
    typical_price_cents: int
    rating: int
    currency: str = "USD"
    image_url: str | None = None
    observed_at: datetime | None = None

    def __post_init__(self):
        if self.observed_at is None:
            object.__setattr__(self, "observed_at", datetime.now(timezone.utc))


class ProductProvider(Protocol):
    def resolve(self, query: str) -> ProductData: ...
    def alternatives(self, product: ProductData) -> list[ProductData]: ...


class PriceProvider(Protocol):
    def current_price(self, external_id: str, fallback_cents: int) -> int: ...


class AffiliateProvider(Protocol):
    def outbound_url(self, product_url: str) -> str: ...


class NotificationProvider(Protocol):
    def deliver(self, user_id: int, title: str, body: str) -> None: ...


class ProviderError(RuntimeError):
    """A provider failed or returned unusable data."""


class ProviderUnavailable(ProviderError):
    """Live provider data cannot support a decision at this time."""


def normalize_url(value: str) -> str:
    parsed = urlparse(value.strip())
    if not parsed.scheme or not parsed.netloc:
        return value.strip()
    tracking_keys = {"gclid", "fbclid", "ref", "referrer", "affiliate", "affiliate_id", "affid"}
    query = [(key, item) for key, item in parse_qsl(parsed.query, keep_blank_values=True) if not key.lower().startswith("utm_") and key.lower() not in tracking_keys]
    return urlunparse((parsed.scheme.lower(), parsed.netloc.lower(), parsed.path.rstrip("/") or "/", "", urlencode(query), ""))


def normalize_seller(value: str | None) -> str:
    return re.sub(r"\s+", " ", (value or "Unknown seller").strip())[:120] or "Unknown seller"


def price_to_cents(value: object, currency: str = "USD") -> int | None:
    minor_digits = 0 if currency.upper() in {"KRW", "JPY"} else 2
    if isinstance(value, (int, float)):
        return max(0, round(float(value) * (10**minor_digits)))
    if not isinstance(value, str):
        return None
    cleaned = re.sub(r"[^\d,.-]", "", value)
    if not cleaned:
        return None
    if "," in cleaned and "." in cleaned:
        cleaned = cleaned.replace(".", "").replace(",", ".") if cleaned.rfind(",") > cleaned.rfind(".") else cleaned.replace(",", "")
    elif "," in cleaned:
        tail = cleaned.rsplit(",", 1)[1]
        cleaned = cleaned.replace(",", "") if len(tail) == 3 else cleaned.replace(",", ".")
    try:
        return max(0, round(float(cleaned) * (10**minor_digits)))
    except ValueError:
        return None


def detect_currency(item: dict, default: str = "USD") -> str:
    explicit = str(item.get("currency") or "").upper()
    if explicit in {"USD", "KRW", "JPY", "EUR", "GBP", "CAD", "AUD"}:
        return explicit
    text = " ".join(str(item.get(key) or "") for key in ("price", "old_price", "alternative_price"))
    if "₩" in text or "KRW" in text.upper():
        return "KRW"
    if "¥" in text or "JPY" in text.upper():
        return "JPY"
    if "€" in text or "EUR" in text.upper():
        return "EUR"
    if "£" in text or "GBP" in text.upper():
        return "GBP"
    return default


def is_sponsored(item: dict) -> bool:
    flags = (item.get("sponsored"), item.get("is_sponsored"), item.get("ad"))
    if any(flag is True or str(flag).casefold() in {"true", "1", "yes"} for flag in flags):
        return True
    labels = [item.get(key) for key in ("tag", "badge", "label", "type")]
    return any("sponsor" in str(label).casefold() or str(label).casefold() in {"ad", "ads", "advertisement"} for label in labels if label)


def infer_category(text: str, hint: str | None = None) -> str:
    value = f"{hint or ''} {text}".casefold()
    if any(term in value for term in ("headphone", "earbud", "phone", "laptop", "tablet", "헤드폰", "이어폰", "스마트폰", "노트북", "태블릿")):
        return "electronics"
    if any(term in value for term in ("humidifier", "coffee", "vacuum", "kitchen", "가습기", "커피", "청소기", "주방")):
        return "home"
    if any(term in value for term in ("cream", "serum", "cosmetic", "beauty", "크림", "세럼", "화장품", "뷰티")):
        return "beauty"
    return "shopping"


CATALOG = (
    ProductData("headphones-1", "https://example.com/headphones", "Focus ANC Headphones", "audio", "Example", 12900, 16900, 86),
    ProductData("headphones-2", "https://example.com/earbuds", "Everyday Wireless Earbuds", "audio", "Example", 7900, 9900, 82),
    ProductData("coffee-1", "https://example.com/coffee", "Compact Coffee Maker", "home", "Example", 6900, 8900, 80),
    ProductData("watch-1", "https://example.com/watch", "Active Smart Watch", "wearables", "Example", 14900, 19900, 84),
)


class MockProductProvider:
    def resolve(self, query: str) -> ProductData:
        lowered = query.lower()
        for product in CATALOG:
            if lowered in product.name.lower() or lowered == product.url.lower() or lowered == product.external_id:
                return product
        digest = sha256(query.encode()).hexdigest()
        price = 5000 + int(digest[:4], 16) % 25000
        merchant = urlparse(query).netloc or "Mock Market"
        label = urlparse(query).path.rstrip("/").split("/")[-1].replace("-", " ").title() if merchant else query.title()
        return ProductData(digest[:16], query if merchant else f"https://example.com/search?q={query}", label or "Imported Product", "other", merchant, price, round(price * 1.15), 78)

    def alternatives(self, product: ProductData) -> list[ProductData]:
        matches = [item for item in CATALOG if item.category == product.category and item.external_id != product.external_id]
        if not matches:
            matches = sorted(CATALOG, key=lambda item: abs(item.current_price_cents - product.current_price_cents))
        return list(matches[:3])


class MockPriceProvider:
    def current_price(self, external_id: str, fallback_cents: int) -> int:
        shift = int(sha256(external_id.encode()).hexdigest()[-2:], 16) % 9 - 4
        return max(100, round(fallback_cents * (100 + shift) / 100))


class SerpApiShoppingProvider:
    """Real Google Shopping data via SerpApi, with bounded retry and TTL cache."""

    endpoint = "https://serpapi.com/search.json"

    def __init__(self, api_key: str | None = None, timeout: float | None = None, retries: int | None = None, cache_ttl: int | None = None, fetch_json=None):
        settings = get_settings()
        self.api_key = api_key if api_key is not None else settings.serpapi_key
        self.timeout = timeout if timeout is not None else settings.provider_timeout_seconds
        self.retries = max(0, retries if retries is not None else settings.provider_retries)
        self.cache_ttl = max(0, cache_ttl if cache_ttl is not None else settings.provider_cache_ttl_seconds)
        self._fetch_json = fetch_json or self._fetch
        self._cache: dict[str, tuple[float, dict]] = {}
        self._lock = threading.Lock()

    def _fetch(self, params: dict) -> dict:
        request = Request(f"{self.endpoint}?{urlencode(params)}", headers={"Accept": "application/json", "User-Agent": "PICK/0.1"})
        with urlopen(request, timeout=self.timeout) as response:
            return json.load(response)

    def _search(self, query: str) -> list[dict]:
        if not self.api_key:
            raise ProviderError("SERPAPI_KEY is not configured")
        key = query.strip().lower()
        now = time.monotonic()
        with self._lock:
            cached = self._cache.get(key)
            if cached and now - cached[0] < self.cache_ttl:
                return list(cached[1].get("shopping_results", []))
        settings = get_settings()
        korean = bool(re.search(r"[\uac00-\ud7a3]", query))
        params = {
            "engine": "google_shopping", "q": query, "api_key": self.api_key,
            "location": settings.provider_location_ko if korean else settings.provider_location,
            "hl": "ko" if korean else settings.provider_language,
            "gl": "kr" if korean else settings.provider_country,
        }
        last_error: Exception | None = None
        for attempt in range(self.retries + 1):
            try:
                payload = self._fetch_json(params)
                if payload.get("error"):
                    raise ProviderError(str(payload["error"]))
                with self._lock:
                    self._cache[key] = (time.monotonic(), payload)
                return list(payload.get("shopping_results", []))
            except Exception as error:
                last_error = error
                if attempt < self.retries:
                    time.sleep(min(0.05 * (2**attempt), 0.25))
        raise ProviderError(f"SerpApi request failed: {last_error}") from last_error

    @staticmethod
    def _identity(item: dict, canonical_url: str, seller: str) -> str:
        if item.get("product_id"):
            return str(item["product_id"]).strip()
        if canonical_url and urlparse(canonical_url).netloc:
            return sha256(f"url:{canonical_url}".encode()).hexdigest()[:16]
        title = re.sub(r"\W+", " ", str(item.get("title") or "").casefold()).strip()
        return sha256(f"title:{title}|seller:{seller.casefold()}".encode()).hexdigest()[:16]

    @classmethod
    def _to_product(cls, item: dict, category_hint: str | None = None) -> ProductData | None:
        if is_sponsored(item):
            return None
        currency = detect_currency(item)
        current = price_to_cents(item.get("extracted_price", item.get("price")), currency)
        if not item.get("title") or current is None or current <= 0:
            return None
        typical = price_to_cents(item.get("extracted_old_price", item.get("old_price")), currency) or round(current * 1.1)
        try:
            rating = max(0, min(100, round(float(item.get("rating", 4)) * 20)))
        except (TypeError, ValueError):
            rating = 80
        raw_url = item.get("product_link") or item.get("link")
        canonical = normalize_url(raw_url) if raw_url else "https://shopping.google.com"
        seller = normalize_seller(item.get("source"))
        external_id = cls._identity(item, canonical if raw_url else "", seller)
        category = infer_category(str(item["title"]), str(item.get("category") or category_hint or ""))
        return ProductData(external_id, canonical, str(item["title"]).strip()[:240], category, seller, current, max(current, typical), rating, currency, item.get("thumbnail"))

    @classmethod
    def _products(cls, items: list[dict], category_hint: str | None = None) -> list[ProductData]:
        products, seen = [], set()
        for item in items:
            product = cls._to_product(item, category_hint)
            if product is None or product.external_id in seen:
                continue
            seen.add(product.external_id)
            products.append(product)
        return products

    def resolve(self, query: str) -> ProductData:
        products = self._products(self._search(query)[:20], query)
        if products:
            return products[0]
        raise ProviderError("SerpApi returned no priced products")

    def alternatives(self, product: ProductData) -> list[ProductData]:
        return [item for item in self._products(self._search(product.name)[:20], product.category) if item.external_id != product.external_id][:3]

    def current_price(self, external_id: str, fallback_cents: int) -> int:
        for product in self._products(self._search(external_id)[:20], None):
            if product.external_id == external_id:
                return product.current_price_cents
        return self.resolve(external_id).current_price_cents


class FallbackProductProvider:
    """Development/test fallback only; production callers must use the live provider."""

    def __init__(self, primary: ProductProvider, fallback: ProductProvider, allow_mock_fallback: bool = True):
        self.primary, self.fallback, self.allow_mock_fallback = primary, fallback, allow_mock_fallback

    def resolve(self, query: str) -> ProductData:
        try:
            return self.primary.resolve(query)
        except Exception as error:
            if self.allow_mock_fallback:
                return self.fallback.resolve(query)
            raise ProviderUnavailable("Live product data is unavailable") from error

    def alternatives(self, product: ProductData) -> list[ProductData]:
        try:
            alternatives = self.primary.alternatives(product)
            if alternatives or not self.allow_mock_fallback:
                return alternatives
            return self.fallback.alternatives(product)
        except Exception as error:
            if self.allow_mock_fallback:
                return self.fallback.alternatives(product)
            raise ProviderUnavailable("Live alternative data is unavailable") from error


class FallbackPriceProvider:
    """Development/test fallback only; production callers must use the live provider."""

    def __init__(self, primary: PriceProvider, fallback: PriceProvider, allow_mock_fallback: bool = True):
        self.primary, self.fallback, self.allow_mock_fallback = primary, fallback, allow_mock_fallback

    def current_price(self, external_id: str, fallback_cents: int) -> int:
        try:
            return self.primary.current_price(external_id, fallback_cents)
        except Exception as error:
            if self.allow_mock_fallback:
                return self.fallback.current_price(external_id, fallback_cents)
            raise ProviderUnavailable("Live price data is unavailable") from error


class PassthroughAffiliateProvider:
    def outbound_url(self, product_url: str) -> str:
        return product_url


class MockAffiliateProvider(PassthroughAffiliateProvider):
    """Local affiliate adapter; attribution is represented by the PICK click token."""


class InMemoryNotificationProvider:
    def deliver(self, user_id: int, title: str, body: str) -> None:
        return None


def build_runtime_providers(settings=None) -> tuple[ProductProvider, PriceProvider, AffiliateProvider]:
    """Select deterministic mocks only outside production."""
    settings = settings or get_settings()
    live_provider = SerpApiShoppingProvider(api_key=settings.serpapi_key)
    if settings.allows_mock_providers:
        return (
            FallbackProductProvider(live_provider, MockProductProvider(), allow_mock_fallback=True),
            FallbackPriceProvider(live_provider, MockPriceProvider(), allow_mock_fallback=True),
            MockAffiliateProvider(),
        )
    return live_provider, live_provider, PassthroughAffiliateProvider()


product_provider, price_provider, affiliate_provider = build_runtime_providers()
notification_provider: NotificationProvider = InMemoryNotificationProvider()
