# Compliance model

What Gripper's governance engine assumes, decides, and records. Code:
`backend/app/services/governance/{rules,evaluator,holdings,explain}.py`, `backend/app/api/rules.py`.
Tests: `backend/tests/test_governance_rules.py`, `backend/tests/integration/test_violation_lifecycle.py`,
`backend/tests/integration/test_compliance_workflow.py`.

## Supported portfolio model

| Aspect | Gripper's model |
|---|---|
| Positions | **Long-only, unleveraged.** Each holding has an explicit `weight`, a fraction of total portfolio value in `[0, 1]`. Short positions, leverage, derivatives and gross/net exposure are **not supported**. This is a product scope decision, not a general investment constraint. |
| Total weight | `sum(weights) <= 1`, checked exactly in decimal (no tolerance). The remainder is implicit cash. |
| Market values | Not stored. Weights are entered by users, not derived from prices × quantities. `cost_basis` is recorded but unused by any rule. |
| Cash | Implicit (`1 - sum(weights)`); not subject to any rule. |
| Classification | Sector and market-cap class come from a static table of 15 tickers (`TICKER_METADATA`); 2 of them (`MCRT`, `GCAP`) are fictional micro-caps for the demo. Any other ticker is **unclassified**. |
| Missing classification | Never treated as compliant. A rule that needs the classification produces an `insufficient_data` finding listing the unclassified tickers (weight > 0). The single-position rule needs no classification. |
| Zero-value portfolio | All weights 0 (or no holdings) → no findings; any open events are resolved on evaluation. |
| Invalid numbers | NaN, ±Infinity, negative or >1 weights, and non-positive thresholds are rejected by the API (422) and raise `InvalidPortfolioData` in the engine. |

## Arithmetic and boundaries

Weights and thresholds are stored as `float`, but every sum and comparison uses
`Decimal(repr(float))`, the float's shortest decimal representation. Consequences:

* `0.1 + 0.2` equals `0.3` exactly, so a sector at exactly its limit is compliant. With binary
  floats it was `0.30000000000000004` and was reported as "30.0% exceeding the limit of 30.0%"
  (regression test: `test_sector_exactly_at_limit_via_float_sum_is_not_a_breach`).
* Results do not depend on summation order (`test_detection_is_order_independent_and_repeatable`).
* A breach means **strictly greater than** the threshold.
* Severity is `critical` when the value is strictly greater than threshold × multiplier
  (single position 1.2, sector 1.15, liquidity 1.3), otherwise `warning`.
* Legacy rule rows storing percentages (`10.0`) are read as fractions (`0.10`). The API only
  accepts fractions in `(0, 1]`.

## Rules and scope

| Rule type | Measures | Scope (optional) |
|---|---|---|
| `single_position_cap` | each holding's weight | one ticker (e.g. `NVDA`) |
| `sector_exposure_cap` | sum of weights per sector | one sector from the reference table |
| `liquidity_constraint` | sum of micro-cap weights | not scopable |

* An unscoped rule applies to every position or sector. A scoped rule applies only to its ticker or sector.
* **Several rules of the same type may be active** if their scopes differ, e.g. Technology ≤ 30%,
  Healthcare ≤ 20%, Energy ≤ 15%, all positions ≤ 5% and NVDA ≤ 3%.
* At most one **active** rule per `(institution, rule_type, scope)`, enforced by the partial unique
  index `uq_ips_rules_active_type_scope` (duplicate → 409).
* **Evaluation is independent per rule:** no precedence, override, or "most specific wins". A holding
  that breaches both a global cap and its own scoped cap yields two findings, one per rule.
  A scoped rule *looser* than the global one does not exempt the holding from the global rule.
* A rule's type and scope are immutable; to change them, deactivate the rule and create a new one.

## Violation lifecycle

One `governance_events` row per breach episode.

| Situation | Effect |
|---|---|
| Same breach found again (unchanged, re-saved holdings, changed weight still breaching) | Same event id; `details` (current weight, threshold, severity) refreshed |
| Breach no longer found | `resolved=true`, `resolved_at`, `details.resolution = "no_longer_breached"` |
| Rule deactivated or deleted | Resolved on next evaluation with `details.resolution = "rule_inactive"` |
| Breach reappears after resolution | **New** event id; the resolved event is never modified again |
| Rule threshold changed | Open events show the new threshold; resolved events keep the threshold in force when they were last evaluated |

Identity is `(rule_id, event_type, ticker-or-sector)`; `holding_id` is not part of it.

**Limitations:**
* There is no rule versioning and no per-evaluation snapshot table: `governance_events`
  is the history.
* An open event reflects the latest evaluation, not its first detection.
* Evaluation runs when a user triggers it, not continuously.

## What compliance does not depend on

Compliance outcomes come only from active rules and saved holdings. They are unaffected by
research documents, embedding-provider availability, retrieval results, or explanation failures
(`test_compliance_unaffected_by_research_embeddings_or_explanation_failure`). Explanations are
rendered by a fixed template from deterministic facts (`ExplanationFacts` →
`render_template_explanation`). Research is reported as context and never approves, exempts or
resolves a violation. There is no exception-approval workflow.
