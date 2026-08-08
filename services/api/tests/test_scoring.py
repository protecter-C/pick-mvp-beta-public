from app.models import Verdict
from app.scoring import ScoreInput, choice_score, score_decision


def test_buy_when_affordable_good_fit_and_discounted():
    result = score_decision(ScoreInput(8000, 10000, 12000, 9, 8, 90))
    assert result.verdict == Verdict.BUY
    assert result.score >= 72
    assert len(result.evidence) == 4


def test_pass_when_over_budget_even_with_quality():
    result = score_decision(ScoreInput(20000, 18000, 10000, 8, 8, 95))
    assert result.verdict == Verdict.PASS


def test_choice_score_is_bounded_and_satisfaction_matters():
    assert choice_score(80, 80, 80, 10) > choice_score(80, 80, 80, 2)
    assert 0 <= choice_score(100, 100, 100, 10) <= 100


def test_choice_score_has_real_variance_across_dimensions():
    scores = {
        choice_score(95, 95, 95, 10),
        choice_score(60, 95, 95, 10),
        choice_score(95, 60, 95, 10),
        choice_score(95, 95, 60, 10),
        choice_score(95, 95, 95, 2),
    }
    assert len(scores) == 5
    assert min(scores) < 80 < max(scores)


def test_low_confidence_prices_are_conservative_and_explain_uncertainty():
    missing = score_decision(ScoreInput(None, 12000, 10000, 9, 8, 90))
    conflicting = score_decision(ScoreInput(10000, 4000, 10000, 9, 8, 90))
    for result in (missing, conflicting):
        assert result.verdict == Verdict.WAIT
        assert result.confidence < 0.5
        assert any("incomplete or conflicting" in line for line in result.evidence)
