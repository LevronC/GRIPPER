"""
The full-text leg used by the evaluation script, on the real database.

Finding an exact shared term inside one tenant is a mechanics check. It is not
a measurement of semantic retrieval quality.
"""

from __future__ import annotations

import pytest

from app.db.session import SessionLocal, set_tenant
from app.services.retrieval.metrics import hit_at_k
from app.services.retrieval.searcher import full_text_leg

pytestmark = pytest.mark.integration


def test_full_text_leg_hits_the_tenant_chunk_only(two_tenants):
    alpha, bravo = two_tenants.a, two_tenants.b
    with SessionLocal() as db:
        set_tenant(db, alpha.institution_id)
        rows = full_text_leg(db, "Semiconductor liquidity risk", alpha.institution_id, limit=5)
    found = [row["chunk_id"] for row in rows]
    assert hit_at_k(found, [str(alpha.chunk_id)], 5) == 1.0
    assert str(bravo.chunk_id) not in found
