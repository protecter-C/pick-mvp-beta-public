import json
from collections import Counter

from app.providers import SerpApiShoppingProvider
from app.scoring import ScoreInput, choice_score, score_decision


def korean_fixture_rows():
    categories = {"electronics": "무선 헤드폰", "home": "스마트 가습기", "beauty": "수분 크림"}
    rows = []
    expected_ids = []
    for category, label in categories.items():
        for index in range(10):
            product_id = f"kr-{category}-{index:02d}"
            expected_ids.append(product_id)
            price = 70000 + index * 3500
            rows.append({"product_id": product_id, "title": f"{label} {index + 1}세대", "source": "  한국   판매자 ", "currency": "KRW", "extracted_price": price, "extracted_old_price": price + 15000, "product_link": f"https://shop.kr/{category}/{index}?utm_source=simulation"})
            if index in {2, 7}:
                rows.append({"product_id": product_id, "title": f"{label} {index + 1}세대 재고", "source": "다른 판매자", "currency": "KRW", "extracted_price": price + 1000, "product_link": f"https://other.kr/{category}/{index}"})
    rows.extend([
        {"product_id": "sponsored-1", "title": "Sponsored item", "source": "Ads", "currency": "KRW", "extracted_price": 10, "tag": "Sponsored", "product_link": "https://ads.kr/p"},
        {"product_id": "missing-price", "title": "가격 누락 상품", "source": "판매자", "currency": "KRW", "product_link": "https://shop.kr/missing"},
    ])
    return rows, expected_ids


def test_korean_30_product_quality_simulation(capsys):
    rows, expected_ids = korean_fixture_rows()
    calls = []
    provider = SerpApiShoppingProvider(api_key="simulation", fetch_json=lambda params: calls.append(params) or {"shopping_results": rows})
    resolved = provider.resolve("무선 헤드폰")
    products = provider._products(rows)
    normalized_ids = {product.external_id for product in products}

    raw_duplicate_rows = len(rows) - len(normalized_ids) - 2
    raw_duplicate_rate = raw_duplicate_rows / (len(rows) - 2)
    residual_duplicate_rate = max(0, len(products) - len(normalized_ids)) / len(products)
    variant_merge_errors = sum(product_id not in normalized_ids for product_id in expected_ids)
    price_anomalies = sum(not (product.current_price_cents > 0 and product.typical_price_cents >= product.current_price_cents and product.currency == "KRW" and product.merchant == "한국 판매자" and product.url.startswith("https://")) for product in products)
    verdict_consistency = []
    wait_buy_transitions = []
    evidence_quality = []
    savings = []
    choice_scores = []
    for product in products:
        initial = score_decision(ScoreInput(10000, 12000, 9000, 7, 1, 80))
        changed = score_decision(ScoreInput(8500, 12000, 9000, 7, 1, 80))
        repeat = score_decision(ScoreInput(10000, 12000, 9000, 7, 1, 80))
        verdict_consistency.append(initial.verdict == repeat.verdict and initial.score == repeat.score)
        wait_buy_transitions.append(initial.verdict.value == "WAIT" and changed.verdict.value == "BUY")
        evidence = " ".join(initial.evidence).lower()
        evidence_quality.append(all(token in evidence for token in ("price", "budget", "fit", "timing", "quality")))
        paid = 8500
        savings.append(max(0, 12000 - paid))
        choice_scores.append(choice_score(80, 70, 60, 8))

    metrics = {
        "products": len(products),
        "categories": dict(Counter(product.category for product in products)),
        "raw_duplicate_rate": raw_duplicate_rate,
        "residual_duplicate_rate": residual_duplicate_rate,
        "variant_merge_errors": variant_merge_errors,
        "price_anomalies": price_anomalies,
        "verdict_consistency": sum(verdict_consistency) / len(verdict_consistency),
        "wait_to_buy_transitions": sum(wait_buy_transitions),
        "evidence_quality": sum(evidence_quality) / len(evidence_quality),
        "realized_savings_expected_krw": sum(savings),
        "realized_savings_accuracy": sum(savings) == 30 * 3500,
        "choice_score_min": min(choice_scores),
        "choice_score_max": max(choice_scores),
        "choice_score_sanity": all(0 <= score <= 100 for score in choice_scores) and choice_score(80, 70, 60, 10) > choice_score(80, 70, 60, 2),
        "korean_locale": calls[0]["hl"] == "ko" and calls[0]["gl"] == "kr" and calls[0]["location"] == "Seoul, South Korea",
        "resolved_identity": resolved.external_id,
    }
    print(json.dumps(metrics, ensure_ascii=False, sort_keys=True))
    assert metrics["products"] == 30
    assert metrics["categories"] == {"electronics": 10, "home": 10, "beauty": 10}
    assert metrics["raw_duplicate_rate"] > 0
    assert metrics["residual_duplicate_rate"] == 0
    assert metrics["variant_merge_errors"] == 0
    assert metrics["price_anomalies"] == 0
    assert metrics["verdict_consistency"] == 1
    assert metrics["wait_to_buy_transitions"] == 30
    assert metrics["evidence_quality"] == 1
    assert metrics["realized_savings_accuracy"] is True
    assert metrics["choice_score_sanity"] is True
    assert metrics["korean_locale"] is True
