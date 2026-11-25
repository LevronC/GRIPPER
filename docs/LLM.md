# Explanations and external processing

Compliance status is computed only by the governance engine. An optional language
model may comment on excerpts that retrieval already selected. It cannot change
a violation, approve an exception, or replace the policy sentences.

Code: `backend/app/services/llm/`, `backend/app/services/governance/explain.py`.
Tests: `backend/tests/test_llm.py`, `backend/tests/integration/test_llm_explanations.py`.

## What is on by default

`LLM_PROVIDER=none`. No explanation request leaves the process. The API returns
`explanation_source: "template"`.

SubQ is used only when all of these are true:

1. `LLM_PROVIDER=subq`
2. `LLM_EXTERNAL_PROCESSING_ENABLED=true`
3. `institutions.external_processing_authorized` is true for that institution

The column defaults to false. The runtime database role can read it and cannot
update `institutions`. An operator sets it with the owner connection:

```bash
cd backend
python scripts/set_external_processing.py --slug example-smif --enable --confirm-external-processing
python scripts/set_external_processing.py --slug example-smif --disable
```

There is no API for a user to choose the provider, the model, or the endpoint.
`SUBQ_BASE_URL` is accepted only when it is `https://api.subq.ai/v1`. Redirects
are not followed, and the HTTP client does not use `HTTP_PROXY` / `HTTPS_PROXY`.

## What a SubQ request contains

One stateless `POST https://api.subq.ai/v1/chat/completions` for model
`subq-savant-1.4` (the id is the `SUBQ_MODEL` setting). The body is:

- A fixed system instruction.
- The deterministic policy sentences, violation status, ticker or sector, the
  weight and threshold already stored on the event, and the retrieval mode.
- At most three excerpts, each truncated to 1,200 characters, with chunk id,
  company, sector, and page. These are the top retrieval results for that
  institution. Empty passages are dropped.

Not sent: passwords, emails, API keys, file paths, the rest of the portfolio,
embeddings, or documents that retrieval did not return. The request sets
`store: false`, `reasoning_effort: low`, and `max_tokens` from
`LLM_MAX_OUTPUT_TOKENS` (default 500). It does not enable tools, web search,
file upload, or a provider-side conversation.

Savant always reasons, and reasoning tokens count toward `max_tokens`. `low` is
the smallest effort the API allows (`none` is rejected). A response that spends
the whole cap on reasoning is discarded and the template is shown.

The model must return a JSON object. Gripper parses it again locally and
rejects unknown fields, unknown citation ids, citations that were not in the
prompt, research commentary with no citation, and phrasing that tries to mark
the violation resolved or exempt. Citation metadata shown to the user is read
from the retrieved rows, not from the model. A rejection discards the model
text. `violation_status` is still the evaluator's value.

There is no numeric relevance cutoff. Rank is not a verified relevance score.
The prompt says so. A cutoff needs labeled data and is left for a later
evaluation phase. Passing citation checks does not mean the commentary is
factually grounded.

## SubQ contract this code follows

Checked against the docs on 2026-11-25 (not against a live account):

| Item | Documented behavior used here |
|---|---|
| Auth | `Authorization: Bearer` |
| Text model | `subq-savant-1.4`, early access, per organization. A key can be valid and still get `403 model_not_allowed`. `GET /v1/models` lists only what the key can call. |
| Endpoint | `POST /v1/chat/completions` |
| Structured output | `response_format.type = json_schema`, nested under `response_format.json_schema`, `strict: true` |
| Output cap | `max_tokens` (not `max_completion_tokens`); includes reasoning tokens |
| Temperature | Omitted. Any value other than `1` is `400 unsupported_value`. |
| Reasoning | Cannot be disabled. This client sends `low`. |
| Errors | OpenAI-style `error.code`. Permanent: 400, 401 `invalid_api_key`, 402 `insufficient_credits`, 403 `model_not_allowed`. One retry: 429, 502, 503, 504, 529, timeouts, transport errors. |
| Snap | `subq-snap-1.2` on `POST /v1/systemone`. Not called. It is not a text model. |

Published rates for Savant, from the models page: input $0.10 / 1M tokens, cached input $0.01 / 1M, output $0.50 / 1M. Reasoning is billed as output. These are list prices, not a quote and not a measurement from this account.

## Retention and training

From SubQ's data-retention page, terms, and privacy policy as fetched on 2026-11-25:

- Chat Completions inputs and outputs are deleted within 60 days, except content flagged for a Terms or Usage Policy investigation, and except where the law requires longer retention.
- `store: false`, which this client sends, is the per-request opt-out described in those docs. It is not an organization-wide zero-data-retention agreement. Zero-data retention is a separate request to SubQ, and even then their terms say flagged content may be kept for investigation.
- SubQ says it always records model, token counts, timing, and metadata for billing. This client sends no metadata. Their docs say that billing record does not include prompts or completions.
- The published terms say SubQ does not use customer content to train or improve its foundational models, unless the customer directs that in writing. Safety review (automated, and limited human review when flagged) is still described.
- Gripper has not executed a separate order form or zero-data-retention request. The sentences above are the public documents, not a representation that a particular account is covered by a negotiated addendum.

No institutional research is sent by the test suite. Live calls are not part of CI.

## Hugging Face embeddings

Separate from explanations. When `EMBEDDING_PROVIDER=hf_api` (or `auto` with `HF_API_KEY` set), `generator.py` POSTs chunk text and query text to `https://router.huggingface.co/hf-inference/models/BAAI/bge-small-en-v1.5/pipeline/feature-extraction`. Hugging Face's Inference Providers security page says Hugging Face does not store request bodies or responses for that routing path, does not store user data for training, and keeps debug logs for up to 30 days that it says contain no user data or tokens. It also says to read the downstream provider's policy. Which organization serves the `hf-inference` route for this model, beyond that page, was not verified here. An authenticated call has not been made (same status as Phase 2). Local embeddings do not leave the machine. With no provider, retrieval is full-text only and nothing is embedded externally.

## Checking access without customer data

```bash
cd backend
LLM_PROVIDER=subq SUBQ_API_KEY=... python scripts/llm_preflight.py
LLM_PROVIDER=subq SUBQ_API_KEY=... python scripts/llm_preflight.py --generate
```

The key is an environment variable. Do not paste it into a chat. The first command sends one `GET /v1/models`. `--generate` is the authorization for a second call: one `POST /v1/chat/completions` whose only user text is "Reply with the single word ready. This is a synthetic connectivity check with no customer data." That call uses `max_tokens` 64, `reasoning_effort: low`, `store: false`, and no schema, so it does not exercise structured output. Structured output is covered by the mocked tests. If Savant is absent, the command exits 3, does not call Snap, and leaves live generation marked unverified. `GET /health` reports `capabilities.llm.live_generation: "unverified"` until a live completion has actually been run and recorded; the application does not flip that flag by itself.

At the published rates, the synthetic call is on the order of a few thousandths of a cent if the prompt is a few dozen tokens and the output stays inside 64 tokens. A normal explanation is capped at 16,000 characters of prompt and 500 output tokens, which at those rates is still under about one cent before caching. Tokenization can differ from a character estimate. Neither figure is an invoice.
