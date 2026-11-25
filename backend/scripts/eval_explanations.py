"""
Explanation evaluation on synthetic violations.

The first pass leaves the provider off and times the deterministic template.
The second pass feeds scripted model JSON through the real validator. It does
not call SubQ. Citation checks passing is not factual grounding and is not a
claim that the commentary is hallucination-free.

    cd backend
    export MIGRATION_DATABASE_URL=postgresql://postgres:postgres@127.0.0.1:55432/gripper_eval
    export DATABASE_URL=postgresql://gripper_app:gripper_app_test@127.0.0.1:55432/gripper_eval
    python scripts/eval_explanations.py
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import time
import uuid
from pathlib import Path

import httpx

BACKEND = os.path.dirname(os.path.dirname(os.path.realpath(__file__)))
sys.path.insert(0, BACKEND)
os.environ.setdefault("SECRET_KEY", "cli-placeholder-" + "x" * 32)
os.environ["ENVIRONMENT"] = "test"
os.environ["EMBEDDING_PROVIDER"] = "hash_test"
os.environ["LLM_PROVIDER"] = "none"
os.environ["LLM_EXTERNAL_PROCESSING_ENABLED"] = "false"

from sqlalchemy import create_engine, text  # noqa: E402

from eval_common import ensure_database, git_revision, require_local_database, upgrade  # noqa: E402

NAMESPACE = uuid.UUID("6ba7b813-9dad-11d1-80b4-00c04fd430c8")
CASES = 12


def _literal(values: list[float]) -> str:
    return "[" + ",".join(f"{value:.6f}" for value in values) + "]"


def _completion(content: str) -> httpx.Response:
    return httpx.Response(200, json={
        "id": "eval",
        "object": "chat.completion",
        "created": 0,
        "model": "subq-savant-1.4",
        "choices": [{"index": 0, "message": {"role": "assistant", "content": content}, "finish_reason": "stop"}],
        "usage": {"prompt_tokens": 1, "completion_tokens": 1, "total_tokens": 2},
    })


def _seed(owner_url: str, runtime_url: str) -> tuple[uuid.UUID, uuid.UUID, list[uuid.UUID], str]:
    from app.db.session import make_session_factory, set_tenant
    from app.services.embeddings.generator import _hash_embed, active_space

    space = active_space()
    if space is None:
        raise SystemExit("hash_test embeddings are required")
    alpha = uuid.uuid5(NAMESPACE, "alpha")
    bravo = uuid.uuid5(NAMESPACE, "bravo")
    foreign = uuid.uuid5(NAMESPACE, "foreign-chunk")
    owner = create_engine(owner_url)
    with owner.begin() as conn:
        for institution, slug, name in (
            (alpha, "synthetic-explain-a", "Synthetic Explain A"),
            (bravo, "synthetic-explain-b", "Synthetic Explain B"),
        ):
            conn.execute(text("DELETE FROM institutions WHERE id = :i"), {"i": institution})
            conn.execute(
                text("INSERT INTO institutions (id, name, slug, tier, external_processing_authorized, created_at) "
                     "VALUES (:i, :n, :s, 'free', true, now())"),
                {"i": institution, "n": name, "s": slug},
            )
    owner.dispose()

    factory = make_session_factory(runtime_url)
    event_ids: list[uuid.UUID] = []
    with factory() as db:
        set_tenant(db, bravo)
        report_b = uuid.uuid5(NAMESPACE, "report-b")
        db.execute(text(
            "INSERT INTO research_reports (id, institution_id, sector, company, recommendation, status, created_at) "
            "VALUES (:r, :i, 'Energy', 'Other Tenant Co', 'hold', 'processed', now())"
        ), {"r": report_b, "i": bravo})
        foreign_text = "OTHER-TENANT confidential note that must not be cited"
        db.execute(text(
            "INSERT INTO document_chunks (id, institution_id, report_id, content, embedding, embedding_model, "
            "embedding_provider, metadata_json, created_at) "
            "VALUES (:c, :i, :r, :t, CAST(:v AS vector), :m, 'hash_test', CAST(:meta AS json), now())"
        ), {
            "c": foreign, "i": bravo, "r": report_b, "t": foreign_text, "v": _literal(_hash_embed(foreign_text)),
            "m": space.space_id, "meta": '{"page": 9, "chunk_index": 0, "synthetic": true}',
        })
        db.commit()

    with factory() as db:
        set_tenant(db, alpha)
        portfolio = uuid.uuid5(NAMESPACE, "portfolio")
        rule = uuid.uuid5(NAMESPACE, "rule")
        db.execute(text(
            "INSERT INTO portfolios (id, institution_id, name, strategy_type, created_at) "
            "VALUES (:p, :i, 'Synthetic book', 'growth', now())"
        ), {"p": portfolio, "i": alpha})
        db.execute(text(
            "INSERT INTO ips_rules (id, institution_id, rule_type, threshold, severity, active, scope, created_at) "
            "VALUES (:r, :i, 'single_position_cap', 0.05, 'warning', true, NULL, now())"
        ), {"r": rule, "i": alpha})
        for index in range(CASES):
            ticker = f"EVAL{index + 1:02d}"
            report = uuid.uuid5(NAMESPACE, f"report-{ticker}")
            chunk = uuid.uuid5(NAMESPACE, f"chunk-{ticker}")
            holding = uuid.uuid5(NAMESPACE, f"holding-{ticker}")
            event = uuid.uuid5(NAMESPACE, f"event-{ticker}")
            content = f"{ticker} investment thesis position sizing risk. Synthetic excerpt for {ticker} only."
            db.execute(text(
                "INSERT INTO research_reports (id, institution_id, sector, company, recommendation, status, created_at) "
                "VALUES (:r, :i, 'Technology', :company, 'hold', 'processed', now())"
            ), {"r": report, "i": alpha, "company": f"{ticker} Corp"})
            db.execute(text(
                "INSERT INTO document_chunks (id, institution_id, report_id, content, embedding, embedding_model, "
                "embedding_provider, metadata_json, created_at) "
                "VALUES (:c, :i, :r, :t, CAST(:v AS vector), :m, 'hash_test', CAST(:meta AS json), now())"
            ), {
                "c": chunk, "i": alpha, "r": report, "t": content, "v": _literal(_hash_embed(content)),
                "m": space.space_id,
                "meta": json.dumps({"page": 1, "chunk_index": 0, "synthetic": True}),
            })
            db.execute(text(
                "INSERT INTO holdings (id, portfolio_id, ticker, weight, cost_basis, updated_at) "
                "VALUES (:h, :p, :t, 0.08, 10, now())"
            ), {"h": holding, "p": portfolio, "t": ticker})
            db.execute(text(
                "INSERT INTO governance_events (id, institution_id, portfolio_id, holding_id, rule_id, event_type, "
                "severity, details_json, resolved, created_at) "
                "VALUES (:e, :i, :p, :h, :rule, 'single_position_cap', 'warning', CAST(:d AS json), false, now())"
            ), {
                "e": event, "i": alpha, "p": portfolio, "h": holding, "rule": rule,
                "d": json.dumps({"ticker": ticker, "current_weight": 0.08, "threshold": 0.05}),
            })
            event_ids.append(event)
        db.commit()
    return alpha, bravo, event_ids, str(foreign)


def _run(runtime_url: str, institution: uuid.UUID, event_ids: list[uuid.UUID]) -> list[dict]:
    from app.db.session import make_session_factory, set_tenant
    from app.services.governance.explain import generate_violation_explanation

    factory = make_session_factory(runtime_url)
    rows = []
    with factory() as db:
        set_tenant(db, institution)
        for event_id in event_ids:
            started = time.perf_counter()
            body = generate_violation_explanation(db, event_id, institution)
            elapsed = time.perf_counter() - started
            resolved = db.execute(text("SELECT resolved FROM governance_events WHERE id = :e"), {"e": event_id}).scalar()
            rows.append({
                "event_id": str(event_id),
                "latency_ms": round(elapsed * 1000, 3),
                "explanation_source": body.get("explanation_source"),
                "fallback_reason": body.get("fallback_reason"),
                "violation_status": body.get("violation_status"),
                "resolved_after": bool(resolved),
                "citation_ids": [item.get("chunk_id") for item in body.get("citations") or []],
                "explanation": (body.get("explanation") or "")[:400],
                "error": body.get("error"),
            })
    return rows


def _scripted_transport(foreign_chunk_id: str):
    from app.services.llm.providers import subq as subq_mod

    seen: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(request)
        if request.url.host != "api.subq.ai":
            return httpx.Response(500, json={"error": {"message": "unexpected host", "code": "unexpected"}})
        index = len(seen) - 1
        user = json.loads(request.content)["messages"][1]["content"]
        payload = json.loads(user)
        excerpts = payload.get("excerpts") or []
        own = excerpts[0]["chunk_id"] if excerpts else ""
        if index < 8:
            content = json.dumps({
                "policy_restatement": "The supplied policy facts stand.",
                "research_commentary": f"SYNTHETIC-NOTE {index + 1} discusses the named position.",
                "cited_chunk_ids": [own],
                "insufficient_research": False,
            })
        elif index < 10:
            content = json.dumps({
                "policy_restatement": "The supplied policy facts stand.",
                "research_commentary": "LEAKED-FROM-OTHER-TENANT",
                "cited_chunk_ids": [foreign_chunk_id],
                "insufficient_research": False,
            })
        elif index == 10:
            content = "not-json"
        else:
            content = json.dumps({
                "policy_restatement": "The supplied policy facts stand.",
                "research_commentary": "This violation was resolved.",
                "cited_chunk_ids": [own] if own else [],
                "insufficient_research": not bool(own),
            })
        return _completion(content)

    subq_mod.transport_override = httpx.MockTransport(handler)
    return seen


def _summarize(rows: list[dict], *, scripted: bool) -> dict:
    latencies = [row["latency_ms"] for row in rows]
    return {
        "cases": len(rows),
        "compliance_unchanged": all(row["violation_status"] == "open" and row["resolved_after"] is False for row in rows),
        "template_count": sum(row["explanation_source"] == "template" for row in rows),
        "llm_count": sum(row["explanation_source"] == "llm" for row in rows),
        "fallback_count": sum(bool(row["fallback_reason"]) for row in rows),
        "fallback_rate": sum(bool(row["fallback_reason"]) for row in rows) / len(rows),
        "mean_latency_ms": sum(latencies) / len(latencies),
        "scripted_model": scripted,
        "live_provider": False,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out", default="eval_results/phase4b/explanations")
    args = parser.parse_args()
    out = Path(BACKEND) / args.out
    if out.with_suffix(".json").exists() or out.with_suffix(".md").exists():
        raise SystemExit("Output exists; choose a new --out to preserve previous results.")
    admin = ensure_database(os.environ.get("MIGRATION_DATABASE_URL") or "", replace=False)
    runtime = require_local_database(os.environ.get("DATABASE_URL") or "", "DATABASE_URL")
    upgrade(admin)
    alpha, _bravo, event_ids, foreign = _seed(admin, runtime)
    deterministic = _run(runtime, alpha, event_ids)

    from app.core.config import settings
    from app.services.llm.providers import subq as subq_mod

    settings.LLM_PROVIDER = "subq"
    settings.LLM_EXTERNAL_PROCESSING_ENABLED = True
    settings.SUBQ_API_KEY = "eval-not-a-real-key"
    settings.SUBQ_BASE_URL = "https://api.subq.ai/v1"
    settings.SUBQ_MODEL = "subq-savant-1.4"
    seen = _scripted_transport(foreign)
    try:
        scripted = _run(runtime, alpha, event_ids)
    finally:
        subq_mod.transport_override = None
        settings.LLM_PROVIDER = "none"
        settings.LLM_EXTERNAL_PROCESSING_ENABLED = False
        settings.SUBQ_API_KEY = ""

    leaked = any("LEAKED-FROM-OTHER-TENANT" in row["explanation"] or "OTHER-TENANT" in row["explanation"] for row in scripted)
    payload = {
        "synthetic": True,
        "live_provider_called": False,
        "note": "Scripted model JSON exercises the validator. It is not a Savant quality measurement and it is not a claim of factual grounding.",
        "requests_seen": len(seen),
        "unexpected_host": any(request.url.host != "api.subq.ai" for request in seen),
        "other_tenant_text_in_output": leaked,
        "deterministic": {**_summarize(deterministic, scripted=False), "rows": deterministic},
        "scripted": {**_summarize(scripted, scripted=True), "rows": scripted},
        "git_revision": git_revision(),
    }
    out.parent.mkdir(parents=True, exist_ok=True)
    out.with_suffix(".json").write_text(json.dumps(payload, indent=2) + "\n")
    out.with_suffix(".md").write_text(_markdown(payload))
    print(out.with_suffix(".md").read_text())
    return 0 if payload["deterministic"]["compliance_unchanged"] and payload["scripted"]["compliance_unchanged"] and not leaked else 1


def _markdown(payload: dict) -> str:
    lines = [
        "# Explanation evaluation",
        "",
        payload["note"],
        "",
        f"- Live provider called: {payload['live_provider_called']}.",
        f"- Scripted requests observed: {payload['requests_seen']}. Unexpected host: {payload['unexpected_host']}.",
        f"- Other-tenant text appeared in an explanation: {payload['other_tenant_text_in_output']}.",
        f"- Commit: `{payload['git_revision']}`.",
        "",
        "| Pass | Cases | Template | Kept model text | Fallbacks | Mean latency ms | Compliance unchanged |",
        "|---|---:|---:|---:|---:|---:|---|",
    ]
    for name in ("deterministic", "scripted"):
        block = payload[name]
        lines.append(
            f"| {name} | {block['cases']} | {block['template_count']} | {block['llm_count']} | "
            f"{block['fallback_count']} | {block['mean_latency_ms']:.2f} | {block['compliance_unchanged']} |"
        )
    lines += ["", "## Samples", ""]
    for row in payload["scripted"]["rows"]:
        lines.append(
            f"- source `{row['explanation_source']}` fallback `{row['fallback_reason']}` "
            f"citations `{row['citation_ids']}`: {row['explanation'][:180]}"
        )
    lines.append("")
    return "\n".join(lines)


if __name__ == "__main__":
    raise SystemExit(main())
