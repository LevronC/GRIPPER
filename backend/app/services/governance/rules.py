"""
Deterministic IPS rule checks.

Portfolio model (see docs/COMPLIANCE_MODEL.md)
* Long-only, unleveraged: each holding carries an explicit weight, a fraction of total
  portfolio value in [0, 1]; weights sum to at most 1. Cash is implicit
  (1 - sum of weights) and is not subject to any rule. Gripper stores no prices or
  market values; weights are entered, not derived.
* Classification (sector, market-cap class) comes from the static TICKER_METADATA
  table. A ticker that is not in the table is UNCLASSIFIED. Rules that need the
  classification report "insufficient_data" for it instead of assuming compliance.

Arithmetic
* Weights and thresholds are stored as floats, but every comparison and sum here uses
  Decimal built from the float's shortest repr (Decimal(repr(0.1)) == Decimal("0.1")).
  This makes 0.1 + 0.2 equal exactly 0.3, so a portfolio exactly at a limit is
  compliant, as the rules state ("exceeds" means strictly greater).
* Non-finite values (NaN, +/-inf) raise InvalidPortfolioData; they never pass silently.
"""

from __future__ import annotations

import math
from decimal import Decimal
from typing import Any, Dict, List, Optional, Sequence

TICKER_METADATA: Dict[str, Dict[str, Any]] = {
    "AAPL": {"sector": "Technology", "market_cap_class": "mega"},
    "MSFT": {"sector": "Technology", "market_cap_class": "mega"},
    "NVDA": {"sector": "Technology", "market_cap_class": "mega"},
    "GOOGL": {"sector": "Communication Services", "market_cap_class": "mega"},
    "AMZN": {"sector": "Consumer Cyclical", "market_cap_class": "mega"},
    "META": {"sector": "Communication Services", "market_cap_class": "mega"},
    "TSLA": {"sector": "Consumer Cyclical", "market_cap_class": "large"},
    "XOM": {"sector": "Energy", "market_cap_class": "large"},
    "CVX": {"sector": "Energy", "market_cap_class": "large"},
    "JPM": {"sector": "Financials", "market_cap_class": "large"},
    "BAC": {"sector": "Financials", "market_cap_class": "large"},
    "JNJ": {"sector": "Healthcare", "market_cap_class": "large"},
    "LLY": {"sector": "Healthcare", "market_cap_class": "large"},
    # Synthetic micro-caps (fictional tickers) used by the demo seed and tests.
    "MCRT": {"sector": "Technology", "market_cap_class": "micro"},
    "GCAP": {"sector": "Financials", "market_cap_class": "micro"},
}

KNOWN_SECTORS = sorted({m["sector"] for m in TICKER_METADATA.values()})

# Severity bands: a breach is "critical" when the value exceeds threshold * multiplier.
SEVERITY_MULTIPLIER = {
    "single_position_cap": Decimal("1.2"),
    "sector_exposure_cap": Decimal("1.15"),
    "liquidity_constraint": Decimal("1.3"),
}


class InvalidPortfolioData(ValueError):
    """A weight or threshold is not a finite number in the supported range."""


def to_decimal(value: Any, what: str = "value") -> Decimal:
    if isinstance(value, Decimal):
        if not value.is_finite():
            raise InvalidPortfolioData(f"{what} must be finite")
        return value
    f = float(value)
    if not math.isfinite(f):
        raise InvalidPortfolioData(f"{what} must be finite (got {value!r})")
    return Decimal(repr(f))


def get_ticker_metadata(ticker: str) -> Optional[Dict[str, Any]]:
    """Sector and market-cap class, or None when the ticker is unclassified."""
    return TICKER_METADATA.get(ticker.upper().strip())


def normalize_threshold(threshold: Any) -> Decimal:
    """
    Legacy compatibility: rows created before the IPS rule API may store percentages
    (10.0 meaning 10%); values > 1 are divided by 100. The API only accepts fractions
    in (0, 1], so new rules are never ambiguous.
    """
    t = to_decimal(threshold, "threshold")
    if t <= 0:
        raise InvalidPortfolioData("threshold must be positive")
    return t / 100 if t > 1 else t


def _weight(h: Any) -> Decimal:
    w = to_decimal(h.weight, f"weight of {h.ticker}")
    if w < 0 or w > 1:
        raise InvalidPortfolioData(f"weight of {h.ticker} must be within [0, 1]")
    return w


def _pct(d: Decimal) -> str:
    return f"{float(d) * 100:.1f}%"


def _severity(rule_type: str, value: Decimal, threshold: Decimal) -> str:
    return "critical" if value > threshold * SEVERITY_MULTIPLIER[rule_type] else "warning"


def _insufficient(rule_type: str, tickers: List[str], needed: str) -> Dict[str, Any]:
    tickers = sorted(set(tickers))
    return {
        "type": "insufficient_data",
        "rule_type": rule_type,
        "tickers": tickers,
        "severity": "warning",
        "message": (
            f"Cannot fully evaluate {rule_type}: no {needed} classification for {', '.join(tickers)}. "
            "Compliance is not established for these holdings."
        ),
    }


def validate_single_position(holding: Any, threshold: Any) -> Optional[Dict[str, Any]]:
    """Breach when the holding's weight is strictly greater than the limit."""
    limit = normalize_threshold(threshold)
    weight = _weight(holding)
    if weight > limit:
        return {
            "type": "single_position_cap",
            "ticker": holding.ticker,
            "current_weight": float(weight),
            "threshold": float(limit),
            "severity": _severity("single_position_cap", weight, limit),
            "message": f"Position {holding.ticker} weight is {_pct(weight)}, exceeding the limit of {_pct(limit)}.",
        }
    return None


def validate_sector_exposures(
    holdings: Sequence[Any], threshold: Any, scope: Optional[str] = None
) -> List[Dict[str, Any]]:
    """
    Breach for each sector whose summed weight is strictly greater than the limit.
    scope=None applies the limit to every sector; scope="Technology" only to that one.
    Unclassified holdings could belong to any sector, so they produce an
    insufficient_data finding instead of being ignored.
    """
    limit = normalize_threshold(threshold)
    sector_weights: Dict[str, Decimal] = {}
    unclassified: List[str] = []
    for h in holdings:
        w = _weight(h)
        meta = get_ticker_metadata(h.ticker)
        if meta is None:
            if w > 0:
                unclassified.append(h.ticker)
            continue
        sector_weights[meta["sector"]] = sector_weights.get(meta["sector"], Decimal(0)) + w

    findings: List[Dict[str, Any]] = []
    for sector in sorted(sector_weights):
        if scope is not None and sector != scope:
            continue
        weight = sector_weights[sector]
        if weight > limit:
            findings.append({
                "type": "sector_exposure_cap",
                "sector": sector,
                "current_weight": float(weight),
                "threshold": float(limit),
                "severity": _severity("sector_exposure_cap", weight, limit),
                "message": f"Sector {sector} exposure is {_pct(weight)}, exceeding the limit of {_pct(limit)}.",
            })
    if unclassified:
        findings.append(_insufficient("sector_exposure_cap", unclassified, "sector"))
    return findings


def validate_liquidity_constraints(holdings: Sequence[Any], max_micro_cap_threshold: Any) -> List[Dict[str, Any]]:
    """Breach when the summed weight of micro-cap holdings is strictly greater than the limit."""
    limit = normalize_threshold(max_micro_cap_threshold)
    micro_weight = Decimal(0)
    micro_tickers: List[str] = []
    unclassified: List[str] = []
    for h in holdings:
        w = _weight(h)
        meta = get_ticker_metadata(h.ticker)
        if meta is None:
            if w > 0:
                unclassified.append(h.ticker)
        elif meta["market_cap_class"] == "micro":
            micro_weight += w
            micro_tickers.append(h.ticker)

    findings: List[Dict[str, Any]] = []
    if micro_weight > limit:
        micro_tickers = sorted(micro_tickers)
        findings.append({
            "type": "liquidity_constraint",
            "current_weight": float(micro_weight),
            "threshold": float(limit),
            "severity": _severity("liquidity_constraint", micro_weight, limit),
            "tickers": micro_tickers,
            "message": f"Micro-cap holdings ({', '.join(micro_tickers)}) total {_pct(micro_weight)}, exceeding the liquidity limit of {_pct(limit)}.",
        })
    if unclassified:
        findings.append(_insufficient("liquidity_constraint", unclassified, "market-cap"))
    return findings


def detect_violations(rules: Sequence[Any], holdings: Sequence[Any]) -> List[Dict[str, Any]]:
    """
    Pure, deterministic evaluation of active rules against holdings.

    Every applicable rule is evaluated independently; there is no precedence or
    override between rules. A holding that breaches a global 10% cap and a 5% cap
    scoped to its ticker produces two findings, one per rule. Output order is
    canonical (sorted), independent of rule and holding order.
    """
    findings: List[Dict[str, Any]] = []
    for rule in rules:
        scope = getattr(rule, "scope", None)
        if rule.rule_type == "single_position_cap":
            for h in holdings:
                if scope is not None and h.ticker.upper() != scope.upper():
                    continue
                v = validate_single_position(h, rule.threshold)
                if v:
                    v["holding_id"] = h.id
                    v["rule_id"] = rule.id
                    findings.append(v)
        elif rule.rule_type == "sector_exposure_cap":
            for v in validate_sector_exposures(holdings, rule.threshold, scope):
                v["rule_id"] = rule.id
                findings.append(v)
        elif rule.rule_type == "liquidity_constraint":
            for v in validate_liquidity_constraints(holdings, rule.threshold):
                v["rule_id"] = rule.id
                findings.append(v)
    findings.sort(key=lambda v: (str(v["rule_id"]), v["type"], v.get("ticker") or v.get("sector") or ""))
    return findings
