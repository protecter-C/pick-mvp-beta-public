from dataclasses import dataclass
from .models import Verdict


@dataclass(frozen=True)
class ScoreInput:
    price_cents: int | None
    typical_price_cents: int | None
    budget_cents: int | None
    fit: int
    urgency: int
    quality: int


@dataclass(frozen=True)
class ScoreResult:
    verdict: Verdict
    score: int
    value: int
    fit: int
    timing: int
    evidence: list[str]
    confidence: float = 1.0


def _clamp(value: float) -> int:
    return max(0, min(100, round(value)))


def score_decision(data: ScoreInput) -> ScoreResult:
    valid_current = data.price_cents is not None and data.price_cents > 0
    valid_typical = data.typical_price_cents is not None and data.typical_price_cents > 0
    valid_budget = data.budget_cents is not None and data.budget_cents > 0
    price_conflict = valid_current and valid_typical and data.typical_price_cents < data.price_cents * 0.5
    confidence = 1.0 if valid_current and valid_typical and valid_budget and not price_conflict else 0.35
    current = data.price_cents if valid_current else 0
    typical = data.typical_price_cents if valid_typical else max(current, 1)
    budget = data.budget_cents if valid_budget else max(current, 1)
    discount = (typical - current) / max(typical, 1)
    value = _clamp(60 + discount * 160)
    affordability = _clamp(100 - max(0, current - budget) / max(budget, 1) * 180)
    timing = _clamp(data.urgency * 10 + discount * 100)
    fit = _clamp(data.fit * 10)
    quality = _clamp(data.quality)
    total = _clamp(value * 0.25 + affordability * 0.25 + fit * 0.25 + timing * 0.15 + quality * 0.10)

    if confidence < 0.5:
        verdict = Verdict.WAIT
    elif current > budget * 1.15 or fit < 45 or total < 50:
        verdict = Verdict.PASS
    elif total >= 72 and affordability >= 65 and fit >= 65:
        verdict = Verdict.BUY
    else:
        verdict = Verdict.WAIT

    evidence = [
        f"Price is {abs(round(discount * 100))}% {'below' if discount >= 0 else 'above'} the typical price.",
        f"Budget fit is {affordability}/100; item costs {round(current / max(budget, 1) * 100)}% of budget.",
        f"Preference fit is {fit}/100 and timing is {timing}/100.",
        f"Product quality signal is {quality}/100.",
    ]
    if confidence < 0.5:
        evidence.append("Price evidence is incomplete or conflicting; verdict is intentionally conservative.")
    return ScoreResult(verdict, total, value, fit, timing, evidence, confidence)


def choice_score(value: int, fit: int, timing: int, satisfaction: int | None) -> int:
    satisfaction_score = 50 if satisfaction is None else satisfaction * 10
    return _clamp(value * 0.30 + fit * 0.25 + timing * 0.20 + satisfaction_score * 0.25)
