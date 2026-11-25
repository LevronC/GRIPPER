"""Evidence selection regression tests; no database or external provider calls."""

import uuid
from types import SimpleNamespace
from unittest.mock import MagicMock

from app.services.governance import explain
from app.services.retrieval.searcher import SearchOutcome, _fill_missing_cosine


def test_insufficient_evidence_preserves_violation_without_calling_provider(monkeypatch):
    event = SimpleNamespace(
        id=uuid.uuid4(), rule_id=None, resolved=False,
        event_type="single_position_cap", severity="critical",
        details_json={"ticker": "SYNTH", "current_weight": 0.08, "threshold": 0.05},
    )
    db = MagicMock()
    db.execute.return_value.scalar_one_or_none.return_value = event
    provider = MagicMock(side_effect=AssertionError("provider must not be called"))
    monkeypatch.setattr(explain, "maybe_explain", provider)
    monkeypatch.setattr(explain, "hybrid_search", lambda *a, **kw: SearchOutcome(
        results=[{"chunk_id": "irrelevant", "cosine_similarity": 0.1}],
        retrieval_mode="hybrid", embedding={"provider": "local"},
    ))

    result = explain.generate_violation_explanation(db, event.id, uuid.uuid4())

    assert result["research_status"] == "insufficient"
    assert result["violation_status"] == "open"
    assert result["explanation_source"] == "template"
    assert result["evidence"] == []
    assert result["citations"] == []
    assert result["llm"]["attempted"] is False
    assert event.resolved is False
    provider.assert_not_called()


def test_cosine_backfill_requires_matching_tenant_and_active_space():
    tenant = uuid.uuid4()
    db = MagicMock()
    db.info = {"tenant_id": str(tenant)}
    rows = [{"chunk_id": str(uuid.uuid4()), "cosine_similarity": None}]
    _fill_missing_cosine(db, uuid.uuid4(), rows, [1.0], "test@1")
    _fill_missing_cosine(db, tenant, rows, [1.0], None)
    db.execute.assert_not_called()


def test_cosine_backfill_filters_embedding_provenance():
    tenant = uuid.uuid4()
    db = MagicMock()
    db.info = {"tenant_id": str(tenant)}
    db.execute.return_value.scalar.return_value = None
    rows = [{"chunk_id": str(uuid.uuid4()), "cosine_similarity": None}]
    _fill_missing_cosine(db, tenant, rows, [1.0], "test@1")
    statement, parameters = db.execute.call_args.args
    assert "embedding_model = :space" in str(statement)
    assert parameters["space"] == "test@1"
    assert parameters["institution"] == tenant
    assert rows[0]["cosine_similarity"] is None
