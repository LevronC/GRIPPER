# Explanation evaluation

Scripted model JSON exercises the validator. It is not a Savant quality measurement and it is not a claim of factual grounding.

- Live provider called: False.
- Scripted requests observed: 12. Unexpected host: False.
- Other-tenant text appeared in an explanation: False.
- Commit: `ebc60e42dc2e3bfd08c403f5b75d958a561a4089`.

| Pass | Cases | Template | Kept model text | Fallbacks | Mean latency ms | Compliance unchanged |
|---|---:|---:|---:|---:|---:|---|
| deterministic | 12 | 12 | 0 | 0 | 3.26 | True |
| scripted | 12 | 4 | 8 | 4 | 2.82 | True |

## Samples

- source `llm` fallback `None` citations `['411a7874-f057-5ddd-903e-a11a5e1945ee']`: EVAL01 is 8.0% of the portfolio; the single-position limit is 5.0%. This violation is open. It stays open until the holdings or the rule change and the portfolio is re-evaluated; r
- source `llm` fallback `None` citations `['6941366a-7b7f-5ded-b9bb-8feca0a9ffdf']`: EVAL02 is 8.0% of the portfolio; the single-position limit is 5.0%. This violation is open. It stays open until the holdings or the rule change and the portfolio is re-evaluated; r
- source `llm` fallback `None` citations `['34e90225-b476-51a1-b5f9-6fcd948eec9e']`: EVAL03 is 8.0% of the portfolio; the single-position limit is 5.0%. This violation is open. It stays open until the holdings or the rule change and the portfolio is re-evaluated; r
- source `llm` fallback `None` citations `['ea9a3d05-da57-537a-be3c-3f6d76f0d57e']`: EVAL04 is 8.0% of the portfolio; the single-position limit is 5.0%. This violation is open. It stays open until the holdings or the rule change and the portfolio is re-evaluated; r
- source `llm` fallback `None` citations `['e82a3c61-57bc-561b-b90c-c449cbc7408a']`: EVAL05 is 8.0% of the portfolio; the single-position limit is 5.0%. This violation is open. It stays open until the holdings or the rule change and the portfolio is re-evaluated; r
- source `llm` fallback `None` citations `['37d9a478-a8bb-5b99-852d-67a609f68e18']`: EVAL06 is 8.0% of the portfolio; the single-position limit is 5.0%. This violation is open. It stays open until the holdings or the rule change and the portfolio is re-evaluated; r
- source `llm` fallback `None` citations `['b7779e63-7813-5455-a5ab-d32e66913853']`: EVAL07 is 8.0% of the portfolio; the single-position limit is 5.0%. This violation is open. It stays open until the holdings or the rule change and the portfolio is re-evaluated; r
- source `llm` fallback `None` citations `['5080e6b6-69e4-5428-a73b-1342204734b5']`: EVAL08 is 8.0% of the portfolio; the single-position limit is 5.0%. This violation is open. It stays open until the holdings or the rule change and the portfolio is re-evaluated; r
- source `template` fallback `invalid_citations` citations `[]`: EVAL09 is 8.0% of the portfolio; the single-position limit is 5.0%. This violation is open. It stays open until the holdings or the rule change and the portfolio is re-evaluated; r
- source `template` fallback `invalid_citations` citations `[]`: EVAL10 is 8.0% of the portfolio; the single-position limit is 5.0%. This violation is open. It stays open until the holdings or the rule change and the portfolio is re-evaluated; r
- source `template` fallback `invalid_output` citations `[]`: EVAL11 is 8.0% of the portfolio; the single-position limit is 5.0%. This violation is open. It stays open until the holdings or the rule change and the portfolio is re-evaluated; r
- source `template` fallback `invalid_output` citations `[]`: EVAL12 is 8.0% of the portfolio; the single-position limit is 5.0%. This violation is open. It stays open until the holdings or the rule change and the portfolio is re-evaluated; r

## Review of the samples

Read after the run, from the rows above. Not produced by the model.

The eight kept explanations still open with the deterministic sentence `EVAL0N is 8.0% of the portfolio; the single-position limit is 5.0%` and `This violation is open`. The scripted commentary is attached after that sentence. The two other-tenant citations and the malformed body fell back to the template, and the sample does not contain `LEAKED-FROM-OTHER-TENANT` or `OTHER-TENANT`. The status-claim body (`This violation was resolved`) also fell back; the stored violation stayed open. That is a citation and schema check. It does not show that the commentary is factually supported, and it was not a live Savant call.

## Review of the samples

Read after the run, from the rows above. Not produced by the model.

The eight kept explanations still open with the deterministic sentence `EVAL0N is 8.0% of the portfolio; the single-position limit is 5.0%` and `This violation is open`. The scripted commentary is attached after that sentence. The two other-tenant citations and the malformed body fell back to the template, and the sample does not contain `LEAKED-FROM-OTHER-TENANT` or `OTHER-TENANT`. The status-claim body (`This violation was resolved`) also fell back; the stored violation stayed open. That is a citation and schema check. It does not show that the commentary is factually supported, and it was not a live Savant call.
