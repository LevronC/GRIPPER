"""
Labeled synthetic research corpus for retrieval evaluation.

Every relevance label was assigned from the text while this file was written,
before any retriever was run against it. Do not edit a label to match a score.

Each document is one chunk. Queries name document ids, not chunk ids. The
evaluation script maps those ids onto the rows it inserts.

Paraphrase queries are written to avoid the distinctive words of the relevant
note, so a lexical retriever can miss them. Confusable queries share words with
a distractor that is not relevant. Unanswerable queries have an empty label.
"""

from __future__ import annotations

from typing import Any

DOCUMENTS: list[dict[str, Any]] = [
    {
        "id": "tech-gpu",
        "company": "Northline Silicon",
        "sector": "Technology",
        "text": (
            "Northline Silicon sells graphics processors to operators of large model-training clusters. "
            "Management said orders for those accelerators remain the main source of revenue growth, "
            "and that lead times for the newest boards are still stretching."
        ),
    },
    {
        "id": "tech-cpu",
        "company": "Harbor Compute",
        "sector": "Technology",
        "text": (
            "Harbor Compute makes server central processors for enterprise database machines. "
            "The note discusses socket share in traditional data-center servers and says accelerator "
            "attach rates are not part of this product line."
        ),
    },
    {
        "id": "tech-saas",
        "company": "Ledgerlane Software",
        "sector": "Technology",
        "text": (
            "Ledgerlane Software reports gross retention and net revenue retention for its application "
            "subscriptions. Customers expand seats in the accounting suite; the note does not discuss "
            "security products."
        ),
    },
    {
        "id": "tech-cyber",
        "company": "Brakeline Security",
        "sector": "Technology",
        "text": (
            "Brakeline Security sells endpoint detection subscriptions. Annual recurring revenue and "
            "logo churn are the figures in the note, which covers malware catching on employee laptops."
        ),
    },
    {
        "id": "tech-cloud",
        "company": "Kiln Hosting",
        "sector": "Technology",
        "text": (
            "Kiln Hosting rents infrastructure capacity. The note focuses on capital intensity and "
            "remaining performance obligations, meaning contracted capacity that has not yet been "
            "recognized as revenue."
        ),
    },
    {
        "id": "energy-refinery",
        "company": "Redwharf Refining",
        "sector": "Energy",
        "text": (
            "Redwharf Refining will raise capital expenditure to build new refineries next year. "
            "The projects add crude-processing units. The note does not discuss dividends."
        ),
    },
    {
        "id": "energy-return",
        "company": "Redwharf Refining",
        "sector": "Energy",
        "text": (
            "The board approved a capital return through dividends and buybacks. Cash is being sent "
            "back to shareholders rather than invested in new plants."
        ),
    },
    {
        "id": "energy-solar",
        "company": "Plainfield Power",
        "sector": "Energy",
        "text": (
            "Plainfield Power is adding utility-scale photovoltaic capacity and signing power-purchase "
            "agreements for those solar farms."
        ),
    },
    {
        "id": "energy-wind",
        "company": "Plainfield Power",
        "sector": "Energy",
        "text": (
            "Plainfield Power wrote down offshore wind leases after higher interest rates. The note "
            "is about impairments on those marine turbines, not about solar farms."
        ),
    },
    {
        "id": "energy-lng",
        "company": "Cove Export",
        "sector": "Energy",
        "text": (
            "Cove Export reports liquefied natural gas export terminal utilization. The facility ran "
            "close to its nameplate capacity during the quarter."
        ),
    },
    {
        "id": "health-glp-price",
        "company": "Marlow Therapeutics",
        "sector": "Healthcare",
        "text": (
            "Marlow Therapeutics discusses the list price of its injected GLP-1 obesity drug and how "
            "many insurers still cover that injection."
        ),
    },
    {
        "id": "health-glp-trial",
        "company": "Marlow Therapeutics",
        "sector": "Healthcare",
        "text": (
            "A separate Marlow note covers the phase-3 trial of an oral GLP-1 candidate. It reports "
            "enrollment and endpoints, not a commercial list price."
        ),
    },
    {
        "id": "health-device",
        "company": "Suture Street",
        "sector": "Healthcare",
        "text": (
            "Suture Street reports cardiac stent volumes and hospital purchasing of those tubes used "
            "to prop open heart arteries."
        ),
    },
    {
        "id": "health-biosim",
        "company": "Oldwell Biologics",
        "sector": "Healthcare",
        "text": (
            "Oldwell Biologics describes biosimilar erosion of a legacy antibody franchise. Discounts "
            "are pulling down the price of that older drug."
        ),
    },
    {
        "id": "fin-nim",
        "company": "Eastbridge Bank",
        "sector": "Financials",
        "text": (
            "Eastbridge Bank's net interest margin moved with its deposit beta. Savings accounts "
            "are repricing faster than the loan book."
        ),
    },
    {
        "id": "fin-card",
        "company": "Eastbridge Bank",
        "sector": "Financials",
        "text": (
            "The card subsidiary reports the net charge-off rate on credit-card balances and a "
            "reserve build for those expected credit losses."
        ),
    },
    {
        "id": "fin-aum",
        "company": "North Ledger Asset Management",
        "sector": "Financials",
        "text": (
            "North Ledger charges a management fee rate on assets under management and describes "
            "client flows into its funds."
        ),
    },
    {
        "id": "fin-broker",
        "company": "Ticketlane Markets",
        "sector": "Financials",
        "text": (
            "Ticketlane Markets receives payment for order flow and reports retail trading volume. "
            "Venues pay the broker for sending small-investor orders."
        ),
    },
    {
        "id": "cons-retail",
        "company": "Marketrow Grocers",
        "sector": "Consumer",
        "text": (
            "Marketrow Grocers reports same-store sales and inventory shrinkage. Grocery shops sold "
            "more than last year, and theft of stock rose."
        ),
    },
    {
        "id": "cons-luxury",
        "company": "Atelier Vale",
        "sector": "Consumer",
        "text": (
            "Atelier Vale discusses handbag pricing power and demand from Chinese tourists in its "
            "European stores."
        ),
    },
    {
        "id": "cons-ad",
        "company": "Brightfold Media",
        "sector": "Consumer",
        "text": (
            "Brightfold Media reports digital advertising cost per click and the conversion rate on "
            "those paid placements."
        ),
    },
    {
        "id": "ind-rail",
        "company": "Ironspan Rail",
        "sector": "Industrials",
        "text": (
            "Ironspan Rail moved freight volume measured in carloads and published its operating ratio, "
            "the share of revenue consumed by operating cost."
        ),
    },
    {
        "id": "ind-aero",
        "company": "Wingset Aviation",
        "sector": "Industrials",
        "text": (
            "Wingset Aviation has commercial aircraft delivery delays because supplier shortages left "
            "parts missing from the assembly line."
        ),
    },
    {
        "id": "ind-chem",
        "company": "Saltwick Chemicals",
        "sector": "Industrials",
        "text": (
            "Saltwick Chemicals reports the polyethylene spread and the ethane feedstock cost. "
            "The profit gap on the plastic resin depends on the gas used to make it."
        ),
    },
]

# Labels below were written with the documents above and were not taken from a ranking.
QUERIES: list[dict[str, Any]] = [
    {"id": "q01", "category": "exact", "text": "graphics processors model-training clusters", "relevant": ["tech-gpu"]},
    {"id": "q02", "category": "exact", "text": "net interest margin deposit beta", "relevant": ["fin-nim"]},
    {"id": "q03", "category": "exact", "text": "liquefied natural gas export terminal utilization", "relevant": ["energy-lng"]},
    {"id": "q04", "category": "exact", "text": "same-store sales inventory shrinkage", "relevant": ["cons-retail"]},
    {"id": "q05", "category": "exact", "text": "cardiac stent hospital purchasing", "relevant": ["health-device"]},
    {"id": "q06", "category": "exact", "text": "payment for order flow retail trading", "relevant": ["fin-broker"]},
    {"id": "q07", "category": "exact", "text": "polyethylene spread ethane feedstock", "relevant": ["ind-chem"]},
    {"id": "q08", "category": "exact", "text": "freight railroad carloads operating ratio", "relevant": ["ind-rail"]},
    {"id": "q09", "category": "paraphrase", "text": "Which note covers demand for chips used to train large neural networks?", "relevant": ["tech-gpu"]},
    {"id": "q10", "category": "paraphrase", "text": "How quickly do savings accounts reprice when loan yields move?", "relevant": ["fin-nim"]},
    {"id": "q11", "category": "paraphrase", "text": "Is the gas-export facility running near full capacity?", "relevant": ["energy-lng"]},
    {"id": "q12", "category": "paraphrase", "text": "Are grocery shops selling more than last year, and is theft of stock rising?", "relevant": ["cons-retail"]},
    {"id": "q13", "category": "paraphrase", "text": "What happened to volumes of tubes used to prop open heart arteries?", "relevant": ["health-device"]},
    {"id": "q14", "category": "paraphrase", "text": "Do brokers get paid by venues for sending small-investor orders?", "relevant": ["fin-broker"]},
    {"id": "q15", "category": "paraphrase", "text": "What is the profit gap on plastic resin versus the cost of the gas used to make it?", "relevant": ["ind-chem"]},
    {"id": "q16", "category": "paraphrase", "text": "How many wagon-loads did the train company move, and what share of revenue is operating cost?", "relevant": ["ind-rail"]},
    {"id": "q17", "category": "paraphrase", "text": "Recurring revenue from software that catches malware on employee laptops", "relevant": ["tech-cyber"]},
    {"id": "q18", "category": "paraphrase", "text": "Contracted capacity that has not yet been recognized as revenue at the infrastructure rental business", "relevant": ["tech-cloud"]},
    {"id": "q19", "category": "confusable", "text": "planned spending to build new refineries", "relevant": ["energy-refinery"]},
    {"id": "q20", "category": "confusable", "text": "cash sent back to shareholders through dividends", "relevant": ["energy-return"]},
    {"id": "q21", "category": "confusable", "text": "server chips for database machines", "relevant": ["tech-cpu"]},
    {"id": "q22", "category": "confusable", "text": "subscription retention for application software", "relevant": ["tech-saas"]},
    {"id": "q23", "category": "confusable", "text": "credit losses on card balances", "relevant": ["fin-card"]},
    {"id": "q24", "category": "confusable", "text": "fee rate charged on managed assets", "relevant": ["fin-aum"]},
    {"id": "q25", "category": "confusable", "text": "handbag prices and visitors from China", "relevant": ["cons-luxury"]},
    {"id": "q26", "category": "confusable", "text": "aircraft not delivered because parts are missing", "relevant": ["ind-aero"]},
    {"id": "q27", "category": "multi", "text": "GLP-1 obesity drug programs", "relevant": ["health-glp-price", "health-glp-trial"]},
    {"id": "q28", "category": "multi", "text": "capital allocation between new plants and shareholder payout", "relevant": ["energy-refinery", "energy-return"]},
    {"id": "q29", "category": "multi", "text": "renewable power projects", "relevant": ["energy-solar", "energy-wind"]},
    {"id": "q30", "category": "multi", "text": "software sold as a subscription", "relevant": ["tech-saas", "tech-cyber"]},
    {"id": "q31", "category": "multi", "text": "plants that turn hydrocarbons into products", "relevant": ["energy-refinery", "ind-chem"]},
    {"id": "q32", "category": "multi", "text": "individual-investor trading and asset-management fees", "relevant": ["fin-broker", "fin-aum"]},
    {"id": "q33", "category": "ambiguous", "text": "capital", "relevant": ["energy-refinery", "energy-return"]},
    {"id": "q34", "category": "ambiguous", "text": "subscription", "relevant": ["tech-saas", "tech-cyber"]},
    {"id": "q35", "category": "ambiguous", "text": "renewables", "relevant": ["energy-solar", "energy-wind"]},
    {"id": "q36", "category": "ambiguous", "text": "drug prices", "relevant": ["health-glp-price", "health-biosim"]},
    {"id": "q37", "category": "unanswerable", "text": "municipal general obligation bond coupon", "relevant": []},
    {"id": "q38", "category": "unanswerable", "text": "cryptocurrency staking yield", "relevant": []},
    {"id": "q39", "category": "unanswerable", "text": "farmland cash rent per acre", "relevant": []},
    {"id": "q40", "category": "unanswerable", "text": "life insurance statutory capital ratio", "relevant": []},
    {"id": "q41", "category": "unanswerable", "text": "container shipping spot rate from Shanghai to Rotterdam", "relevant": []},
    {"id": "q42", "category": "unanswerable", "text": "timberland harvest volume in board feet", "relevant": []},
]


def validate_corpus() -> None:
    """Raise if the hand labels are internally inconsistent. This does not look at scores."""
    ids = [doc["id"] for doc in DOCUMENTS]
    if len(ids) != len(set(ids)):
        raise ValueError("duplicate document id")
    if not 15 <= len(ids) <= 30:
        raise ValueError(f"expected 15 to 30 documents, found {len(ids)}")
    if len(QUERIES) < 40:
        raise ValueError(f"expected at least 40 queries, found {len(QUERIES)}")
    qids = [query["id"] for query in QUERIES]
    if len(qids) != len(set(qids)):
        raise ValueError("duplicate query id")
    known = set(ids)
    for query in QUERIES:
        missing = [doc_id for doc_id in query["relevant"] if doc_id not in known]
        if missing:
            raise ValueError(f"{query['id']} cites unknown documents {missing}")
        if query["category"] == "unanswerable" and query["relevant"]:
            raise ValueError(f"{query['id']} is unanswerable but has labels")
        if query["category"] != "unanswerable" and not query["relevant"]:
            raise ValueError(f"{query['id']} has no relevant document")
        if query["category"] == "multi" and len(query["relevant"]) < 2:
            raise ValueError(f"{query['id']} is multi but has fewer than two labels")
