"""
Re-embed chunks whose vectors are missing or from a different embedding space.

    MIGRATION_DATABASE_URL=... EMBEDDING_PROVIDER=local python scripts/reembed.py            # dry run
    MIGRATION_DATABASE_URL=... EMBEDDING_PROVIDER=local python scripts/reembed.py --apply    # write

Dry run (default) only reports counts per embedding space. --apply re-embeds in batches
and stamps each chunk with the active space. Chunks marked 'legacy-unknown' (pre-provenance
rows, which may contain hash vectors) are included. Uses the owner connection; it is an
operator action, so take a backup and get authorisation before running it on production.
"""

from __future__ import annotations

import argparse
import sys

from _cli import owner_engine
from sqlalchemy import text

from app.services.embeddings.generator import EmbeddingUnavailable, active_space, generate_embeddings


def _vec(v):
    return "[" + ",".join(f"{x:.7f}" for x in v) + "]"


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--apply", action="store_true")
    ap.add_argument("--batch", type=int, default=64)
    args = ap.parse_args()

    space = active_space()
    if space is None:
        sys.exit("No embedding provider is available (set EMBEDDING_PROVIDER / HF_API_KEY).")
    eng = owner_engine()
    with eng.connect() as conn:
        counts = conn.execute(text(
            "SELECT coalesce(embedding_model, '(none)') AS m, count(*) FROM document_chunks GROUP BY 1 ORDER BY 1"
        )).all()
    print(f"Active space: {space.space_id} ({space.provider})")
    for model, n in counts:
        marker = "" if model == space.space_id else "  <- needs re-embedding"
        print(f"  {model:40s} {n:>8d}{marker}")
    if not args.apply:
        print("Dry run. Re-run with --apply to re-embed.")
        return 0

    done = 0
    while True:
        with eng.begin() as conn:
            rows = conn.execute(text(
                "SELECT id, content FROM document_chunks "
                "WHERE embedding IS NULL OR embedding_model IS DISTINCT FROM :m "
                "ORDER BY id LIMIT :n FOR UPDATE SKIP LOCKED"
            ), {"m": space.space_id, "n": args.batch}).all()
            if not rows:
                break
            try:
                vectors, used = generate_embeddings([r.content for r in rows])
            except EmbeddingUnavailable as exc:
                sys.exit(f"Embedding failed after {done} chunks: {exc}")
            for row, vec in zip(rows, vectors):
                conn.execute(text(
                    "UPDATE document_chunks SET embedding = CAST(:v AS vector), embedding_model = :m, "
                    "embedding_provider = :p WHERE id = :id"
                ), {"v": _vec(vec), "m": used.space_id, "p": used.provider, "id": row.id})
            done += len(rows)
            print(f"  re-embedded {done}")
    print(f"Done: {done} chunks now in {space.space_id}.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
