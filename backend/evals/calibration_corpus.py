"""
Separate relevance-calibration corpus. Not the Phase 4 42-query set.

Labels were assigned from the text while this file was written. Calibration
queries and held-out queries use different topic families so a threshold fit
on one family is not the same notes as the other. Synthetic labels are not
independent expert annotations.

The threshold is chosen only from `split == "calibration"`. Held-out queries
are scored once after the cutoff is frozen.
"""

from __future__ import annotations

from typing import Any

DOCUMENTS: list[dict[str, Any]] = [
    {"id": "ship-rates", "family": "shipping", "company": "Keel Line", "sector": "Industrials",
     "text": "Keel Line reports container freight rates on the Pacific lane and how blank sailings tightened capacity."},
    {"id": "ship-fuel", "family": "shipping", "company": "Keel Line", "sector": "Industrials",
     "text": "A Keel Line note covers bunker fuel cost and the scrubber surcharge, not freight rates."},
    {"id": "ins-combined", "family": "insurance", "company": "Harbor Mutual", "sector": "Financials",
     "text": "Harbor Mutual's combined ratio deteriorated because catastrophe losses exceeded premiums."},
    {"id": "ins-life", "family": "insurance", "company": "Harbor Mutual", "sector": "Financials",
     "text": "Harbor Mutual's life segment discusses surrender rates and crediting rates on annuities."},
    {"id": "ag-corn", "family": "agriculture", "company": "Fieldward", "sector": "Consumer",
     "text": "Fieldward describes corn yield per acre and the cash price at the elevator."},
    {"id": "ag-fert", "family": "agriculture", "company": "Fieldward", "sector": "Consumer",
     "text": "Fieldward's input note is about nitrogen fertilizer cost, not grain prices."},
    {"id": "muni-go", "family": "municipal", "company": "Civic Paper", "sector": "Financials",
     "text": "Civic Paper summarizes a general-obligation bond coupon and the city's tax pledge."},
    {"id": "muni-rev", "family": "municipal", "company": "Civic Paper", "sector": "Financials",
     "text": "A different Civic Paper note covers a toll-road revenue bond, not a general-obligation pledge."},
    {"id": "mine-copper", "family": "mining", "company": "Redseam Mining", "sector": "Materials",
     "text": "Redseam Mining reports copper grade and cash cost per pound at the open pit."},
    {"id": "mine-gold", "family": "mining", "company": "Redseam Mining", "sector": "Materials",
     "text": "Redseam's gold appendix discusses all-in sustaining cost, not the copper pit."},
    {"id": "tel-arpu", "family": "telecom", "company": "Wirelane", "sector": "Communication",
     "text": "Wirelane reports postpaid ARPU and churn after a handset promotion."},
    {"id": "tel-fiber", "family": "telecom", "company": "Wirelane", "sector": "Communication",
     "text": "Wirelane's network note counts fiber homes passed and build cost per home."},
    {"id": "air-load", "family": "airlines", "company": "North Cabin Air", "sector": "Industrials",
     "text": "North Cabin Air reports passenger load factor and yield per revenue passenger mile."},
    {"id": "air-fuel", "family": "airlines", "company": "North Cabin Air", "sector": "Industrials",
     "text": "North Cabin Air's fuel hedge note explains collar contracts, not ticket yield."},
    {"id": "water-rate", "family": "utilities", "company": "Clearbend Water", "sector": "Utilities",
     "text": "Clearbend Water was granted a rate increase by the utility commission to fund pipe replacement."},
    {"id": "water-lead", "family": "utilities", "company": "Clearbend Water", "sector": "Utilities",
     "text": "Clearbend's compliance note inventories lead service lines, not the allowed return."},
]

QUERIES: list[dict[str, Any]] = [
    {"id": "c01", "split": "calibration", "category": "exact", "text": "container freight rates Pacific blank sailings", "relevant": ["ship-rates"]},
    {"id": "c02", "split": "calibration", "category": "paraphrase", "text": "Are ships skipping departures so the price to move boxes across the ocean rose?", "relevant": ["ship-rates"]},
    {"id": "c03", "split": "calibration", "category": "confusable", "text": "bunker fuel cost", "relevant": ["ship-fuel"]},
    {"id": "c04", "split": "calibration", "category": "exact", "text": "combined ratio catastrophe losses", "relevant": ["ins-combined"]},
    {"id": "c05", "split": "calibration", "category": "paraphrase", "text": "Did disaster claims cost more than the premiums the insurer collected?", "relevant": ["ins-combined"]},
    {"id": "c06", "split": "calibration", "category": "confusable", "text": "annuity crediting rates", "relevant": ["ins-life"]},
    {"id": "c07", "split": "calibration", "category": "exact", "text": "corn yield per acre elevator price", "relevant": ["ag-corn"]},
    {"id": "c08", "split": "calibration", "category": "paraphrase", "text": "How many bushels of grain came off each acre, and what did the buyer pay?", "relevant": ["ag-corn"]},
    {"id": "c09", "split": "calibration", "category": "confusable", "text": "nitrogen fertilizer cost", "relevant": ["ag-fert"]},
    {"id": "c10", "split": "calibration", "category": "exact", "text": "general obligation bond coupon tax pledge", "relevant": ["muni-go"]},
    {"id": "c11", "split": "calibration", "category": "confusable", "text": "toll road revenue bond", "relevant": ["muni-rev"]},
    {"id": "c12", "split": "calibration", "category": "hard_negative", "text": "cryptocurrency staking yield on the shipping notes", "relevant": []},
    {"id": "c13", "split": "calibration", "category": "unanswerable", "text": "semiconductor export license", "relevant": []},
    {"id": "c14", "split": "calibration", "category": "multi", "text": "Harbor Mutual insurance results", "relevant": ["ins-combined", "ins-life"]},
    {"id": "h01", "split": "heldout", "category": "exact", "text": "copper grade cash cost per pound", "relevant": ["mine-copper"]},
    {"id": "h02", "split": "heldout", "category": "paraphrase", "text": "How rich is the ore and what does it cost to produce a pound of the red metal?", "relevant": ["mine-copper"]},
    {"id": "h03", "split": "heldout", "category": "confusable", "text": "gold all-in sustaining cost", "relevant": ["mine-gold"]},
    {"id": "h04", "split": "heldout", "category": "exact", "text": "postpaid ARPU churn handset", "relevant": ["tel-arpu"]},
    {"id": "h05", "split": "heldout", "category": "paraphrase", "text": "How much revenue does each phone subscriber bring, and how many left?", "relevant": ["tel-arpu"]},
    {"id": "h06", "split": "heldout", "category": "confusable", "text": "fiber homes passed build cost", "relevant": ["tel-fiber"]},
    {"id": "h07", "split": "heldout", "category": "exact", "text": "passenger load factor yield per mile", "relevant": ["air-load"]},
    {"id": "h08", "split": "heldout", "category": "paraphrase", "text": "Were the seats full, and what did the airline earn per passenger mile?", "relevant": ["air-load"]},
    {"id": "h09", "split": "heldout", "category": "confusable", "text": "fuel hedge collar", "relevant": ["air-fuel"]},
    {"id": "h10", "split": "heldout", "category": "exact", "text": "utility commission rate increase pipe replacement", "relevant": ["water-rate"]},
    {"id": "h11", "split": "heldout", "category": "confusable", "text": "lead service lines", "relevant": ["water-lead"]},
    {"id": "h12", "split": "heldout", "category": "unanswerable", "text": "private equity carried interest", "relevant": []},
    {"id": "h13", "split": "heldout", "category": "hard_negative", "text": "municipal bond coupon in the mining notes", "relevant": []},
    {"id": "h14", "split": "heldout", "category": "multi", "text": "North Cabin Air costs and ticket revenue", "relevant": ["air-load", "air-fuel"]},
]


def validate_calibration_corpus() -> None:
    ids = [doc["id"] for doc in DOCUMENTS]
    if len(ids) != len(set(ids)):
        raise ValueError("duplicate document id")
    families = {doc["family"] for doc in DOCUMENTS}
    cal_families = set()
    hold_families = set()
    known = set(ids)
    for query in QUERIES:
        if query["split"] == "calibration":
            cal_families.update(doc["family"] for doc in DOCUMENTS if doc["id"] in query["relevant"])
        elif query["split"] == "heldout":
            hold_families.update(doc["family"] for doc in DOCUMENTS if doc["id"] in query["relevant"])
        else:
            raise ValueError(query["id"])
        missing = [doc_id for doc_id in query["relevant"] if doc_id not in known]
        if missing:
            raise ValueError(f"{query['id']} cites {missing}")
    if cal_families & hold_families:
        raise ValueError(f"topic families overlap splits: {cal_families & hold_families}")
    if not cal_families or not hold_families:
        raise ValueError("both splits need labeled topics")
    unused = families - cal_families - hold_families
    if unused:
        raise ValueError(f"documents in unused families: {unused}")
