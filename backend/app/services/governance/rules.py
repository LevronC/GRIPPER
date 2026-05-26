from typing import Dict, Any, List, Optional

# Static repository of ticker metadata for compliance analysis.
# Maps ticker symbols to their sector and market capitalization class.
TICKER_METADATA: Dict[str, Dict[str, Any]] = {
    "AAPL": {"sector": "Technology", "market_cap_class": "mega", "market_cap_usd": 3000e9},
    "MSFT": {"sector": "Technology", "market_cap_class": "mega", "market_cap_usd": 3200e9},
    "NVDA": {"sector": "Technology", "market_cap_class": "mega", "market_cap_usd": 2200e9},
    "GOOGL": {"sector": "Communication Services", "market_cap_class": "mega", "market_cap_usd": 1800e9},
    "AMZN": {"sector": "Consumer Cyclical", "market_cap_class": "mega", "market_cap_usd": 1900e9},
    "META": {"sector": "Communication Services", "market_cap_class": "mega", "market_cap_usd": 1200e9},
    "TSLA": {"sector": "Consumer Cyclical", "market_cap_class": "large", "market_cap_usd": 550e9},
    "XOM": {"sector": "Energy", "market_cap_class": "large", "market_cap_usd": 480e9},
    "CVX": {"sector": "Energy", "market_cap_class": "large", "market_cap_usd": 290e9},
    "JPM": {"sector": "Financials", "market_cap_class": "large", "market_cap_usd": 580e9},
    "BAC": {"sector": "Financials", "market_cap_class": "large", "market_cap_usd": 350e9},
    "JNJ": {"sector": "Healthcare", "market_cap_class": "large", "market_cap_usd": 370e9},
    "LLY": {"sector": "Healthcare", "market_cap_class": "large", "market_cap_usd": 750e9},
    # Micro-caps for testing liquidity violations
    "MCRT": {"sector": "Technology", "market_cap_class": "micro", "market_cap_usd": 120e6},
    "GCAP": {"sector": "Financials", "market_cap_class": "micro", "market_cap_usd": 85e6},
}

def get_ticker_metadata(ticker: str) -> Dict[str, Any]:
    """
    Returns sector and market cap classification for a ticker symbol.
    Defaults to Technology / mega-cap for unknown symbols.
    """
    upper_ticker = ticker.upper().strip()
    return TICKER_METADATA.get(upper_ticker, {
        "sector": "Other",
        "market_cap_class": "large",
        "market_cap_usd": 10e9
    })

def normalize_threshold(threshold: float) -> float:
    """
    Ensures thresholds are consistently represented as decimals.
    E.g. both 10.0 (10%) and 0.10 (10%) map to 0.10.
    """
    if threshold > 1.0:
        return threshold / 100.0
    return threshold

def validate_single_position(holding: Any, threshold: float) -> Optional[Dict[str, Any]]:
    """
    Checks if a single holding exceeds the max weight limit.
    """
    norm_threshold = normalize_threshold(threshold)
    if holding.weight > norm_threshold:
        return {
            "type": "single_position_cap",
            "ticker": holding.ticker,
            "current_weight": holding.weight,
            "threshold": norm_threshold,
            "severity": "critical" if holding.weight > norm_threshold * 1.2 else "warning",
            "message": f"Position {holding.ticker} weight is {holding.weight*100:.1f}%, exceeding the limit of {norm_threshold*100:.1f}%."
        }
    return None

def validate_sector_exposures(holdings: List[Any], threshold: float) -> List[Dict[str, Any]]:
    """
    Checks if combined portfolio weights in any sector exceed the limit.
    """
    norm_threshold = normalize_threshold(threshold)
    sector_weights: Dict[str, float] = {}
    
    for h in holdings:
        meta = get_ticker_metadata(h.ticker)
        sector = meta["sector"]
        sector_weights[sector] = sector_weights.get(sector, 0.0) + h.weight
        
    violations = []
    for sector, weight in sector_weights.items():
        if weight > norm_threshold:
            violations.append({
                "type": "sector_exposure_cap",
                "sector": sector,
                "current_weight": weight,
                "threshold": norm_threshold,
                "severity": "critical" if weight > norm_threshold * 1.15 else "warning",
                "message": f"Sector {sector} exposure is {weight*100:.1f}%, exceeding the limit of {norm_threshold*100:.1f}%."
            })
            
    return violations

def validate_liquidity_constraints(holdings: List[Any], max_micro_cap_threshold: float) -> Optional[Dict[str, Any]]:
    """
    Ensures combined weight in highly illiquid micro-cap stocks does not exceed limits.
    """
    norm_threshold = normalize_threshold(max_micro_cap_threshold)
    micro_cap_weight = 0.0
    micro_tickers = []
    
    for h in holdings:
        meta = get_ticker_metadata(h.ticker)
        if meta["market_cap_class"] == "micro":
            micro_cap_weight += h.weight
            micro_tickers.append(h.ticker)
            
    if micro_cap_weight > norm_threshold:
        return {
            "type": "liquidity_constraint",
            "current_weight": micro_cap_weight,
            "threshold": norm_threshold,
            "severity": "critical" if micro_cap_weight > norm_threshold * 1.3 else "warning",
            "tickers": micro_tickers,
            "message": f"Micro-cap holdings {micro_tickers} combined weight is {micro_cap_weight*100:.1f}%, exceeding liquidity limit of {norm_threshold*100:.1f}%."
        }
    return None
