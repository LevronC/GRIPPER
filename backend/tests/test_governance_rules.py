"""
Governance rule correctness (pure functions, no database).

"Exceeds" means strictly greater than the limit. Boundaries use decimal arithmetic on the
float's shortest repr, so values that are equal in decimal (0.1 + 0.2 vs 0.3) are equal.
"""

from __future__ import annotations

import math
import random
import uuid
from types import SimpleNamespace

import pytest

from app.services.governance.rules import (
    InvalidPortfolioData,
    detect_violations,
    normalize_threshold,
    validate_liquidity_constraints,
    validate_sector_exposures,
    validate_single_position,
)


def H(ticker, weight):
    return SimpleNamespace(id=uuid.uuid4(), ticker=ticker, weight=weight)


def R(rule_type, threshold, scope=None):
    return SimpleNamespace(id=uuid.uuid4(), rule_type=rule_type, threshold=threshold, scope=scope)


def types(findings):
    return sorted((f["type"], f.get("ticker") or f.get("sector") or "") for f in findings)


# ── Single-position cap ──────────────────────────────────────────────────────

@pytest.mark.parametrize("weight, breached", [
    (0.05, False),          # clearly passing
    (0.0999999, False),     # just below
    (0.10, False),          # exactly at the limit: not a breach
    (0.1000001, True),      # just above
    (0.25, True),           # clearly violating
    (0.0, False),           # zero weight
])
def test_single_position_boundaries(weight, breached):
    assert (validate_single_position(H("NVDA", weight), 0.10) is not None) is breached


def test_single_position_reports_values():
    v = validate_single_position(H("NVDA", 0.14), 0.10)
    assert (v["current_weight"], v["threshold"], v["ticker"]) == (0.14, 0.10, "NVDA")
    assert v["message"] == "Position NVDA weight is 14.0%, exceeding the limit of 10.0%."


# ── Sector cap ───────────────────────────────────────────────────────────────

def test_sector_exactly_at_limit_via_float_sum_is_not_a_breach():
    """Regression: 0.1 + 0.2 == 0.30000000000000004 in binary floats used to breach a 30% cap."""
    assert validate_sector_exposures([H("AAPL", 0.1), H("MSFT", 0.2)], 0.30) == []


@pytest.mark.parametrize("extra, breached", [(0.0999999, False), (0.10, False), (0.1000001, True)])
def test_sector_boundaries(extra, breached):
    findings = validate_sector_exposures([H("AAPL", 0.2), H("NVDA", extra)], 0.30)
    assert bool(findings) is breached


def test_sector_sums_only_within_sector_and_reports_each_breach():
    hs = [H("AAPL", 0.2), H("MSFT", 0.15), H("XOM", 0.2), H("CVX", 0.15), H("JPM", 0.1)]
    findings = validate_sector_exposures(hs, 0.30)
    assert types(findings) == [("sector_exposure_cap", "Energy"), ("sector_exposure_cap", "Technology")]
    tech = next(f for f in findings if f["sector"] == "Technology")
    assert tech["current_weight"] == 0.35


def test_scoped_sector_rule_only_checks_its_sector():
    hs = [H("AAPL", 0.35), H("XOM", 0.35)]
    assert types(validate_sector_exposures(hs, 0.30, scope="Energy")) == [("sector_exposure_cap", "Energy")]


# ── Liquidity ────────────────────────────────────────────────────────────────

@pytest.mark.parametrize("weights, breached", [
    ((0.02, 0.02), False),
    ((0.02, 0.03), False),            # exactly 5%
    ((0.02, 0.0300001), True),
    ((0.04, 0.04), True),
])
def test_liquidity_boundaries(weights, breached):
    findings = validate_liquidity_constraints([H("MCRT", weights[0]), H("GCAP", weights[1]), H("AAPL", 0.5)], 0.05)
    assert any(f["type"] == "liquidity_constraint" for f in findings) is breached


def test_liquidity_tickers_are_sorted_and_reported():
    [f] = validate_liquidity_constraints([H("MCRT", 0.04), H("GCAP", 0.04)], 0.05)
    assert f["tickers"] == ["GCAP", "MCRT"] and f["current_weight"] == 0.08


# ── Missing information is never evidence of compliance ──────────────────────

def test_unclassified_ticker_is_insufficient_data_not_compliant():
    """Regression: an unknown ticker used to default to 'large-cap', passing the liquidity rule."""
    findings = validate_liquidity_constraints([H("ZZZZ", 0.5)], 0.05)
    assert types(findings) == [("insufficient_data", "")]
    assert findings[0]["tickers"] == ["ZZZZ"] and findings[0]["rule_type"] == "liquidity_constraint"
    sector = validate_sector_exposures([H("ZZZZ", 0.5), H("AAPL", 0.1)], 0.30)
    assert types(sector) == [("insufficient_data", "")]


def test_unclassified_with_zero_weight_needs_no_classification():
    assert validate_liquidity_constraints([H("ZZZZ", 0.0)], 0.05) == []


def test_single_position_rule_does_not_need_classification():
    assert validate_single_position(H("ZZZZ", 0.5), 0.10)["ticker"] == "ZZZZ"


def test_known_breach_and_insufficient_data_are_both_reported():
    findings = validate_liquidity_constraints([H("MCRT", 0.06), H("ZZZZ", 0.1)], 0.05)
    assert types(findings) == [("insufficient_data", ""), ("liquidity_constraint", "")]


# ── Empty / zero portfolios ──────────────────────────────────────────────────

@pytest.mark.parametrize("holdings", [[], [H("AAPL", 0.0), H("MCRT", 0.0)]])
def test_empty_and_zero_value_portfolios_have_no_findings(holdings):
    rules = [R("single_position_cap", 0.1), R("sector_exposure_cap", 0.3), R("liquidity_constraint", 0.05)]
    assert detect_violations(rules, holdings) == []


# ── Invalid numbers are rejected, never treated as compliant ─────────────────

@pytest.mark.parametrize("weight", [math.nan, math.inf, -math.inf, -0.01, 1.01])
def test_invalid_weights_raise(weight):
    with pytest.raises(InvalidPortfolioData):
        validate_single_position(H("AAPL", weight), 0.10)
    with pytest.raises(InvalidPortfolioData):
        validate_sector_exposures([H("AAPL", weight)], 0.30)
    with pytest.raises(InvalidPortfolioData):
        validate_liquidity_constraints([H("MCRT", weight)], 0.05)


@pytest.mark.parametrize("threshold", [0, -0.1, math.nan, math.inf])
def test_invalid_thresholds_raise(threshold):
    with pytest.raises(InvalidPortfolioData):
        normalize_threshold(threshold)


def test_legacy_percentage_thresholds_are_normalised():
    assert normalize_threshold(10.0) == normalize_threshold(0.10)
    assert validate_single_position(H("AAPL", 0.10), 10.0) is None
    assert validate_single_position(H("AAPL", 0.11), 10.0) is not None


# ── Severity bands ───────────────────────────────────────────────────────────

@pytest.mark.parametrize("weight, severity", [(0.11, "warning"), (0.12, "warning"), (0.1200001, "critical")])
def test_single_position_severity_band_is_exact(weight, severity):
    """critical iff weight > 1.2 x limit; 0.12 vs 10% is exactly 1.2x (was misclassified by float error)."""
    assert validate_single_position(H("AAPL", weight), 0.10)["severity"] == severity


# ── Multiple rules of the same type ──────────────────────────────────────────

def test_scoped_and_global_position_rules_evaluate_independently():
    glob, nvda = R("single_position_cap", 0.10), R("single_position_cap", 0.05, scope="NVDA")
    def by_rule(hs):
        return sorted((str(f["rule_id"]) == str(glob.id), f["ticker"]) for f in detect_violations([glob, nvda], hs))
    assert by_rule([H("NVDA", 0.08), H("AAPL", 0.08)]) == [(False, "NVDA")]          # only the scoped rule
    assert by_rule([H("NVDA", 0.12)]) == [(False, "NVDA"), (True, "NVDA")]           # both rules, two findings
    assert by_rule([H("AAPL", 0.12)]) == [(True, "AAPL")]                            # scope does not apply


def test_multiple_sector_rules():
    rules = [R("sector_exposure_cap", 0.30, "Technology"), R("sector_exposure_cap", 0.15, "Energy"),
             R("sector_exposure_cap", 0.40)]
    hs = [H("AAPL", 0.31), H("XOM", 0.16), H("JPM", 0.41)]
    got = sorted((f["sector"], f["threshold"]) for f in detect_violations(rules, hs))
    assert got == [("Energy", 0.15), ("Financials", 0.40), ("Technology", 0.30)]


# ── Determinism ──────────────────────────────────────────────────────────────

def _canonical(findings):
    return [(str(f["rule_id"]), f["type"], f.get("ticker") or f.get("sector") or "", f["current_weight"] if "current_weight" in f else None,
             f["severity"]) for f in findings]


def test_detection_is_order_independent_and_repeatable():
    """Seeded randomized check: shuffling holdings and rules never changes the outcome."""
    rng = random.Random(20261125)
    tickers = ["AAPL", "MSFT", "NVDA", "MCRT", "GCAP", "XOM", "CVX", "JPM", "BAC", "JNJ", "LLY", "ZZZZ"]
    for _ in range(300):
        chosen = rng.sample(tickers, rng.randint(1, len(tickers)))
        raw = [rng.choice([0.0, 0.01, 0.05, 0.1, 0.2, 0.3]) + rng.randint(0, 3) * 0.01 for _ in chosen]
        total = sum(raw) or 1.0
        hs = [H(t, round(w / total * rng.choice([0.5, 0.9, 1.0]), 6)) for t, w in zip(chosen, raw)]
        rules = [R("single_position_cap", 0.1), R("sector_exposure_cap", 0.3),
                 R("liquidity_constraint", 0.05), R("single_position_cap", 0.05, scope="NVDA")]
        baseline = _canonical(detect_violations(rules, hs))
        for _ in range(3):
            assert _canonical(detect_violations(rng.sample(rules, len(rules)), rng.sample(hs, len(hs)))) == baseline
