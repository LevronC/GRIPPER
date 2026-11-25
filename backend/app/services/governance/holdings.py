"""Validation shared by saved and simulated holdings."""

from __future__ import annotations

from typing import Iterable

from fastapi import HTTPException

WEIGHT_TOLERANCE = 1e-9


def validate_holdings_set(tickers: Iterable[str], weights: Iterable[float]) -> None:
    """Unique tickers (case-insensitive) and a total weight of at most 100%."""
    upper = [t.upper() for t in tickers]
    if len(set(upper)) != len(upper):
        raise HTTPException(status_code=422, detail="Duplicate tickers in holdings.")
    if sum(weights) > 1.0 + WEIGHT_TOLERANCE:
        raise HTTPException(status_code=422, detail="Total holdings weight exceeds 100%.")
